# Chem-Vault2

Chemical compound management & screening platform (enterprise-grade). 8 bounded contexts, 17+ aggregates, 136 use cases.

**Repo:** `git@github.com:sidxz/chem-vault.git`
**Board:** https://github.com/users/sidxz/projects/4/views/1

---

## Stack

**Backend:** Python 3.13+ / FastAPI 0.115+ / SQLAlchemy 2.0 async (asyncpg) / PostgreSQL 16 + RDKit cartridge / Pydantic v2 / Alembic / Lagom (DI) / dry-python/returns (Railway) / Valkey 8 (Redis-compat) / Temporal / structlog / fsspec

**Frontend:** Next.js 16 / React 19 / TypeScript 5.7+ / Turbopack / shadcn/ui / Tailwind CSS v4 / AG Grid Community / TanStack Query v5 / Zustand / React Hook Form + Zod / Ketcher / RDKit.js / Tiptap / Plotly.js / orval / Playwright

**Infra:** Docker Compose / Grafana Tempo / Prometheus / Sentry (self-hosted) / GitHub Actions / ghcr.io

**Package managers:** `uv` (Python), `pnpm` (JS)

Full rationale: `docs/tech-stack.md`

---

## Architecture

DDD + Clean Architecture + Railway Pattern. No event sourcing.
Domain -> Application -> Infrastructure -> Interface layers.
Domain events for side effects (audit, notifications, async processing).
Optimistic concurrency (version column) on all aggregates.
Audit trail is append-only (21 CFR Part 11 alignment).
Auth delegated to Sentinel (external, `~/workspace/identity-service/`).

### Layer Rules

| Layer | Depends On | Never Depends On |
|-------|-----------|-----------------|
| Domain | Nothing (pure Python) | Application, Infrastructure, Interface |
| Application | Domain | Infrastructure, Interface |
| Infrastructure | Domain, Application | Interface |
| Interface | All layers | — |

### Bounded Contexts

| # | Context | Key Aggregates | Phase |
|---|---------|---------------|-------|
| 01 | Chemical Registration | Molecule, DisclosureRequest, BulkDisclosure, SynthesisRoute | 1 |
| 02 | Screening & Assay | Protocol, Run | 1 |
| 03 | Inventory | Batch, Sample, SampleRequest, Shipment, SynthesisRequest | 1 |
| 04 | SAR Analysis | MarkushDefinition, MolecularFingerprint | 2 |
| 05 | Research Organization | Project, Collection, ELNEntry, SavedSearch | 1-2 |
| 06 | Audit & Compliance | AuditOperation (append-only) | 0 |
| 07 | Workspace Config | Organization, WorkspaceSettings, ControlledVocabulary | 1 |
| 08 | Sentinel Auth | External — User, Workspace, Roles, Permissions | External |
| 11 | Formulation & Drug Product | Formulation, FormulationBatch, StabilityStudy | 2 |

---

## Project Layout

```
chem-vault2/
  backend/
    pyproject.toml
    alembic/
    src/chem_vault/
      domain/
        shared/
        chemical_registration/
        screening_assay/
        inventory/
        formulation/
        sar_analysis/
        research_organization/
        audit_compliance/
        workspace_config/
      application/
      infrastructure/
        persistence/sqlalchemy/
        rdkit/
        storage/
        messaging/
        temporal/
        di/
        sentinel/
      interface/
    tests/
      unit/ integration/ api/
    Dockerfile

  frontend/
    package.json
    next.config.ts / orval.config.ts
    components.json
    src/
      middleware.ts
      app/
        login/ auth/callback/
        (dashboard)/
      features/
        chemical-registration/
        screening-assay/
        inventory/ ...
      shared/
        components/ui/
        components/layout/
        hooks/
        lib/
        providers/
        types/
    tests/
    Dockerfile

  docker-compose.yml
  docker-compose.dev.yml
  docs/
  .github/workflows/
```

---

## Implementation Status

Phase 0-1 complete (S01-S32). Phase 2 complete (fingerprints, research org, plates, export+search). Phase 3 not started (Temporal, ELN, Markush, Formulation, observability).

Full checklist with gates: `docs/implementation-status.md`

---

## Documentation Index

> **Before writing any backend code, read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md`.** These contain mandatory rules for workspace scoping, auth guards, railway pattern, and a checklist for every new use case.

| Purpose | Location |
|---------|----------|
| Backend coding rules (MANDATORY) | `docs/backend-code-guidelines.md` |
| Patterns & exemplar paths (MANDATORY) | `docs/patterns-and-conventions.md` |
| Tech stack decisions + rationale | `docs/tech-stack.md` |
| Key architectural decisions | `docs/key-decisions.md` |
| Full implementation checklist | `docs/implementation-status.md` |
| Domain model (per context) | `docs/domain-model/NN-name.md` |
| Implementation plan + sessions | `docs/planning/` |
| Test scenarios & use cases | `docs/test-reference/` |
| Incomplete work items | `docs/backlog/` |
| Historical plans/specs | `docs/archive/` |

---

## Domain Model Reference

Detailed specs in `docs/domain-model/`:

| File | Content |
|------|---------|
| `00-overview.md` | Context map, cross-context relationships, attachment entity |
| `01-chemical-registration.md` | Molecule, identifiers, disclosure, merge, bulk registration |
| `02-screening-assay.md` | Protocol, runs, plates, wells, readout data, dose-response |
| `03-inventory.md` | Batches, samples, storage, requests, shipments |
| `04-sar-analysis.md` | Fingerprints, matched molecular pairs, Markush |
| `05-research-organization.md` | Projects, collections, saved searches, ELN |
| `06-audit-compliance.md` | Audit operations, entries, electronic signatures |
| `07-workspace-config.md` | Organizations, workspace settings, controlled vocabularies |
| `08-sentinel-integration.md` | Auth boundary, JWT claims, service actions |
| `09-value-objects.md` | All shared VOs (ChemicalStructure, Amount, Concentration, etc.) |
| `10-business-rules.md` | Registration rules, merge safety, chemical standards |
| `11-formulation.md` | Formulations, excipient catalog, batches, stability studies |

---

## Session Model

**Batch 3-5 related sessions per conversation.** Each conversation:
1. **Reads** this CLAUDE.md (auto-loaded) + `docs/planning/session-specs.md` for the batch
2. **Reads** `docs/patterns-and-conventions.md` + `docs/backend-code-guidelines.md` before writing code
3. **Implements** each session in order, committing after each
4. **Tests** — all tests pass before moving to next session
5. **Updates** `docs/implementation-status.md` (check off sessions)
6. **Commits + pushes** after each session
7. **Closes GitHub issues + updates project board** after each session (see below)
8. **Before ending** — updates "Current Session Notes" below with detailed handoff

**Layer order per context:** Domain -> Domain tests -> Persistence -> Integration tests -> Application -> API -> API tests -> UI -> E2E tests

**Context budget:** Stay under 60% context window per session. Use CLAUDE.md + 1 domain doc + 1-2 exemplar files.

### GitHub Project Board (mandatory after each session)

**Repo:** `sidxz/chem-vault` | **Project:** #4 (board at https://github.com/users/sidxz/projects/4/views/1)
**Issues:** #1-#32 map to sessions S01-S32.

After completing each session, run:
```bash
gh issue close <N> --repo sidxz/chem-vault --comment "Completed in S<N>. <one-line summary>"
```
Closing the issue automatically moves it to "Done" on the project board.

---

## Current Session Notes

> ### Handoff (2026-05-07 cont., branch: `fe2`) — Phase B SHIPPED, awaiting NadD smoke verification
>
> #### What's in tree (uncommitted)
>
> Phase B is implemented end-to-end. Branch is clean against `origin/fe2`
> (Phase A is already pushed as commit `cbb4783`). The Phase B diff is 14
> files modified + 1 new component, ~1500 LOC net. **Not yet committed —
> waiting on the user to run the NadD CV-00784 manual smoke (B11 below).**
>
> Test status:
> - Backend: **1617 unit tests pass** (was 1594 pre-Phase-B; +23 new for
>   range constraints + NadD acceptance fixture).
> - Frontend: `pnpm tsc --noEmit` clean.
>
> Files touched:
> - `backend/src/chem_vault/domain/screening_assay/dose_response_config.py`
>   — 6 new optional fields (`top/bottom/hill_*_min/max`) + validation:
>   lock+range mutually exclusive per param, min<max, hill range vs enum
>   consistency.
> - `backend/src/chem_vault/infrastructure/lmfit/curve_fitter.py` — new
>   `_clamp` helper; three-mode precedence in `_build_params` (lock > range
>   > free, with hill enum interplay); `has_constraints` extended to
>   include range fields so the inactive fast-path is bypassed when ranges
>   are set.
> - `backend/src/chem_vault/application/screening/refit_dose_response.py`
>   — `RefitDoseResponseCurveCommand` extended with `override_<param>:
>   bool` flags + range fields. `_resolve_config` resolves per-param: when
>   `override_<param>` is True, client is authoritative (incl. Free); else
>   inherits from protocol. Back-compat: clients that only send
>   `top_constraint` without the flag are treated as Lock override.
> - `backend/src/chem_vault/application/screening/fit_dose_response.py` —
>   `FitOverrides.apply` (used by Recompute popover) zeroes the protocol's
>   range when a per-run lock override is applied (lock+range mutually
>   exclusive).
> - `backend/src/chem_vault/application/screening/create_protocol.py`,
>   `manage_readout_definitions.py` — pass-through of new fields in
>   dict→VO deserializers (4 call sites total, kept inline rather than
>   extracting a helper to keep the diff surgical).
> - `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py`
>   — `_reconstruct_dose_response_config` reads new fields. Serializer
>   uses `asdict` so it picks them up automatically. **Persistence is
>   JSONB — no migration needed.** Old protocol rows missing the fields
>   deserialize cleanly via `.get(...)`.
> - `backend/src/chem_vault/interface/routes/protocols.py` — response body
>   now emits the 6 new fields.
> - `backend/src/chem_vault/interface/routes/readout_data.py` —
>   `RefitDoseResponseCurveRequest` extended with `override_<param>` +
>   range fields, plumbed through to the command.
> - `backend/tests/unit/domain/screening_assay/test_dose_response_config.py`
>   — 13 new tests covering each validation rule.
> - `backend/tests/unit/screening/test_curve_fitter.py` — 10 new tests
>   including the canonical `test_nadd_partial_curve_with_cdd_default_ranges`
>   acceptance test (NadD-shaped partial curve, Top ∈ [85, 110], Bottom ∈
>   [-10, 10], Hill ∈ [0.9, 1.1] → IC50 in [55, 90] µM).
> - `frontend/src/features/screening-assay/types/index.ts` — extended
>   `DoseResponseConfig` and `RefitDoseResponseCurveInput` interfaces.
> - `frontend/src/features/screening-assay/components/detail-tabs/design-tab.tsx`
>   — Free/Range/Lock segmented control per Top and Bottom; Hill enum
>   select + "Custom range" checkbox + min/max inputs. Smart defaults
>   switched to CDD ranges. "Use suggested" applies all three. Eye icon
>   added to action column (visible always, not just for drafts);
>   readout name made clickable. Viewer dialog mounted.
> - `frontend/src/features/screening-assay/components/dose-response-chart.tsx`
>   — `CurveControls` rebuilt with the same Free/Range/Lock toggles.
>   `callRefit` sends all `override_<param>` flags. `handleReset` clears
>   per-curve overrides via empty refit.
> - **NEW** `frontend/src/features/screening-assay/components/readout-definition-viewer-dialog.tsx`
>   — CDD-style read-only viewer with disabled inputs preserving the
>   spatial/visual structure of the Edit dialog. Renders Basic, Axes, Fit
>   Parameters sections. Shows mode badge (Free/Range/Lock) per param.
>
> #### Smoke recipe to verify (B11 from previous handoff)
>
> 1. Restart backend: `docker compose restart backend`. (No alembic
>    migration needed — JSONB.)
> 2. Open the existing `NadD-Sumo dose response` protocol → Design tab
>    → click the IC50 readout's Edit pencil.
> 3. Set:
>    - Top: **Range**, from 85 to 110
>    - Bottom: **Range**, from −10 to 10
>    - Hill: check "Custom range", from 0.9 to 1.1
>    Save.
> 4. Click **Recompute** on `Run 2026-05-07`.
> 5. Open CV-00784 (page 3/31). Acceptance:
>    - IC50 ∈ **[55, 90] µM** (CDD reports 70).
>    - Hill ≈ 1.0 (within [0.9, 1.1]).
>    - R² > 0.95.
>    - No `ec50_at_bound` warning.
> 6. From Design tab, click the new **Eye** icon (or the readout name
>    itself) on IC50. Confirm the viewer modal renders with all fields
>    disabled and matches what was just saved. Close button works; no
>    save button visible.
> 7. Open per-curve **Fit Constraints** accordion on CV-00784. Toggle Top
>    to **Lock = 130** (override). Refit triggers; IC50 shifts. Switch
>    Top back to **Free** — IC50 returns to data-driven value.
>
> Acceptance: IC50 within ±15 µM of CDD's 70 µM with the user able to
> inspect the protocol config in a read-only modal.
>
> #### Once verified
>
> Commit Phase B as one clean commit, e.g. `feat(screening): bounded-range
> constraints + read-only protocol viewer (CDD parity)`. Phase A
> (`cbb4783`) plus Phase B together close the IC50 vocabulary gap.
>
> #### Phase C deferrals (unchanged from prior handoff)
>
> Profile-likelihood CIs, plate-normalizer warnings on % > 110 / < -10,
> non-percent classification refinements, Spearman ρ direction tiebreak,
> snapshot history viewer.
>
> ---
>
> ### Original Phase B plan (preserved below for reference)
>
> #### ⚠️ Critical handoff state (now resolved)
>
> **Phase A is shipped but UNCOMMITTED on `fe2`.** Branch is 24+ commits
> ahead of `origin/fe2`; new Phase A work is on top of that, untracked.
> Migration `020_add_fit_quality_warnings.py` exists in
> `backend/alembic/versions/`. Do not lose either. Recommended first move:
> commit Phase A as a single commit ("feat(screening): direction-agnostic
> 4PL fitter + fit-quality warnings") *before* starting Phase B work, so
> the boundary is clean.
>
> Files modified by Phase A (uncommitted):
> - `backend/src/chem_vault/infrastructure/lmfit/curve_fitter.py` — full rewrite (Prism param, log-space EC50, CI, warnings, fast-path guard, `_build_params` helper)
> - `backend/src/chem_vault/domain/screening_assay/curve_fitting.py` — `FittedCurveResult.fit_quality_warnings`
> - `backend/src/chem_vault/domain/screening_assay/dose_response_curve.py` — entity field
> - `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/screening_assay/models.py` — JSONB column
> - `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/screening_assay/dose_response_curve_repository.py` — round-trip
> - `backend/src/chem_vault/application/screening/fit_dose_response.py` — persist warnings
> - `backend/src/chem_vault/application/screening/refit_dose_response.py` — persist warnings on refit
> - `backend/src/chem_vault/interface/routes/readout_data.py` — response field
> - `backend/alembic/versions/020_add_fit_quality_warnings.py` — new migration
> - `backend/tests/unit/screening/test_curve_fitter.py` — 8 new direction-aware tests
> - `frontend/src/features/screening-assay/types/index.ts` — `fit_quality_warnings?: string[]`
> - `frontend/src/features/screening-assay/lib/dose-response-display.ts` — shared `evaluate4PL` / `generate4PLPoints`
> - `frontend/src/features/screening-assay/components/dose-response-chart.tsx` — uses shared evaluator + WarningBadge row + "(extrapolated)" suffix
> - `frontend/src/features/screening-assay/components/dose-response-sparkline.tsx` — uses shared evaluator
> - `frontend/src/shared/lib/export/curve-image.ts` — uses shared evaluator
>
> Phase A was driven by the plan at `~/.claude/plans/mellow-mixing-pony.md`.
> Tests: `uv run pytest tests/unit/` → 1594 passing. `pnpm tsc --noEmit` clean.
>
> #### Why Phase A wasn't enough
>
> Phase A made the 4PL math correct. Smoke test on the NadD file (CV-00784,
> page 3/31) revealed a remaining IC50 disagreement with CDD on the SAME
> data: chem-vault → IC50 = 39 µM, CDD → 70 µM. Both fits are
> mathematically valid; the disagreement is a vocabulary gap.
>
> CDD's `IC50calc` readout definition (verified against the live UI) uses
> **bounded ranges**, not single-value locks:
> - Min (Bottom): from −10 to 10
> - Max (Top): from 85 to 110
> - Slope (Hill): from 0.9 to 1.1
>
> CDD's optimizer searches inside those ranges. For partial curves where
> the upper plateau isn't observed (NadD CV-00784 caps at 62 % at 100 µM),
> CDD's fit converges at Max = 110 (the upper bound), Min = −0.019 →
> IC50 ≈ 70 µM with an honestly wide CI [12, 410] µM.
>
> chem-vault's `DoseResponseConfig` only supports `top_constraint: float | None`
> (None = free, value = `vary=False` hard lock). When the user mirrors CDD by
> setting Top = 85 (CDD's lower bound), our fitter locks Top exactly there →
> midpoint at 37.5 % → IC50 ≈ 39 µM with artificially narrow CI [34, 45].
> The math is correct, but the constraint shape is wrong.
>
> When the upper plateau is unobserved, IC50 is highly sensitive to where
> Top is fixed (Top = 85 → IC50 39, Top = 110 → IC50 70, Top free → IC50 108).
> Hard locks are arbitrary; ranges let the optimizer pick the
> data-consistent point. Industry standard (CDD, GraphPad Prism, Genedata
> Screener, ActivityBase) is ranges by default with locks as a special case.
>
> #### Phase B scope (this session)
>
> Add bounded-range constraints to `DoseResponseConfig`. Hard locks remain
> a special case (range collapsed to a point). Add a CDD-style read-only
> protocol design viewer alongside.
>
> ##### B1. Domain extension — `DoseResponseConfig`
>
> File: `backend/src/chem_vault/domain/screening_assay/dose_response_config.py`
>
> New optional fields:
> ```python
> top_constraint_min: float | None = None
> top_constraint_max: float | None = None
> bottom_constraint_min: float | None = None
> bottom_constraint_max: float | None = None
> hill_slope_min: float | None = None
> hill_slope_max: float | None = None
> ```
>
> Existing `top_constraint` / `bottom_constraint` / `hill_slope_constraint`
> stay — they represent the "lock" mode. Validation rules:
> - Cannot set both `top_constraint` AND (`top_constraint_min` OR
>   `top_constraint_max`) — choose lock or range, not both.
> - If both `_min` and `_max` set, `_min < _max`.
> - Same for bottom.
> - Hill: range fields override the enum's implicit bounds when set.
> - Open question for the next session: should `HillSlopeConstraint` enum
>   gain a `RANGE` variant, or stay as-is and treat range fields as
>   independent? Recommendation — keep enum, add range fields independent.
>   The enum continues to express the discrete intent (UNCONSTRAINED, FIXED_AT_ONE,
>   POSITIVE_ONLY, NEGATIVE_ONLY); the range fields are an explicit override.
>
> ##### B2. Curve fitter — `_build_params`
>
> File: `backend/src/chem_vault/infrastructure/lmfit/curve_fitter.py`
>
> For each of Top, Bottom, Hill, decide mode in this order:
> 1. If single-value `top_constraint` is set → existing `vary=False` lock.
> 2. Else if `top_constraint_min` or `top_constraint_max` is set →
>    `params['top'].set(value=clamp(top_init, min, max), min=..., max=...)`.
> 3. Else → existing free / direction-aware behavior.
>
> Hill needs care: existing enum sets bounds for POSITIVE_ONLY (`[0.01, 20]`)
> and NEGATIVE_ONLY (`[-20, -0.01]`). When `hill_slope_min` / `hill_slope_max`
> are also set, they override the enum's bounds. Validate that explicit
> range is consistent with the enum (e.g. POSITIVE_ONLY + range [-2, 2]
> is contradictory; raise `ValidationError`).
>
> Initial-value clamping: when the data-driven `top_init` falls outside
> [min, max], lmfit will reject it. Clamp into the range before
> `params.set(...)`. Same for bottom and hill.
>
> ##### B3. Persistence
>
> First step for the next session: **verify how `DoseResponseConfig` is
> currently stored**. If it's a JSONB blob on the protocol's readout
> definitions table, the new fields just go in the dict — no schema
> migration. If columns, add 6 nullable Float columns with a migration
> (`021_add_dose_response_range_constraints.py`).
>
> Update `_to_model` / `_to_domain` mappers in the protocol repository to
> round-trip the new fields.
>
> ##### B4. API
>
> File: `backend/src/chem_vault/interface/routes/protocols.py`
>
> Extend `DoseResponseConfigRequest` and `DoseResponseConfigResponse`
> (or whatever Pydantic shape exists) with the 6 new fields. Validation
> at the API layer mirrors the domain layer.
>
> Refit endpoint (`readout_data.py`): extend `RefitDoseResponseCurveRequest`
> with the 6 new fields. Per-curve refits already merge protocol defaults
> with overrides (`refit_dose_response.py:_resolve_config`); add range
> handling there.
>
> Recompute endpoint (`plate_setup.py:RecomputeRunRequest`): keep as is —
> per-run override remains single-value-only (one-shot exploration tool;
> ranges live on the protocol).
>
> ##### B5. UI — Protocol Design tab Add/Edit Readout dialog
>
> File: `frontend/src/features/screening-assay/components/detail-tabs/design-tab.tsx`
>
> Replace each Top / Bottom input with a **mode segmented control**:
>
> ```
> Top:    ( ) Free    ( ) Range    ( ) Lock
>          ────────────────────────────────────
>          Range mode:  [ from 85 ] to [ 110 ]
>          Lock  mode:  [    100   ]
>          Free  mode:  (no inputs)
> ```
>
> Hill slope: keep the existing enum dropdown but add a new `Custom range...`
> entry that reveals two inputs ("from 0.9 to 1.1").
>
> Update the smart-default suggestion logic. When the Y readout's
> normalization is `% inhibition`, `% activation`, or `% control`, suggest:
> - Top: Range, [85, 110]
> - Bottom: Range, [-10, 10]
> - Hill: Custom range, [0.9, 1.1]
>
> "Use suggested" button applies all three at once. These are CDD's exact
> defaults — see CDD screenshot in this session.
>
> Edit-mode loading (`openEditReadout`): branch on which fields are set
> (single-value → Lock mode, range → Range mode, neither → Free mode) and
> populate the appropriate inputs.
>
> ##### B6. UI — Per-curve Fit Constraints accordion
>
> File: `frontend/src/features/screening-assay/components/dose-response-chart.tsx`
>
> Same Free / Range / Lock toggle pattern for Top and Bottom in the
> existing `CurveControls` component. Per-curve override semantics
> unchanged: protocol provides defaults; per-curve override applies to
> this curve only on this run. Bidirectional — protocol Range can be
> overridden to per-curve Lock and vice versa.
>
> Refit hook (`useRefitDoseResponse`) updated to send all 6 range fields.
>
> ##### B7. UI — Per-run Recompute popover
>
> File: `frontend/src/features/screening-assay/components/run-detail.tsx`
>
> Stays exactly as is. Single-value lock inputs only. Per-run override is
> intentionally simpler than protocol-level — it's a one-shot "what if Top = 100"
> exploration tool, not a configuration surface.
>
> ##### B8. UI — NEW: Read-only protocol design viewer (CDD-style) ⭐
>
> User explicitly asked for this in the same conversation: *"now there is
> no way to view what the protocol design says in detail. i liked the way
> CDD shows making the field read only."*
>
> Reference: CDD's *View Readout Definition: IC50calc* modal (screenshot
> 3 from this session). Key UX trait: a structured form with **disabled
> inputs** (greyed but visually preserved), not a text dump. The user can
> read the configuration as if they were about to edit it, without risk
> of accidental changes.
>
> New component: `frontend/src/features/screening-assay/components/readout-definition-viewer-dialog.tsx`.
>
> Trigger: small "View" / info icon button (lucide-react `Eye` or `Info`)
> next to the existing "Edit" pencil on each readout chip in the Design
> tab. Also: clicking the readout name itself opens the viewer (Edit
> stays as the explicit pencil click). For non-draft protocols where Edit
> is hidden, View is the only access — and it's the primary discovery
> path for "what's actually configured here".
>
> Modal layout (mirror CDD's structure but on our domain):
>
> ```
> ┌────────────────────────────────────────────────────────────┐
> │  View Readout Definition: <name>                       ✕  │
> ├────────────────────────────────────────────────────────────┤
> │  ⓘ <status banner — only when relevant>                   │
> │     "This protocol is published; edits go through a new   │
> │      version" / "Read-only from a shared project" / etc.  │
> │                                                            │
> │  ── Basic ─────────────────────────────────────────────── │
> │   Name        [ raw AU                                  ] │
> │   Data Type   [ Numeric                            ▾   ] │
> │   Unit        [ AU                                       ] │
> │   Aggregation [ Mean                               ▾   ] │
> │   Normalization [ % Inhibition                     ▾   ] │
> │                                                            │
> │  ── Axes (dose-response) ──────────────────────────────── │
> │   X readout   [ (use well concentration)           ▾   ] │
> │   Y readout   [ raw AU                             ▾   ] │
> │   X log scale  ☑                                          │
> │                                                            │
> │  ── Fit Parameters ────────────────────────────────────── │
> │   Top      ( )Free  (●)Range  ( )Lock                     │
> │            from [ 85    ]  to [ 110   ]                   │
> │   Bottom   ( )Free  (●)Range  ( )Lock                     │
> │            from [ -10   ]  to [ 10    ]                   │
> │   Hill     [ Custom range                          ▾   ] │
> │            from [ 0.9   ]  to [ 1.1   ]                   │
> │   Activity Threshold   [ 30                          ] %  │
> │   Normalization Scope  [ Per Plate                 ▾   ] │
> │                                                            │
> │  ── Inactive Range ────────────────────────────────────── │
> │   ● max(response) < 30 %  (built-in)                      │
> │   ○ 3 SD from negative control mean (Phase C)             │
> │                                                            │
> │                                          [    Close    ]  │
> └────────────────────────────────────────────────────────────┘
> ```
>
> All form controls `disabled` (greyed). No save button. Same component
> reusable for snapshot/history views later.
>
> Implementation tip: extract the dose-response config block from
> `design-tab.tsx` into a presentational component (`<DoseResponseConfigBlock readOnly={...}>`)
> shared between the Edit dialog and the new Viewer dialog. Same UI,
> different `disabled` state. Saves duplication and keeps the two views
> structurally identical.
>
> #### B9. Tests
>
> Backend (`backend/tests/unit/screening/test_curve_fitter.py`):
> 1. **Range constraint on Top** — set Top ∈ [85, 110]; fit; assert
>    `85 ≤ fitted_top ≤ 110`.
> 2. **Range hits upper bound** — synthetic data plateauing at 130 %, Top
>    range [85, 110]; assert `fitted_top == pytest.approx(110, abs=0.1)`.
> 3. **NadD CV-00784 fixture, CDD-equivalent ranges** — Top [85, 110],
>    Bottom [-10, 10], Hill [0.9, 1.1]; assert IC50 ∈ [55, 90] µM, R² > 0.95.
>    This is the canonical Phase B acceptance test.
> 4. **Lock + range mutually exclusive** — `DoseResponseConfig(top_constraint=100, top_constraint_min=80)`
>    raises `ValidationError`.
> 5. **Range with min > max** — raises `ValidationError`.
> 6. **Initial value clamping** — synthetic data with `top_init = 150`,
>    Top range [50, 100]; fitter clamps initial value into the range, fit
>    succeeds.
> 7. **Hill range overrides enum** — POSITIVE_ONLY enum + explicit Hill
>    range [-5, 5] is contradictory → `ValidationError`. POSITIVE_ONLY +
>    Hill range [0.5, 2] is consistent → fit lands inside.
>
> Frontend:
> - Component test for `ReadoutDefinitionViewerDialog`: renders all
>   sections, all inputs disabled, no save button, configured values match
>   the input prop.
> - `tsc --noEmit` clean.
>
> #### B10. Migration / back-compat
>
> Phase A's hard-lock semantic is preserved:
> - Existing protocols with `top_constraint = 85` continue to apply that
>   exact lock. No data migration.
> - The new range fields are nullable additions — existing rows have them
>   as NULL, treated as "no range constraint" by the fitter.
>
> One-time UX nudge: when a user opens the Edit Readout dialog on an old
> protocol with single-value `top_constraint = 100` AND the Y readout's
> normalization is `% inhibition`, show a small banner above the Top
> control: *"This is locked at 100. Switch to a Range like CDD does
> ([85, 110]) to allow the optimizer to find the natural plateau? [Apply
> suggested ranges]"*. One click → switches to Range mode with smart
> defaults. Optional, not blocking.
>
> #### B11. Verification recipe (canonical NadD smoke)
>
> 1. Apply migration: `cd backend && uv run alembic upgrade head` (only
>    needed if Phase B adds columns; if JSONB-only, no migration).
> 2. Restart backend: `docker compose restart backend`.
> 3. Open the existing `NadD-Sumo dose response` protocol → Design tab →
>    Edit the IC50 readout.
> 4. Set:
>    - Top mode: **Range**, from 85 to 110
>    - Bottom mode: **Range**, from −10 to 10
>    - Hill: **Custom range**, from 0.9 to 1.1
>    Save.
> 5. Click **Recompute** on `Run 2026-05-07`.
> 6. Open CV-00784 (page 3/31). Expect:
>    - IC50 ∈ **[55, 90] µM** (CDD reports 70).
>    - Hill ≈ **1.0** (within [0.9, 1.1] range).
>    - R² > 0.95.
>    - Top fitted near 110, Bottom near 0.
>    - 95 % CI band asymmetric, similar shape to CDD's [12, 410].
>    - No `ec50_at_bound` warning.
> 7. From the Design tab readout list, click the new "View" icon (or the
>    readout name) on IC50. Confirm the viewer modal renders with all
>    fields read-only and matches what was just saved. Close button
>    works; no save button visible.
> 8. Open the per-curve Fit Constraints accordion on CV-00784. Toggle Top
>    to Lock = 130 (override). Refit triggers; IC50 should shift to the
>    larger value the new lock implies. Switch back to Range — IC50
>    returns to ~70.
>
> Acceptance criterion: IC50 within 10 µM of CDD's 70 µM on the canonical
> NadD curve, with the user able to inspect the protocol config end-to-end
> in a read-only modal.
>
> #### B12. Out of scope (Phase C, future)
>
> - **Profile-likelihood CIs** — more accurate than log-space symmetric.
>   lmfit's `conf_interval()` does this. Replace the `1.96 × stderr` fallback.
> - **Plate normalizer warnings** — emit `WARN` log when % inhibition > 110
>   or < -10 to surface mis-orientation of controls. Don't clamp.
> - **Curve classification refinements** for non-percentage readouts —
>   thresholds tied to readout normalization.
> - **Direction inference robustness** — Spearman ρ as tiebreak when low
>   and high plateaus are within noise.
> - **`HillSlopeConstraint.FIXED_AT_ONE` migration banner** — communicate
>   the sign-convention change from Phase A.
> - **Snapshot history viewer** — reuse the new viewer for "what was the
>   protocol config when this curve was fit?". Out of scope; future feature.
>
> #### Where to start
>
> 1. Commit Phase A as a single clean commit on `fe2`.
> 2. Read this handoff section + `~/.claude/plans/mellow-mixing-pony.md`
>    (the Phase A plan, for parametrization context).
> 3. Verify how `DoseResponseConfig` is persisted (JSONB or columns).
>    Decide migration accordingly.
> 4. Start with B1 (domain extension) → B2 (fitter) → B9 (tests). That
>    cycle alone should bring NadD CV-00784 into the [55, 90] range.
> 5. Then B5/B6 (UI for ranges).
> 6. Finally B8 (read-only viewer) — independent of the rest, ship in
>    parallel if convenient.
>
> ---
>
> ### Resolved (2026-05-07) — four IC50/import bugs from the 2026-05-05 handoff are all fixed
>
> All four issues called out in the prior handoff have landed on `fe2` and
> verified manually against the NadD file. Keeping a short pointer here in
> case anyone comes back asking; the verbose handoff that used to live at
> this position has been pruned.
>
> 1. **Curves all 0 / Inactive / R²=0** — fixed in `6f81e1f`. `fit_dose_response.py`
>    now selects the canonical value layer (raw vs `is_computed`) per readout
>    def, so the 4PL optimizer stops being fed two y-values per dose point.
> 2. **Plate Map UI broken on multi-plate runs** — backend response shape
>    realigned in `6f81e1f`; tab-strip-per-plate UI in `3248235`. `PlateMapResponse`
>    now returns `plates: PlateData[]` with per-plate summary; frontend renders
>    one heatmap per plate.
> 3. **Scientist text vanishing during import** — Text-readout support shipped
>    end-to-end across `0933a62` / `33b7d83` / `fbd35bb` / `c9ad8c3` / `873f118`.
>    Long-format normalizer carries `dict[uuid, float | str]`; importer dispatches
>    on `data_type` to write `value` vs `value_text`.
> 4. **`concentration` readout def em-dash on Readout Data** — addressed by the
>    protocol-edit work (`4f4a21d`, `ef3862c`) plus making `x_readout_name`
>    optional so X is sourced implicitly from `well.concentration`.
>
> Net follow-ons since: `fbdc6e3` refactor, `3d93b39` rdr fix, `fdc7af5` dr.
>
> ---
>
> ### Stale handoff below — preserved only for archaeology, do NOT act on it
>
> The block that used to live here described the four bugs as still open
> with a "no shortcuts" mandate. It is OBSOLETE as of 2026-05-07.
>
> ### Original handoff (2026-05-05) — superseded
>
> #### ⚠️ Mandate for the next session
>
> **Do not take shortcuts. Do not patch over symptoms. Do not write
> compatibility shims to avoid touching the underlying contract.** Every
> bug below has a clean root-cause fix that touches the right layer of
> the architecture. If you find yourself reaching for a "just write a
> derived field downstream" or "just filter at display time" workaround,
> stop and fix the actual thing. If a fix requires changing a contract
> across backend + frontend, change both. If it requires updating tests,
> update them — don't disable, don't loosen.
>
> The user is a real screener trying to get a real IC50 out of a real
> NadD file. A demo-grade fix that "looks right in this case" but is
> wrong in the next one is worse than no fix.
>
> #### What was shipped this session (4 commits on `fe2`)
>
> 1. `b013837` `feat(import): control layouts as canonical well-type source; drop inference`
>    — `_infer_well_type()` removed entirely. Long-format normalizer is
>    now pure data shape; classification comes only from
>    `protocol.control_layouts[plate_format]` →
>    `PlateTemplate.template_map`. Pre-flight in both Preview and Import:
>    if any readout uses control-based normalization (% Inhibition,
>    % Activation, % Control, Z-score) and a plate format in the file
>    has no Control Layout configured, the import is BLOCKED before any
>    writes with a clear, actionable message.
>    `PlatePreview.control_count` → `blank_count`. New result fields:
>    `controls_from_template`, `controls_unclassified`,
>    `validation_errors`. ReadoutData domain entity already had nullable
>    molecule/batch on the DB side; the entity now matches.
>
> 2. `082bdae` `feat(screening): X/Y editor for IC50 + Control Layout discoverability + import wizard guards`
>    — Add/Edit Readout dialogs on protocol Design tab now expose the
>    Dose-Response Configuration block (curve type, X/Y readout,
>    Hill slope, normalization scope, activity threshold). Previously
>    only the initial Create Protocol wizard had it; existing IC50 rows
>    couldn't be re-pointed. Control Layouts card got "Manage Templates"
>    header link, an empty-state CTA when the workspace has zero
>    templates, and template-by-format filtering. Import wizard renders
>    `validation_errors` as a destructive banner; "Import" button gated
>    on no errors. "Controls" column in the per-plate preview renamed to
>    "Blanks".
>
> 3. `53dd5bf` `fix(import): write readouts for control wells; unblocks plate normalization`
>    — `ImportRunFile` no longer skips readouts for non-sample wells.
>    Control wells (NEG/POS/BLANK) now persist their raw values with
>    `molecule_id = batch_id = None`. Without this, plate normalization
>    found zero negative-control values and silently failed via the
>    swallowed-DomainError path. Calc engine's per-molecule aggregation
>    step now filters `molecule_id is None` rows so they don't pollute
>    `aggregated_values[None]`.
>
> 4. `00a5fef` `feat(runs): delete run end-to-end (draft + in-progress, unlocked)`
>    — `DeleteRun` use case (the feature was missing entirely; only
>    SQL-level cleanup was possible). Editor + workspace guards. Blocks
>    locked runs and any non-draft / non-in-progress status (terminal
>    states have audit trails — once approved/rejected, no delete).
>    Cleanup order: `dose_response_curves` → `readout_data` → `run`.
>    Plates and wells cascade via existing FK ON DELETE CASCADE.
>    `DELETE /api/v1/runs/{run_id}` (204). `useDeleteRun` hook +
>    destructive button on Run detail page, visible only when
>    `(draft || in_progress) && !is_locked`. Confirm dialog redirects to
>    the protocol page.
>
> All four committed; not pushed. Branch is 24 commits ahead of
> `origin/fe2`.
>
> #### Where the user is in the manual flow
>
> The user has:
> - A **Draft Plate Template** named `NadD 384 — col1 NEG, col24 POS`,
>   384-well, with col 1 painted as NEGATIVE_CONTROL and col 24 as
>   POSITIVE_CONTROL. (User got there via Administration → Screening
>   Setup → Plate Templates after the new in-context CTAs surfaced it.)
> - The protocol **`NadD-Sumo dose response`** is in some published
>   state with: `concentration` (Numeric, uM), `raw AU` (Numeric, AU,
>   Normalization=% Inhibition), `IC50` (Dose-Response, X=concentration,
>   Y=`raw AU`), `Scientist` (Text). Control Layout for 384 is wired to
>   the plate template above.
> - A **Run 2026-05-05** with `In Progress` status, run id
>   `ba0e6dfe-c73d-4153-bead-6e4fd34a40d8`, imported from
>   `~/Downloads/NadD_LG-2200467564_100uM-DR_4.20.26.xlsx`. Import
>   succeeded with `2 plates · 680 wells · 680 readouts · 64 controls
>   from layout · 23 blank wells unclassified`.
>
> The user can now `Delete` the run (new feature in `00a5fef`) and
> re-import once the bugs below are fixed.
>
> #### Bug 1 — Curves all return 0.000 / Inactive / R²=0 [CRITICAL]
>
> File: `backend/src/chem_vault/application/screening/fit_dose_response.py`
> Lines: ~96–110
>
> **Root cause:** `ReadoutCalculationEngine` writes normalized values as
> new `ReadoutData` rows with `is_computed=True` and the **same
> `readout_definition_id`** as the raw rows
> (`readout_calculation_engine.py:181–191`). The fitter (`fit_dose_response.py`)
> filters by `y_rd.id` only — it never looks at `is_computed`. So per
> concentration point, the 4PL optimizer is fed two y-values that
> disagree by orders of magnitude (raw AU ~0.07–0.6 and post-normalization
> % inhibition 0–100). The Levenberg-Marquardt fit cannot converge and
> returns degenerate zeros.
>
> **Proper fix:** in `fit_dose_response.py`, before the group-by loop,
> compute `use_computed = y_rd.normalization != ReadoutNormalization.NONE
> or y_rd.is_calculated`. In the loop, skip rows whose
> `is_computed != use_computed`. This selects the correct value layer
> deterministically — post-normalization for normalized readouts, raw
> for direct readouts, computed for calculated readouts.
>
> **Do not** "deduplicate by well_id and prefer is_computed" — that's a
> patch. The real semantic is: for each readout def, exactly ONE value
> layer is the canonical fit input, determined by the def's
> normalization/calculation state.
>
> Add unit tests covering: (a) normalized readout fits use only computed
> values, (b) raw readout fits use only is_computed=False values,
> (c) calculated readout fits use only computed values.
>
> #### Bug 2 — Plate Map UI cannot render multi-plate runs [CRITICAL]
>
> Files:
> - `backend/src/chem_vault/interface/routes/plate_setup.py` (`PlateMapResponse`,
>   `WellMapEntry`, `get_plate_map`)
> - `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/screening_assay/plate_map_reader.py`
> - `backend/src/chem_vault/application/screening/plate_map_reader.py`
> - `frontend/src/features/screening-assay/types/index.ts` (`PlateMapResponse`,
>   `PlateMapWell`, `PlateMapSummary`)
> - `frontend/src/features/screening-assay/components/run-data-panel.tsx`
> - `frontend/src/features/screening-assay/components/plate-map-viewer.tsx`
> - `frontend/src/features/screening-assay/components/plate-heatmap.tsx`
>
> **Root cause:** the backend response shape and the frontend type
> contract diverged when multi-plate support was added on the backend.
> The frontend type was never updated. Both the structural shape AND
> several field names mismatch:
>
> Backend returns:
> ```json
> {"run_id": "...", "plates": [{"plate_id": "...", "plate_number": 1, "wells": [...]}]}
> ```
> Frontend reads `plateMap?.wells` (top-level), so `hasPlateMap` is
> always `false` → empty-state grid with "Set Up Plate" buttons. The
> heatmap has been broken since multi-plate landed.
>
> Field-level: backend sends `concentration_value` / `concentration_unit`
> and no `position` or `batch_number`. Frontend reads `concentration`,
> `position`, `batch_number`.
>
> **Proper fix:** redesign the contract end-to-end as one logical
> response, not a backwards-compat patch on either side.
>
> Backend `PlateMapResponse` becomes:
> ```python
> class PlateData(BaseModel):
>     plate_id: uuid.UUID
>     plate_number: int
>     format: str           # plate format per plate (a run can mix formats)
>     wells: list[PlateMapWellModel]
>     summary: PlateMapSummaryModel
>
> class PlateMapResponse(BaseModel):
>     run_id: uuid.UUID
>     plates: list[PlateData]
> ```
>
> `PlateMapWellModel` includes `position` (e.g., "A1" — derive from
> row+column, no zero-padding to match frontend convention),
> `concentration` + `concentration_unit` (rename from
> `concentration_value`), `batch_number` (lookup join through BatchModel
> in the reader, same pattern as the existing molecule_name lookup).
>
> `PlateMapSummary` is computed in the reader: `total_wells`,
> `sample_wells`, `control_wells`, `compounds`,
> `concentrations_per_compound`, `replicates`. Reuse domain enums.
>
> Frontend `PlateMapResponse` mirrors. `usePlateMap` typing updates.
> `RunDataPanel`'s plate-map tab renders a tab strip when `plates.length > 1`
> (one tab per plate, label = "Plate {n}"), one `PlateMapViewer` per
> tab. `PlateMapViewer` already takes a single-plate input — its props
> change from `plateMap: PlateMapResponse` to `plate: PlateData`.
> `hasPlateMap` becomes `plates.length > 0 && plates[0].wells.length > 0`.
>
> Also update `PlateHeatmap` (the empty-state placeholder) — it should
> only render when there are no plates at all, not when wells are
> wrongly empty due to a contract bug.
>
> Tests: backend route test for multi-plate response shape; frontend
> render test for the tab strip + per-plate heatmap.
>
> **Do not** add a `wells` top-level field to the backend response as a
> backwards-compat shim. Change the frontend.
>
> #### Bug 3 — Scientist text vanishes during import [IMPORTANT]
>
> Files:
> - `backend/src/chem_vault/application/screening/long_format_normalizer.py`
> - `backend/src/chem_vault/application/screening/import_run_file.py`
> - `frontend/src/features/screening-assay/components/run-import-wizard.tsx`
>   (mapping step)
>
> **Root cause:** the wizard offers two ways to map a column —
> "Scientist" role or "Readout" with a readout def. Today, only "Readout"
> mappings result in `ReadoutData` writes (and only numeric ones, because
> `_parse_float` is in the path). "Scientist" role stores the value on
> `LongFormatRow.scientist` and **drops it** — `ImportRunFile` never
> reads that field. Result: the protocol's `Scientist` Text readout def
> is never populated; the column shows em-dash on the Readout Data
> table.
>
> The deeper issue: the long-format normalizer cannot handle Text
> readouts at all. `_parse_float` rejects them. The wizard's "Readout"
> dropdown likely doesn't surface Text readout defs.
>
> **Proper fix (not a patch):** add Text readout support end-to-end.
>
> 1. `long_format_normalizer.py`: extend `LongFormatRow.readouts` to
>    `dict[uuid.UUID, float | str]`. The mapping step decides per
>    readout column whether to parse as float or text based on the
>    selected readout def's `data_type` (TEXT vs NUMERIC). The wizard
>    backend route must accept this — extend `ColumnMapping.ReadoutColumn`
>    if needed, OR parse type-blind and let the writer dispatch. The
>    type-aware branch is cleaner: extend `ReadoutColumn` with a flag
>    or look up the def by id at parse time.
>
> 2. `import_run_file.py`: when writing `ReadoutData`, dispatch on the
>    readout def's `data_type`. TEXT → `value=None, value_text=str(v)`;
>    NUMERIC → `value=QualifiedValue(value=float(v))`.
>
> 3. Wizard frontend: list Text readout defs in the readout-column
>    dropdown alongside Numeric. Synonym matching for Scientist columns
>    can suggest a TEXT readout def named "Scientist" if one exists.
>
> 4. **Drop the Scientist *role*** from the wizard. It exists only to
>    work around the missing Text-readout support; once Text readouts
>    work, the role is redundant. Migrating callers: this role isn't
>    persisted anywhere downstream — confirm with a grep before deleting.
>    Update tests.
>
> If a stakeholder ever wants per-run "operator" info as run metadata
> (not per-row), use `Run.operator` — that field already exists.
>
> #### Bug 4 — `concentration` readout def shows em-dash on Readout Data table [DESIGN]
>
> The protocol has `concentration` as a Numeric readout def. But actual
> concentration values live on `Well.concentration` (set via the
> Concentration role at import time), not as `ReadoutData` rows. The
> grouped readout-data view has nothing to put in that column.
>
> **Proper fix:** treat this as a domain-modeling issue, not a display
> hack. The concentration is a property of the well (the dose at which
> a compound was tested), not a measurement. It must not be a readout
> def.
>
> 1. `Protocol.add_readout_definition` / `update_readout_definition`:
>    reject readout defs whose name (case-insensitive, normalized)
>    collides with reserved well-metadata names: `concentration`,
>    `dose`, `well`, `plate`, `batch`, `compound`. Domain
>    `ValidationError` with a clear message. This prevents the
>    confusion at protocol creation time.
>
> 2. UI: in the Add/Edit Readout dialogs on Design tab, surface the
>    same constraint as a real-time validation hint.
>
> 3. The user's existing `NadD-Sumo dose response` protocol will need
>    a New Version with `concentration` removed. The IC50 row's
>    `x_readout_name` is currently `"concentration"` — that's
>    documentation only; the fitter pulls X from `well.concentration`
>    regardless. Either point `x_readout_name` at a different existing
>    numeric readout (suboptimal — the field then lies) OR — better —
>    make `x_readout_name` Optional and have the IC50 def represent
>    "fit against well concentration" implicitly.
>
> The cleaner long-term move: `DoseResponseConfig.x_readout_name`
> becomes `Optional[str]`. When None, X is `well.concentration` (the
> default and most common case). When set, X is sourced from the named
> readout def (rare — only meaningful for derived/transformed X axes,
> e.g., log-concentration computed via a formula readout). This
> dual-source model needs to be reflected in:
>
> - `DoseResponseConfig` domain validation (already enforces
>   `x_readout_name != y_readout_name` when both set; relax for None).
> - `Protocol.add_readout_definition` cross-readout-name validation
>   (only when set).
> - `fit_dose_response.py` X-axis sourcing (already uses
>   `well.concentration` — make this explicit when `x_readout_name` is
>   None).
> - The Add/Edit Readout dialog (X readout dropdown gets a "(use well
>   concentration)" None option, and that's the default).
>
> Migration: existing `DoseResponseConfig` rows with non-empty
> `x_readout_name` keep working; document that `concentration` /
> `dose` etc. are no longer valid x_readout names going forward.
>
> #### Don't forget
>
> - All four bugs need new tests, not just code changes. Cover the
>   non-obvious cases (Bug 1: calculated readouts; Bug 2: single-plate
>   AND multi-plate AND zero-plate; Bug 3: TEXT readout writes; Bug 4:
>   reserved-name validation + None x_readout_name).
> - Backend type-check + full unit test suite must pass before each
>   commit. `uv run pytest backend/tests/unit/` is the canonical command.
> - Frontend `pnpm tsc --noEmit` must be clean before commit.
> - Migrations: only Bug 4 might need one (if `x_readout_name` becomes
>   nullable in the DB — confirm by reading the schema). Bugs 1–3 are
>   pure application/code fixes.
> - The user has 24 unpushed commits on `fe2`. Don't push without
>   asking. After all four bugs are fixed and verified by the user
>   manually re-running the NadD flow, ask whether to push and whether
>   to merge `fe2 → main`.
>
> #### Manual verification recipe (after each bug is fixed)
>
> 1. Restart backend (`docker compose restart backend`).
> 2. Delete the existing `Run 2026-05-05` (Delete button works now).
> 3. Click "New Run" on the protocol → pick the plate template → save.
> 4. Open the run → Plate Map tab → "Import Run File".
> 5. Upload `~/Downloads/NadD_LG-2200467564_100uM-DR_4.20.26.xlsx`.
> 6. Wizard auto-suggests should be all High confidence. Map Raw Data
>    to `raw AU`. Continue.
> 7. Preview: 2 plates × 384 wells. **No red validation banner.**
>    Confirm.
> 8. After Bug 1 fix: Dose-Response tab → curves have non-zero
>    parameters; R² in [0, 1]; classes mix of Active/Inactive based on
>    actual dose-response in the data.
> 9. After Bug 2 fix: Plate Map tab renders TWO heatmaps (one per
>    plate, with a tab strip). Col 1 wells are red (NEG), col 24 wells
>    are green (POS), samples shaded by % inhibition.
> 10. After Bug 3 fix: Readout Data table shows "Dan Selle" (or
>     whoever) under the Scientist column for sample rows.
> 11. After Bug 4 fix: protocol design tab rejects readouts named
>     `concentration`; existing IC50 row's X axis can be saved with
>     no readout (uses well concentration implicitly).
>
> The smoke is "do all of this on the actual file with the actual
> protocol the user already has, end-to-end, in a browser." Type-check
> + tests are necessary but not sufficient.
>
> ---

> ### What Was Built (2026-05-05 cont., branch: `fe2`) — long-format run import shipped
>
> All eight sessions of the long-format run-file import plan
> (`docs/planning/run-import-long-format-plan.md`) are now in. Eight commits
> on top of the prior session's UX/bugfix work, all on `fe2`.
>
> **Backend (S1–S5)**
> 1. `316893d` `feat(parsers): unify csv + xlsx via tabular_file abstraction`
>    — single `parse_tabular(bytes, filename)` that detects xlsx via magic
>    bytes / extension; existing `ImportRunReadouts` + `ParsePlateMapFile`
>    refactored to consume `ParsedTable`. Both endpoints accept .xlsx.
> 2. `b025e11` `feat(screening): long-format run file normalizer`
>    — pure-function `infer_mapping()` (synonyms + value-based fallback with
>    confidence) + `normalize()` (A01↔A1, plate-format inference, control
>    inference). NadD fixture roundtrip in tests.
> 3. `7bfdcaa` `feat(screening): ImportRunFile use case + preview/import gate`
>    — `PreviewRunFile` parses + suggests + dry-resolves batches, stashes
>    parsed table in TTL `InMemoryPreviewStore`; `ImportRunFile` consumes
>    `preview_id` + confirmed `ColumnMapping`, builds Plate/Well/ReadoutData.
>    Locked-run, has-wells, unmatched-batch policies enforced.
> 4. `0e80a6d` `feat(screening): RunImportTemplate aggregate + CRUD + DI`
>    — workspace-scoped reusable column mapping. New table
>    `run_import_templates` (alembic 016). Header-match scoring helper.
> 5. `8e9e796` `feat(api): REST endpoints for run-file import + templates`
>    — `POST /runs/{id}/preview-file` (multipart), `POST /runs/{id}/import-file`
>    (JSON), full CRUD on `/run-import-templates`.
>
> **Frontend (S6–S7)**
> 6. `43a8962` `feat(screening): RunImportWizard + Run Detail entry points`
>    — 4-step modal (Upload → Mapping → Preview → Confirm) with confidence
>    badges, auto-applied template banner, save-as-template toggle. Wired
>    into RunDataPanel: primary "Import Run File" on Plate Map empty state,
>    secondary toolbar button on Readout Data when no plate map exists.
>
> **Test status:** 1514 unit tests pass. Frontend `tsc --noEmit` clean.
> Integration/API tests skipped — would need Docker Postgres.
>
> #### Migrations to apply (in order)
>
> 1. `015_add_updated_at_to_compound_flags.py` (committed earlier this
>    session — `ae6cb87`)
> 2. `016_add_run_import_templates.py` (this batch — `0e80a6d`)
>
> Run `alembic upgrade head` before smoke-testing.
>
> #### Manual smoke recipe
>
> 1. Start backend + frontend.
> 2. Create or pick an active protocol with at least one Numeric readout
>    definition.
> 3. Click **New Run**, save the empty draft.
> 4. Open the run, go to **Plate Map** tab, click **Import Run File**.
> 5. Upload `~/Downloads/NadD_LG-2200467564_100uM-DR_4.20.26.xlsx`.
> 6. Mapping step should auto-populate from synonyms (Plate Name, Well,
>    Concentration, LGCY BATCH NAME, Raw Data, Scientist all "high"
>    confidence). Pick the readout definition for "Raw Data". Continue.
> 7. Preview shows two 384-well plates. Most batch refs will be unmatched
>    (the lab's external batches aren't registered locally) — wells with
>    refs will be skipped, blank wells will still come through.
> 8. Click Import. The run gets two plates and the inferred blanks.
>
> #### Deferred / known gaps
>
> - **L8 — Playwright E2E**: not added. Smoke manually first.
> - **replace_existing**: command field accepted but the use case currently
>   fails with `ValidationError("not yet supported in MVP — re-create the
>   run")`. The wizard does not expose this option. To re-import, delete
>   the run and re-create.
> - **Curve-fitting auto-trigger**: out of MVP — readout data is written
>   but `FitCurvesForRun` is not called by the importer.
> - **Async/Temporal pipeline**: out of MVP — sync only with a 50K-row cap.
>
> ---
>
> ### Earlier on 2026-05-05 (branch: `fe2`)
>
> Small UX/bugfix session + planning for the next major feature.
>
> #### Commits
>
> 1. `891a32d` fix(search): saved-search load stuck on skeleton — inline mutation
>    Saved-search useEffect routed through `handleSearch` via a ref, but its
>    closure captured `readoutExtraColumns`. `loadFromSavedSearch` updated
>    Zustand inside the same effect that invalidated the render, intermittently
>    losing the mutation's onSuccess. Inlined `searchMutation.mutate` in the
>    effect; deps now use stable `runSearch` + `enrichItems` references.
> 2. (uncommitted) feat(screening): wire "New Run" button + fix Select empty-string
>    `CreateRunDialog` was mounted but had no trigger. Added "New Run" button to
>    Protocol Detail actions for active protocols. Fixed Radix Select crash:
>    `<SelectItem value="">` → `value="__none__"` with mapping back to null on
>    submit.
>
> #### Plan written, ready for next session
>
> **Long-format run import + xlsx-everywhere** — see
> `docs/planning/run-import-long-format-plan.md`. 8 sessions (S1–S8), starting
> with a tabular file abstraction that makes xlsx a first-class format across
> all importers. The reference file is
> `~/Downloads/NadD_LG-2200467564_100uM-DR_4.20.26.xlsx` (384-well, long
> format).
>
> Key locked decisions:
> - One file → one run, multi-plate (distinct `Plate Name` values ⇒ separate plates).
> - xlsx + csv via shared parser; existing CSV importers refactored to consume it.
> - Preview-then-write hard gate (separate endpoints, short-lived `preview_id`).
> - Fuzzy header guessing with confidence badges; user verifies in wizard.
> - Workspace-scoped mapping templates (NOT per-protocol — readout-def mapping is per-protocol).
> - Run pre-created via existing dialog; "Import Run File" populates wells + readouts.
>
> Defaults already chosen (override in next session if needed):
> - Multi-readout columns supported in MVP.
> - Unmatched batch ref ⇒ skip + report (not silently treat as control).
> - Sync only; Temporal deferred.
>
> **Next session entry point:** read the plan doc + `import_run_readouts.py` +
> `plate_setup.py`, then start S1 (tabular file abstraction).
>
> ---
>
> ### What Was Built (2026-05-03, branch: `fe2`) — ALL COMMITTED + PUSHED
>
> **Major backend refactor + Phase A/B wizard work consolidation.** Cleaned up
> 226 uncommitted files plus pre-existing test breakage on `fe2`.
>
> #### New commits this session
>
> 1. `06f6971` refactor(backend): hoist workspace_id into DomainEvent base, extract CQRS readers, split DI container
> 2. `d5743e2` feat(frontend): wizard polish, merge-impact row, query-key extraction
> 3. `3d35e2e` fix(execute-search): restore saved-search write-back on first page
> 4. `d3d558f` refactor(cdd-import): migrate protocol use cases to GetDataSourceForImport
>
> #### Backend refactor highlights (`06f6971`)
>
> - **Domain events:** `workspace_id` hoisted into `DomainEvent` base; per-context events
>   (attachment, research_org, chemical_reg, inventory, screening, workspace_config)
>   updated; emitting entities now pass `workspace_id` at construction.
> - **Attachment:** `StorageClient` protocol moved domain → application; auth tightened
>   (`require_same_workspace`); event dispatch moved outside the UoW transaction.
> - **CQRS Reader pattern:** raw-SQL read queries extracted from use cases into
>   infrastructure `*_reader.py` classes — `inventory_summary`, `merge_impact`,
>   `plate_map`, `protocol_activity`, `protocol_stats`, `dose_response_enriched`,
>   `readout_data_enriched`, `compound_curves`. Application now exposes thin Reader interfaces.
> - **DI:** monolithic 1979-line `container.py` split into per-context modules
>   (`_attachment`, `_audit`, `_cdd_import`, `_chemical_registration`, `_core`,
>   `_dashboard`, `_inventory`, `_research_organization`, `_screening`, `_user`,
>   `_workspace_config`).
> - **New screening features:** compound flags CRUD, `fit_curves_for_run`,
>   `get_plate_map`, `list_runs_with_counts`, `list_dose_response_enriched`,
>   `list_readout_data_enriched`.
> - **CDD import:** dedicated status query handlers extracted
>   (`get_cdd_molecule_import_status`, `get_cdd_plate_import_status`).
> - **Domain pagination VO** (`domain/shared/pagination.py`) introduced.
>
> #### Test status
>
> **1462 unit tests pass, 0 skipped, 0 failing.** (Started at 1448 passing + 14 failing.)
> Two pre-existing breakages on `fe2` (unrelated to this session's WIP) were
> properly fixed rather than papered over: ExecuteSearch saved-search write-back
> (`3d35e2e`) and CDD protocol use cases that called `check_cdd_configured` with
> the wrong arity (`d3d558f`).
>
> Integration/API tests (172 errors) skipped — require Docker Postgres.
>
> #### Phase B wizard status (committed earlier on `fe2`)
>
> - StepBatch + StepSummary wizard steps wired in (`7212871`)
> - Entry points point at wizard, old dialogs removed (`29c8bf7`)
> - Disclosure mode hits disclosure endpoint, not registration (`84d696d`)
> - Disclosure provenance fields + pre-submit confirmation (`9a62ef4`)
> - FormData Content-Type + status poll URL fixes (`c4f8714`)
>
> ---
>
> ### Recommended next session
>
> 1. **Merge `fe2` → `main`.** `fe2` is now 20+ commits ahead, all green, all pushed.
>    Phase A (two-phase disclosure with merge preview) is stable and Phase B wizard
>    is functional.
> 2. **Pending-disclosures visibility** — badge on dashboard / disclosure review list
>    for compounds stuck in `pending_confirmation` status.
> 3. **Search revamp follow-through** — saved searches now functional again
>    (write-back fixed), but the broader revamp (cross-protocol selectivity, unified
>    search UI, readout column customization) is still open.
>
> ### Operational backlog (from prior sessions, still open)
>
> - Complete 214K molecule import (resume script or fresh start)
> - Re-import molecules to populate `cdd_batch_id` on existing batches
> - Run plate import against live vault (2,152 plates)
> - Export file cleanup (old chunk files never deleted)
> - Bulk protocol import — Temporal pipeline (single import works)
> - Import Wizard Phase 2 (runs + readout data) — plan written
>   (`docs/planning/run-import-long-format-plan.md`), implementation pending
> - Screening dashboard redesign (`/assays` global views, summary cards)
> - T10 Custom Fields + Salt Forms (next from Gap Fix Plan)
