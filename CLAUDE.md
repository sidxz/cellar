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

### 2026-05-13 — Frontend cleanup (review punch list) on `fe2`

**Plan:** `docs/superpowers/plans/2026-05-12-frontend-cleanup.md`

**Shipped (49 commits, 113 files touched, 4a089392..93ced7a2):**
- Phase 1 — Shared primitives: `useDebounce`, `useHashTab`, `formatDate`/`formatDateTime`/`formatRelativeDate`, `formatFileSize`, `SearchInput`; extended `status-variants` (in_use/stored/merged/conflict/preclinical_candidate/development_candidate)
- Phase 2 — Sweeps: SearchInput at 7 callsites; useDebounce ×2; StatusBadge collapsing 4 local switches; date utilities across 18 files; formatFileSize ×2; ConfirmDeleteDialog at 5 delete callsites; useHashTab unifying tab state on 5 detail pages + inventory-dashboard
- Phase 3 — Cross-feature boundaries: `MOLECULES_KEY`, `CampaignList`, `CurveSnapshot`, `DoseResponseSparkline`, `CurveClassBadge`, `useProtocolSummaries` now exported via each feature's `index.ts`; 6 internal-path imports fixed
- Phase 4 — screen-campaign realignment: `hooks/` separated from `lib/`; `useCampaignsByProject` → `useCampaigns(projectId?)`; `useMoleculesByIds` moved to chemical-registration; raw `AgGridReact` callsites routed through `DataGrid` (DataGrid extended with `ColGroupDef` support + `clearSelectionToken` prop); `campaign-builder.tsx` loading/error states aligned with `DetailShell`
- Phase 5 — Antipattern fixes: server-state-sync effect dropped in registration wizard; state-sync effects in `molecule-selector`/`override-modal`/`add-from-runs-dialog` replaced with derived values; `window.location.href`/`window.location.hash` replaced with `useRouter`/`useHashTab`; search-page 11 useStates collapsed into a reducer; CSS group-hover replaces per-cell `useState(hover)` in results-grid; `audit-timeline` uses shared `EmptyState`
- Phase 6 — God-module decomp:
  - `design-tab.tsx` 2080→756 (-64%) + extracted use-readout-definition-form hook, readout-definition-dialog, condition-definition-dialog, design-tab-protocol-card
  - `search-query-builder.tsx` 1554→285 (-82%) + extracted search-query-config + 4 criterion-row files (simple/resource/structure/advanced)
  - `synthesis-request-detail.tsx` 1191→519 (-56%) + extracted use-synthesis-request-actions hook + synthesis-request-dialogs
  - `activity-tab.tsx` 1021→658, `run-dr-results.tsx` 757→443 (extracted columns/transforms/use-activity-tab)
  - `dose-response-chart.tsx` 1549→1054 (extracted math/constraints/controls)
  - `run-import-wizard.tsx` 1291→960 (extracted run-import-mapping + use-run-import-wizard hook)
  - `run-detail.tsx` 836→776 (extracted use-recompute-overrides hook)
- Phase 7 — RHF + Zod form migration: 12 dialogs migrated to react-hook-form + zod (create-project, create-collection, organization, create-saved-search, registration-form-admin, ontology-slot-admin, custom-field-admin, api-key-admin, workspace-settings-form, data-source-detail, create-run-dialog, create-protocol-dialog)
- Phase 8 — Promoted `CollectionPickerDialog` to shared with `simple?: boolean` prop (deleted both per-feature copies); `MoleculeThumbnail` kept (legitimate size/null-handling wrapper)

**Verification:** `pnpm exec tsc --noEmit` clean. `pnpm test` 106/106 pass. `pnpm lint` 753 pre-existing errors (–3 net from baseline, no new errors introduced). Branch is local; not pushed.

**Deferred to next session:**
- Browser smoke: dialogs (12 migrated), all detail-page tabs (hash links), Add-from-runs flow (state derivation refactor), inventory-dashboard navigation, search-page reducer
- Task 35 — Orval regen + remove `as unknown as` casts (5 sites) — needs backend OpenAPI to expose `curve_snapshot` field and proper `recommended_hit_criteria` typing first
- Optional follow-ups noted by sub-agents: extract `SummaryCard` from `dose-response-chart` (~890 lines after), extract step sub-components from `run-import-wizard` (~600 lines after), split `readout-definition-dialog.tsx` (904 lines) — none essential, all clean wins if pursued

**Next:** Browser smoke-test on the 12 form migrations and the major decomps (Phase 6+7 surfaces). Then push `fe2` and merge.

Long-lived state (current branch, what's shipped, what's next, operational backlog) lives in `~/.claude` memory — see `MEMORY.md` for the index.
