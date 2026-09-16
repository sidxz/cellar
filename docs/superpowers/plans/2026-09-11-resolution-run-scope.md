# Resolution honours the campaign's runs (batch 3) — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Lean plan by user ruling: files, interfaces, tests. No per-task reviews; one whole-branch review at the end.

**Goal:** Every campaign resolver path restricts candidates to the runs the campaign was seeded from, so reopen-then-refresh cannot pull a newer run's value into an old campaign; a per-readout opt-out keeps today's protocol-wide behaviour for readouts that want it.

**Architecture:** One helper derives the run set from per-row `added_from` refs; the query port and resolver gain an optional `run_ids`; nine call sites pass it; one new boolean column on the channel (migration 078) with DTOs and a checkbox in the channel form.

**Spec:** `docs/superpowers/specs/2026-09-11-hit-stages-followups-design.md` §5 (D4). Issue sidxz/cellar#76. Branch `feat/resolution-run-scope` from `main` (after PR for #75).

## Global constraints

- Read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md` before backend code.
- Backend tests: `cd backend && uv run pytest tests/unit/... -q`; `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/... tests/api/... -q`. Lint: `cd backend && uv run ruff check src && uv run ruff format src`.
- Frontend checks: `cd frontend && pnpm vitest run src/features/screen-campaign && pnpm exec biome check src/features && pnpm exec tsc --noEmit -p .`.
- Migration `078_campaign_channel_resolve_from_all_runs` revises `077_campaign_stage_kind`; apply to the dev DB (`cd backend && uv run alembic upgrade head`).
- Orval regen after the backend task (`cd frontend && pnpm generate:api`, revert version-stamp churn). No hand-written TS types mirroring DTOs.
- Explicit-pathspec commits; unrelated user edits (`frontend/next-env.d.ts`, `frontend/AGENTS.md`) stay out. No `Claude-Session` trailer; keep `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- D4 exactly: run set = union of `RunRef.run_id` over every result's `added_from`; empty set → unrestricted (`None`); `resolve_from_all_runs=True` on a channel → unrestricted for that channel; rows added manually or from a collection in a run-seeded campaign are restricted too.
- `add_results_from_runs` (and its preview) are already run-scoped and are NOT changed.

Paths relative to `backend/src/cellar/` unless prefixed `backend/tests/`, `backend/alembic/`, or `frontend/`.

---

### Task 1: Run-scoped resolution with a per-channel opt-out (backend)

**Modify — domain**
- `domain/research_organization/campaign.py` — add:
  ```python
  def source_run_ids(self) -> set[uuid.UUID]:
      """Runs this campaign was seeded from: the RunRef run ids over every
      result's added_from. Empty for a campaign seeded only by hand, from a
      collection, or from another campaign — such a campaign resolves
      protocol-wide until its first add-from-runs, after which it narrows
      to those runs (spec D4)."""
      return {r.added_from.run_id for r in self.results if isinstance(r.added_from, RunRef)}
  ```
- `domain/research_organization/campaign_channel.py::CampaignChannel` (:25-58) — `resolve_from_all_runs: bool = False` after `intercept_key`, docstring: opt-out of the campaign's run scope (a counter-screen measured whenever).

**Modify — persistence**
- `models.py::CampaignChannelModel` (~:218-250) — `resolve_from_all_runs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.false())` (use the module's existing `text("false")`/`false()` style).
- `campaign_repository.py::_channel_to_domain` (:172) / `_channel_to_model` (:191) and the channel reconcile in `_update_model` (~:130-140, where `label`/`selection_rule`/`qc_filter`/`display_order` are copied onto an existing channel model) — map the flag.
- `backend/alembic/versions/078_campaign_channel_resolve_from_all_runs.py` — `revision = "078_campaign_channel_resolve_from_all_runs"`, `down_revision = "077_campaign_stage_kind"`; upgrade adds the boolean column with `server_default=sa.false()`, downgrade drops it. Docstring in the 076/077 style. Apply to the dev DB.

**Modify — resolution**
- `application/research_organization/channel_resolution.py`:
  - Port `ChannelResolutionQuery.fetch_candidates(..., run_ids: list[uuid.UUID] | None = None)` and `fetch_endpoint_candidates(..., run_ids: list[uuid.UUID] | None = None)`; docstrings: `None` = every run of the protocol.
  - `ChannelResolver.resolve(..., run_ids: list[uuid.UUID] | None = None)` — pass `run_ids` to both `fetch_candidates` and the D1 endpoint fallback (`:212`).
  - Module helper:
    ```python
    def resolution_run_ids(campaign: Campaign, channel: CampaignChannel) -> list[uuid.UUID] | None:
        """Run scope for resolving one channel of a campaign (spec D4): None when
        the channel opts out or the campaign has no run sources; else the sorted
        source run ids."""
        if channel.resolve_from_all_runs:
            return None
        ids = campaign.source_run_ids()
        return sorted(ids) if ids else None
    ```
- `infrastructure/persistence/sqlalchemy/research_organization/channel_resolution_query.py` — `fetch_candidates` (:175), `_fetch_curve_candidates` (:188, WHERE at :223), `fetch_endpoint_candidates` (:401, WHERE at ~:428): thread `run_ids` and add `.where(<Model>.run_id.in_(run_ids))` when it is not `None`. `fetch_candidates_for_runs` / `fetch_endpoint_candidates_for_runs` unchanged.
- The nine call sites, each `run_ids=resolution_run_ids(campaign, channel)` (the campaign and channel are in scope at every one; check the local variable names): `add_campaign_channel.py:124`, `add_results_from_campaign.py:141`, `add_result_row.py:104`, `add_results_from_collection.py:133`, `close_campaign.py:107`, `mirror_protocol_channels.py:298`, `refresh_campaign_from_sources.py:102`, `recompute_channel.py:108`, `update_campaign_channel.py:146`. (`bulk_add_to_collection.py` and `collection_membership.py` use a different resolver — leave them.)

**Modify — application and interface**
- `add_campaign_channel.py::AddCampaignChannelCommand` — `resolve_from_all_runs: bool = False` into `CampaignChannel(...)`. `update_campaign_channel.py::UpdateCampaignChannelCommand` — `resolve_from_all_runs: bool | object = UNSET`, applied to the channel like `label`; when it changes, the use case's existing re-resolve loop (the one at :146) already recomputes every cell of that channel — confirm and keep.
- `interface/routes/_campaign_dtos.py` — `AddChannelRequest.resolve_from_all_runs: bool = False`; `UpdateChannelRequest.resolve_from_all_runs: bool | None = None` (omitted = unchanged, via `model_fields_set`); `CampaignChannelResponse.resolve_from_all_runs: bool`. Routes in `campaigns_channels.py` thread both.
- `get_published_campaign.py` channel serializer — add `resolve_from_all_runs`; contract fixture: add the boolean to `channels[].properties` (required if the fixture requires the other channel keys).

**Tests**
- `backend/tests/unit/domain/research_organization/test_campaign.py` — `source_run_ids()`: empty for manual/collection/campaign refs; union over run refs; mixed rows.
- `backend/tests/unit/domain/research_organization/test_campaign_channel.py` — default False round-trips through the constructor.
- `backend/tests/unit/application/research_organization/test_channel_resolver.py` — `_FakeQuery` records `run_ids`; `resolve(run_ids=[...])` forwards it to both fetches; `resolution_run_ids` unit cases (opt-out → None; empty → None; sorted ids).
- `backend/tests/integration/research_organization/test_channel_resolution_query.py` — `fetch_candidates(run_ids=[r1])` excludes a curve from r2 (DR branch) and a readout row from r2 (readout branch); `fetch_endpoint_candidates(run_ids=...)` likewise; `None` keeps both.
- One unit case per use case (`test_refresh_campaign_from_sources.py`, `test_close_campaign.py`, `test_add_campaign_channel.py`, `test_update_campaign_channel.py`, `test_recompute_channel.py`, `test_mirror_protocol_channels.py`, `test_add_results_from_campaign.py`, `test_add_results_from_collection.py`, `test_add_result_row.py` — create where absent): the fake resolver asserts it received `run_ids` equal to the campaign's source runs, and `None` when the channel opts out.
- `backend/tests/integration/application/research_organization/test_close_campaign.py` — seed via add-from-runs on run A, add a newer run B of the same protocol with a different value, reopen, refresh: the cell keeps run A's value; flip the channel to `resolve_from_all_runs` and refresh: it takes run B's.
- `backend/tests/api/test_campaigns_api.py` — `POST/PATCH …/channels` with the flag; response carries it. `test_campaign_published_contract.py` passes.
- `backend/tests/integration/research_organization/test_campaign_repository.py` — flag round-trips.

**Interfaces produced**
- `Campaign.source_run_ids()`, `CampaignChannel.resolve_from_all_runs`, `resolution_run_ids(campaign, channel)`, `ChannelResolver.resolve(run_ids=)`, `fetch_candidates(run_ids=)`, `fetch_endpoint_candidates(run_ids=)`, `AddChannelRequest.resolve_from_all_runs`, `UpdateChannelRequest.resolve_from_all_runs`, `CampaignChannelResponse.resolve_from_all_runs`.

**Commit:** `feat(campaigns): resolution honours the campaign's source runs, with a per-readout opt-out`

---

### Task 2: Channel form opt-out and marker (frontend)

- `cd frontend && pnpm generate:api`; revert version-stamp churn; commit `chore(frontend): regen API types for channel run scope`.
- `frontend/src/features/screen-campaign/components/channel-popover.tsx` — schema gains `resolve_from_all_runs: z.boolean()` (default false / existing value); a `Checkbox` row "Resolve from all runs of the protocol" with helper text "Off: only the runs this campaign was seeded from." under the QC fields; sent on both add and update.
- `frontend/src/features/screen-campaign/components/sections/channels-section.tsx` — a small muted "all runs" marker on rows with the flag.
- Tests: `components/sections/channels-section.test.tsx` — marker shown when set; a form test (create if absent) that the checkbox value is sent.

**Commit:** `feat(screen-campaign): per-readout "resolve from all runs" opt-out`

---

### Task 3: Whole-branch verification and hand-off

- Full backend and frontend suites as in Global constraints; dev DB at 078.
- One whole-branch review, one fix wave, one scoped re-review; push; PR against `main` referencing #76 with the D4 note (rows added by hand or from a collection into a run-seeded campaign are restricted too; the channel checkbox is the escape); merge per the owner's instruction; report hashes to the consumer session.
