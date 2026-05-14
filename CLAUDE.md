# Cellar

Chemical compound management & screening platform (enterprise-grade). 8 bounded contexts, 17+ aggregates, 136 use cases.

**Repo:** `git@github.com:sidxz/cellar.git`
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
cellar2/
  backend/
    pyproject.toml
    alembic/
    src/cellar/
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
7. **Before ending** — updates "Current Session Notes" below with a brief handoff if work needs continuation

**Layer order per context:** Domain -> Domain tests -> Persistence -> Integration tests -> Application -> API -> API tests -> UI -> E2E tests

## Current Session Notes

_Per-conversation handoff. Add a brief status block when ending a session that needs continuation; keep prior handoffs out of this file once the work is shipped._

### 2026-05-14 — DR curve identity refactor + dynamic intercept columns on `prot-2`

**Branch:** `prot-2`, `git rev-list --count e807dd03..HEAD` commits ahead of the merged `fe2` HEAD. Nothing pushed yet. Dev DB at head migration `035_cc_intercept_key`. Live snapshot rebuild has been run (`rebuild_campaign_curve_snapshots.py --include-closed`) so existing closed campaigns now carry the full chart shape.

**Spec:** `docs/superpowers/specs/2026-05-13-dynamic-intercept-columns-design.md` (8 surfaces shipped, all acknowledged as done modulo browser smoke).

**Commits shipped this session** (full detail in `git log`; this list is hash + one-line "what" + key tests/migrations only):

| # | Hash | Title | Notes |
|---|---|---|---|
| 1 | `32da062c` | refactor(screening): identify DR curves by readout-def, not curve_type | Migrations 033 + 034. Truncates `dose_response_curves`; resolver + 3 reader queries flip to `readout_definition_id`. |
| 2 | `19ed9253` | chore(screening): refit-all script | Ran live, restored 40 curves across 5 runs / 3 protocols. |
| 3 | `0d8aae80` | fix(screening): IC90/EC90 marker Y position needs level/100 | Single-line fix; was producing y≈9746 on the chart. |
| 4 | `a31bf7cc` | feat(screening): run DR table per-intercept columns (Surface #1) | New `intercept-label.ts` + 9 unit tests. |
| 5 | `5fe1e245` | feat(screening): activity tabs per-intercept columns (Surfaces #2–#3) | Both protocol-hub + molecule-activity payloads. |
| 6 | `e67b7641` | feat(search): results grid per-intercept columns (Surface #4) | `resolveColumns` over the new `drc:<rd_id>` colId shape; +7 grid tests. |
| 7 | `971c03de` | refactor(screening): chart labels via interceptLabel (Surface #5) | Single source of truth across surfaces. |
| 8 | `c92f3d11` | feat(screening): readout-data table per-intercept columns (Surface #6) | FE-only denorm. |
| 9 | `622490f8` | fix(search): detail drawer "Selected Protocols" missing on DR rows | Lifted resolver into shared `protocol-column-id.ts` (+5 tests). |
| 10 | `c561f557` | feat(screening): promote Intercepts to first-class in protocol design | Editor moves out of collapsed `<details>`; create-dialog now emits `intercepts`. |
| 11 | `db04e938` | feat(screening): hit-criteria builder targets specific intercepts (Surface #7) | New `InterceptKey` VO + `hit-criteria-options.ts`. |
| 12 | `dbc42464` | feat(search): unified Export menu (Surface #8 — scope-reduced) | CI sub-columns vetoed at smoke (see [[feedback-no-ci-subcolumns]]). |
| 13 | `73bb6f07` | feat(campaign): channel hit threshold honors intercept_key end-to-end | FE picker, defaults, display chip; +9 FE tests. |
| 14 | `0003597e` | feat(campaign): add-from-runs splits multi-intercept DR readouts per intercept | `channelConfigKey` helper; +5 FE tests. |
| 15 | `e364c07b` | fix(campaign): multi-intercept channels — proper cells, hits, labels | 3 coordinated bugs (channel-key collision + primary aggregate + label collision); +1 BE test. |
| 16 | `1c19f594` | feat(campaign): channel intercept_key as top-level field (Option A) | **Migration 035** (additive JSONB on `campaign_channel`). Decouples identity from `hit_threshold`; `_intercept_scalar` becomes the single SoT. +1 BE preview test, 4 resolver tests updated. |
| 17 | `00cf02bd` | feat(campaign): mirror protocol — bulk-create channels for every readout | New use case + `POST /channels/mirror-protocol` + `MirrorProtocolPopover`. Idempotent on `(protocol, rd, norm, ik)`. +6 BE tests. |
| 18 | `570f67b6` | feat(campaign): expand-dialog renders via shared DoseResponseChart | `_build_curve_snapshot` writes `curve_type` + `intercept_values` + CI + warnings; new `snapshotToDoseResponseCurve` adapter; dialog rewritten ~100→~50 LOC. **Backfill script** (`rebuild_campaign_curve_snapshots.py`, `--include-closed` ran). +1 BE + 4 FE tests. |
| 19 | `ec0eeb15` | fix(campaign): closed view defaults filter to Selected only | New `closedCampaignFilters()`; chemist's frame is "what made the cut". |

**Verification at HEAD:**
- Backend research_org subset = **218 passed** (was 211 pre-session); migration 035 on dev DB; live snapshot rebuild complete.
- Frontend = **156 passed**, `pnpm exec tsc --noEmit` clean.
- Browser smoke for Surfaces #1–#7 passed on 2026-05-14. Commits #12, #14, #15, #16, #17, #18, #19 still need fresh browser smokes.

**How to resume:**
1. **Live smoke #16** on `Mtb_WCA_mc2-7000_Resazurin` against a fresh campaign — add-from-runs with `EC50 use_for_filter:ON, <50 µM` + `EC90 use_for_filter:OFF, no threshold`. Expect `22 mols · 2 hits` (CV-00967, CV-00983), distinct EC50 vs EC90 cell numbers, HIT badges only on the EC50 column. DB check: 2 rows on `campaign_channel` for Resazurin — EC50 row `intercept_key=NULL`, EC90 row `intercept_key={"kind":"ec","level":90.0}`. Then edit the EC90 channel to add `<100` threshold and re-render → EC90 cells gain HIT badges where appropriate.
2. **Live smoke #17** on the same protocol against a *fresh* campaign with NO channels — click `[Copy] Mirror protocol`, pick the protocol, click **Mirror**. Expect `Created N channels` toast. Re-mirror → `No new channels — N already mirrored`. DB check: rows match expected shape (multi-intercept DR → 2 rows, non-DR → 1 row each with `normalization_applied` set).
3. **Live smoke #18** on the existing closed `Mtb_WCA_mc2-7000_Resazurin` campaign — click a curve thumbnail. Expand dialog should render via `<DoseResponseChart>` with intercept chip strip (EC50 + EC90), CI strip, warning badges — bit-identical to the same compound in the search compound-detail sheet. Backfill already ran so closed-campaign snapshots carry the full shape.
4. **Live smoke #19** — open the closed `Mtb_WCA_mc2-7000_Resazurin` campaign and confirm the filter bar opens with `Selected` chip pre-active and only the 2 selected molecules visible (rejected/deferred chips one click away).
5. **Smoke #12 + #14 + #15** if not already done.
6. **Push** — `prot-2` is local-only. After smokes pass: push and open a PR against `main`.

**Diagnostic anchors:**
- `frontend/src/features/screening-assay/lib/intercept-label.ts` — only place chemist-facing intercept labels are produced or cell lookups happen. `narrowInterceptKey` is the wire→domain narrower for orval-generated `{kind: string, ...}` → hand-typed `InterceptKey`.
- `frontend/src/features/screening-assay/lib/hit-criteria-options.ts` — only place the hit-criteria dialog's option list is built or a rule is mapped back to an option id.
- `frontend/src/features/research-organization/lib/protocol-column-id.ts` — only place `drc:<rd_id>` / `rd:<proto>:<rd>` colIds get joined back to their owning protocol.
- `application/screening/molecule_activity_service.py::_serialize_intercept_values` — single helper feeds both the molecule-activity payload and the search-grid `ActivityValue.intercept_values`.
- `application/research_organization/channel_resolution.py::_intercept_scalar` — single helper produces the channel's per-candidate scalar from `channel.intercept_key`. `_build_curve_snapshot` in the same file is the only place a `CampaignMeasurement.curve_snapshot` JSONB is shaped.
- `application/research_organization/preview_run_import.py` + `add_results_from_runs.py` — channel-reuse key tuple's fourth element is `cfg.intercept_key` (top-level), not `cfg.hit_threshold.intercept_key`. Display-only multi-intercept channels keep identity even with `hit_threshold=None`.
- `application/research_organization/mirror_protocol_channels.py` — only place that bulk-creates channels from a protocol; same idempotency key as preview_run_import.
- `frontend/src/features/screen-campaign/lib/snapshot-adapter.ts::snapshotToDoseResponseCurve` — only place the campaign's `CurveSnapshot` is widened to the chart's `DoseResponseCurve` shape.

**Open caveat:** Multi-DR protocols (2+ DOSE_RESPONSE readout-defs with their own intercept lists) still use the *first* DR readout's intercepts on every grid. Per-readout column groups deferred until a real protocol surfaces it.

Long-lived state lives in `~/.claude` memory — see `MEMORY.md`, especially `feedback_drc_identity.md` (the "curves keyed by readout_definition_id" principle that motivated the whole refactor).
