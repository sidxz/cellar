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

> ### What Was Built (2026-05-05, branch: `fe2`)
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
