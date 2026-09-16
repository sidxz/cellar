# Import data shape (batch 1) — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Lean plan by user ruling: files, interfaces, tests. No per-task reviews; one whole-branch review at the end.

**Goal:** Three data-shape rules the stage evaluator depends on: no direct entry onto a calculated readout, one run holds one shape of data, and a dose-response channel falls back to reported endpoint rows when no fitted curve survives QC.

**Architecture:** Guards live in the application layer next to the use cases they protect (screening imports, bulk create); the DR fallback lives in the campaign resolver (post-QC) with the query port exposing endpoint candidates; the compound page and search reuse the existing raw-layer aggregate query. No migration.

**Spec:** `docs/superpowers/specs/2026-09-11-hit-stages-followups-design.md` §3 (D1, D8). Issue sidxz/cellar#74. Branch `feat/import-data-shape`.

## Global constraints

- Read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md` before backend code.
- Backend tests: `cd backend && uv run pytest tests/unit/...` (no Docker); `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/... tests/api/...` (testcontainers).
- Frontend checks: `cd frontend && pnpm vitest run src/features/screening-assay src/features/screen-campaign src/features/research-organization && pnpm exec biome check src/features && pnpm exec tsc --noEmit -p .`
- Commit with explicit pathspecs (`git commit -m … -- <paths>`); the working tree carries unrelated user changes (`frontend/next-env.d.ts`, `frontend/AGENTS.md`) — never sweep them in. No `Claude-Session` trailer; keep `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Errors are returned as `Failure(DomainError)`, never raised from use cases: `ValidationError` → 422, `ConflictError` → 409, `NotFoundError` → 404 (`interface/error_handlers.py`).
- No new DTO shapes in this batch, so no orval regen. Do not hand-write TS types mirroring backend DTOs.
- Tool shell is fish; BSD sed has no `\b` — use `perl -pi -e` for identifier renames.

Paths below are relative to `backend/src/cellar/` unless prefixed `backend/tests/` or `frontend/`.

---

### Task 1: Refuse direct entry onto a calculated readout (ask 2)

**Modify (backend)**
- `application/screening/preview_summary_file.py:148-153` — build `readout_by_name` only from definitions with `not d.is_calculated`, so the preview never suggests a calculated readout as a target.
- `application/screening/import_summary_file.py::_execute` (after `defs_by_id`, line 185) and `application/screening/preview_summary_import.py::_execute` (after line 123) — add the same check, before parsing the file:
  ```python
  for header, rd_id in mapping.readout_columns.items():
      d = defs_by_id.get(rd_id)
      if d is not None and d.is_calculated:
          return Failure(ValidationError(
              f"Column '{header}' is mapped to readout '{d.name}', which is calculated; "
              "calculated values are computed from other readouts and cannot be imported"
          ))
  ```
  Put the loop in one module-level helper `calculated_readout_error(mapping_pairs: Iterable[tuple[str, uuid.UUID]], defs_by_id) -> ValidationError | None` in `application/screening/readout_entry_guard.py` and call it from both; the plate path below reuses it.
- `application/screening/import_run_file.py:246-262` — in the loop that validates `cmd.mapping.readout_columns`, after the "does not belong" check: `if rd.is_calculated: return Failure(ValidationError(...))` using the helper with `(rc.header, rc.readout_definition_id)` pairs. Apply the identical check wherever `PreviewRunFile` / `RepreviewRunFile` (`application/screening/preview_run_file.py`) validate the mapping's readout columns (grep `readout_definition_id` in that file; the confirmed-mapping path).
- `application/screening/import_run_readouts.py:148` — the `name → id` map is built from all definitions; skip calculated ones so a grid header naming a calculated readout is reported as unknown by the existing unknown-header path (read the code for the exact error it emits and keep it).
- `application/screening/bulk_create_readout_data.py::_resolve_readout_definition_id` (171-215) — after the definition is resolved by id or name: `if d.is_calculated: return Failure(ValidationError(f"Item {idx}: readout '{d.name}' is calculated; values cannot be entered directly"))`. Follow how the existing per-item errors are collected there (they are appended to the result's `errors`, not returned as a whole-call failure — match that).

**Modify (frontend)** — filter `!rd.is_calculated`:
- `frontend/src/features/screening-assay/hooks/use-summary-import-wizard.ts:91-99`
- `frontend/src/features/screening-assay/hooks/use-run-import-wizard.ts:106`
- `frontend/src/features/screening-assay/components/grid-import-dialog.tsx:47,109`

**Tests**
- `backend/tests/unit/application/screening/test_readout_entry_guard.py` (new): helper returns `None` for a non-calculated def, a `ValidationError` naming the column and readout for a calculated one, `None` for an unknown id (membership is someone else's check).
- `backend/tests/unit/application/screening/test_preview_summary_file.py` — a calculated definition whose name matches a header is not suggested.
- `backend/tests/integration/application/screening/test_import_summary_file.py` and `test_preview_summary_import.py` — mapping a column onto a calculated readout → `Failure(ValidationError)`; nothing written.
- `backend/tests/unit/application/screening/test_import_run_file.py` — `TestImportRunFile`: mapping onto a calculated readout → `ValidationError`.
- `backend/tests/integration/application/screening/test_bulk_readout_upsert.py` — item on a calculated readout → per-item error, other items still written.
- Frontend: existing wizard hook tests (if any) gain one case that a calculated definition is absent from the options; otherwise a unit test on the option-building function.

**Interfaces produced**
- `application/screening/readout_entry_guard.py::calculated_readout_error(pairs, defs_by_id) -> ValidationError | None`.

**Commit:** `feat(screening): refuse direct entry onto calculated readouts across summary, plate and bulk paths`

---

### Task 2: One run, one shape (ask 3)

A run is **welled** when `run.wells` is non-empty; **well-less** when it has raw rows with `well_id IS NULL AND is_computed IS FALSE`. Computed rows are excluded because the calculation engine writes calculated readouts well-less on welled runs by design (`readout_calculation_engine.py:352-360`).

**Create**
- `application/screening/run_shape.py`:
  ```python
  def refuse_if_welled(run: Run) -> ConflictError | None:
      """Summary (well-less) import onto a run that already has plates/wells."""
      if run.wells:
          return ConflictError(
              f"Run {run.id} has {len(run.plates)} plate(s) with wells; "
              "well-less summary results cannot be imported onto it"
          )
      return None

  async def refuse_if_wellless(repo: ReadoutDataRepository, workspace_id, run_id) -> ConflictError | None:
      """Plate paths onto a run that already holds well-less summary rows."""
      if await repo.has_wellless_rows(workspace_id, run_id):
          return ConflictError(
              f"Run {run_id} holds well-less summary results; "
              "plate setup and plate import cannot be applied to it"
          )
      return None
  ```

**Modify**
- `domain/screening_assay/repository.py::ReadoutDataRepository` — add `async def has_wellless_rows(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool: ...` with the docstring above (raw rows only).
- `infrastructure/persistence/sqlalchemy/screening_assay/readout_data_repository.py` — implement next to `find_wellless_by_keys` (278-326): `select(exists().where(workspace_id == …, run_id == …, well_id.is_(None), is_computed.is_(False)))`.
- `application/screening/import_summary_file.py::_execute` and `preview_summary_import.py::_execute` — right after the run is loaded: `if (err := refuse_if_welled(run)) is not None: return Failure(err)`.
- `application/screening/preview_run_file.py` (`PreviewRunFile`, `RepreviewRunFile`), `application/screening/import_run_file.py` (`ImportRunFile`), `application/screening/import_run_readouts.py` (`ImportRunReadouts`) — all already hold `self._readout_data_repo`; after loading the run: `if (err := await refuse_if_wellless(self._readout_data_repo, ws, run.id)) is not None: return Failure(err)`.
- `application/screening/plate_setup.py::SetUpRunPlate` (221-318) — add a `readout_data_repo: ReadoutDataRepository` constructor dependency, apply `refuse_if_wellless` after the run loads (line 248); register it in `infrastructure/di/_screening.py:698`.
- `application/screening/bulk_create_readout_data.py` — the run is loaded at 245-249; per item, alongside the definition check:
  ```python
  if run.wells and item.well_id is None:
      errors.append(f"Item {idx}: run has plates; well_id is required")
  elif not run.wells and item.well_id is not None:
      errors.append(f"Item {idx}: run has no plates; well_id must be omitted")
  ```
  `ImportPlateData` (`application/inventory/import_plate_data.py:506-522`) auto-creates a well-less run and sends no `well_id`, so it stays valid — confirm by reading its run-creation branch.

**Tests**
- `backend/tests/unit/application/screening/test_run_shape.py` (new): `refuse_if_welled` on a run with/without wells; `refuse_if_wellless` with a fake repo returning True/False.
- `backend/tests/integration/test_readout_data_repository_find_wellless.py` — `has_wellless_rows` is False on an empty run, False when only computed well-less rows exist, True after a raw well-less row.
- `backend/tests/integration/application/screening/test_import_summary_file.py` — import onto a run with a plate → `Failure(ConflictError)`.
- `backend/tests/unit/application/screening/test_import_run_file.py` — preview and import onto a run whose fake readout repo reports well-less rows → `ConflictError`.
- `backend/tests/unit/screening/test_import_run_readouts.py` and `test_plate_setup.py` — same, one case each (extend the fakes with `has_wellless_rows`).
- `backend/tests/integration/application/screening/test_bulk_readout_upsert.py` — welled run + item without `well_id` → per-item error; well-less run + item with `well_id` → per-item error.

**Interfaces produced**
- `ReadoutDataRepository.has_wellless_rows(workspace_id, run_id) -> bool`
- `run_shape.refuse_if_welled(run) -> ConflictError | None`, `run_shape.refuse_if_wellless(repo, workspace_id, run_id) -> ConflictError | None`

**Commit:** `feat(screening): one run, one shape — refuse summary import onto welled runs and plate paths onto well-less runs`

---

### Task 3: Dose-response channel falls back to reported endpoints, post-QC (ask 1, resolver side)

**Modify**
- `application/research_organization/channel_resolution.py::ChannelResolutionQuery` (port, 82-111) — add:
  ```python
  async def fetch_endpoint_candidates(
      self, *, workspace_id: uuid.UUID, channel: CampaignChannel, molecule_id: uuid.UUID,
  ) -> list[ResolvedCandidate]:
      """Raw-layer readout_data rows for the channel's readout definition, regardless
      of the channel's source_kind. Used as the reported-endpoint fallback on a
      dose-response channel when no curve survives QC."""

  async def fetch_endpoint_candidates_for_runs(
      self, *, workspace_id, run_ids, protocol_id, readout_definition_id, normalization_applied=None,
  ) -> dict[uuid.UUID, list[ResolvedCandidate]]:
  ```
- `infrastructure/persistence/sqlalchemy/research_organization/channel_resolution_query.py` — rename `_fetch_readout_candidates` (332-398) to `fetch_endpoint_candidates` (update the call at 104); extract the readout branch of `fetch_candidates_for_runs` (243-330) into `fetch_endpoint_candidates_for_runs` and call it from the `else` branch so the existing behaviour is unchanged.
- `application/research_organization/channel_resolution.py::ChannelResolver.resolve` (155-160) — after the QC filter:
  ```python
  if not candidates and channel.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE:
      endpoints = await self._q.fetch_endpoint_candidates(
          workspace_id=workspace_id, channel=channel, molecule_id=molecule_id
      )
      candidates = [c for c in endpoints if _passes_qc(c, channel.qc_filter)]
  ```
  Comment: D1 — a QC-passing curve of any class wins; endpoints are considered only when no curve survives QC.
- `application/screening/run_aggregation.py::resolve_intercept` (121) — first statement: `if run.curve_id is None: return run.value, ValueQualifier.EQ` with a comment that a readout row has no intercept to resolve (behaviour-preserving for readout channels, which reach the same result via `intercept_key is None` today). The resolver already re-applies the candidate's own qualifier, so `>32` stays `>32`.
- `application/research_organization/add_results_from_runs.py:306-313` — after `fetch_candidates_for_runs`, when `cfg.source_kind == DOSE_RESPONSE_CURVE`: fetch `fetch_endpoint_candidates_for_runs(...)` for the same runs/definition and, for each molecule with no curve candidates, use its endpoint candidates. Molecules with curves keep curves (even if `allowed_curve_classes` then drops them — a measurement wins).
- `application/research_organization/get_published_campaign.py::_serialize_measurement` (422-432) — `source` gains `"curve_id": str(m.source_curve_id) if m.source_curve_id else None` and `"readout_id": …` (D8).
- `backend/tests/api/fixtures/daikon_contract.schema.json:253-267` — add `curve_id` and `readout_id` as `{"type": ["string", "null"]}` under `source.properties` (`additionalProperties` is false there).

**Tests**
- `backend/tests/unit/application/research_organization/test_channel_resolver.py` — extend `_FakeQuery` with `fetch_endpoint_candidates` (returns a configurable list) and add: (a) DR channel, no curves, one endpoint row `>32` → measurement value 32, qualifier GT, `source_readout_id` set, `source_curve_id` None; (b) DR channel with one curve failing QC and one endpoint → endpoint wins; (c) DR channel with a QC-passing inactive curve and an endpoint → ND (curve wins); (d) DR channel with an intercept key and an endpoint row → value resolves (regression for `resolve_intercept`).
- `backend/tests/unit/application/screening/test_run_aggregation.py` (or wherever `resolve_intercept` is tested; create if absent) — readout candidate with `intercept_key` set → `(value, EQ)`.
- `backend/tests/integration/research_organization/test_channel_resolution_query.py` — `fetch_endpoint_candidates` on a DR channel returns the well-less raw row and ignores computed/normalised rows; `fetch_endpoint_candidates_for_runs` respects `run_ids`; `fetch_candidates_for_runs` DR branch unchanged.
- `backend/tests/unit/application/research_organization/test_add_results_from_runs.py` — DR config, molecule with only an endpoint row → cell added from the endpoint; molecule with a curve → curve, endpoint ignored.
- `backend/tests/api/test_campaign_published_contract.py` — passes with the two new `source` keys.

**Interfaces produced**
- `ChannelResolutionQuery.fetch_endpoint_candidates(...)`, `fetch_endpoint_candidates_for_runs(...)` (both on the port and the SQLAlchemy implementation).

**Commit:** `feat(campaigns): dose-response channels fall back to reported endpoint rows when no curve survives QC`

---

### Task 4: Compound page, search, and the "reported" markers (ask 1, display side)

**Modify (backend)**
- `application/screening/molecule_activity_service.py:406-416` — before the per-molecule loop, collect `missing: dict[rd_id, list[molecule_id]]` for DR specs with no curves; one call per rd_id `await self._readout_repo.find_aggregated_by_molecules(workspace_id, mols, [(rd_id, None)])`; in the loop, when `curves` is empty and the aggregate exists, emit `ActivityValue(value=agg.value, qualifier=agg.qualifier, unit=agg.unit, source="readout", data_point_count=agg.data_point_count)` under `f"drc:{rd_id}"`. Check `domain/screening_assay/activity_types.py::ActivityValue` for required fields and how `_build_dr_activity` fills the curve-only ones (leave them None).
- `docs/backlog/drc-sort-curves-only.md` (new, `git add -f`): sort by a `drc:` column (`chemical_registration/molecule_reader.py:410` `drc_best` subquery) still ranks curves only; reported endpoints sort as missing. Fix = union the raw-layer rows into the subquery.

**Modify (frontend)**
- `frontend/src/features/screen-campaign/components/grid/results-grid.tsx` — where `CompoundValueCell` is rendered (line ~421) the channel is in scope (`isDR` at 348). Pass `reported={isDR && !!m.source_readout_id && !m.source_curve_id}`; in `CompoundValueCell` (132-…) render a small muted "reported" chip on the marker line with `title="Reported endpoint — no fitted curve for this compound"`. Keep the chip on the second line like the verdict chip so the 120px column does not clip.
- `frontend/src/features/research-organization/components/search/results-grid.tsx` — the `drc:` column cell: when `activity.source === "readout"`, render the same "reported" chip. The hand-written `ActivityValue.source` union in `frontend/src/features/research-organization/types/index.ts:494` already includes `"readout"`.
- `frontend/src/features/chemical-registration/components/detail-tabs/activity-tab.tsx` — the dose-response rows: same chip when `source === "readout"`.

**Tests**
- `backend/tests/unit/application/screening/test_molecule_activity_service.py` (extend or create next to the existing service tests): DR spec, molecule without curves but with a raw-layer aggregate → `drc:` entry with `source="readout"`; molecule with curves → unchanged.
- `frontend/src/features/screen-campaign/components/grid/results-grid.test.tsx` (create if absent, following `notes-cell.test.tsx`): a DR measurement with `source_readout_id` and no `source_curve_id` shows "reported"; one with `source_curve_id` does not.

**Commit:** `feat(activity): compound page and search fall back to reported endpoints for dose-response columns; reported markers`

---

### Task 5: Whole-branch verification and hand-off

- Run: `cd backend && uv run pytest tests/unit -q`, then `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration tests/api -q`, then `uv run ruff check src tests && uv run ruff format --check src tests`.
- Run: `cd frontend && pnpm vitest run && pnpm exec biome check src && pnpm exec tsc --noEmit -p .` — verify by exit code.
- Pre-existing failures: compare against `docs/backlog/pre-existing-test-failures.md` and `preexisting-test-lint-failures-main.md`; anything new is ours.
- One whole-branch review (superpowers:requesting-code-review), fix findings, push, open the PR against `main` referencing #74 with the spec §3 summary and the two new 409/422 behaviours called out.
