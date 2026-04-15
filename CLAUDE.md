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

> ### What Was Built (2026-04-15, branch: `fe2`) — ALL COMMITTED
>
> **Two-Phase Disclosure with Merge Preview — Phase A Complete**
>
> **Design doc:** `docs/planning/merge-preview-design.md`
>
> #### Summary of All Commits on fe2
>
> 1. `886ac86` fix: disclosure FK violation + add missing merge side effects
> 2. `1ac9022` feat: two-phase disclosure with merge preview (domain + application)
> 3. `43ee2a3` fix: mark_conflict keyword arg + add find_by_id_in_workspace to Protocol
> 4. `91d86c5` feat: merge preview UI + API wiring (Steps 3-5, Phase A)
>
> #### What Phase A Delivered (Steps 1-5)
>
> **Backend:**
> - `PENDING_CONFIRMATION` status + state machine transitions on DisclosureRequest
> - `matched_molecule_id`, `scientist_name` fields on DR entity + persistence
> - `auto_approve` flag on `SubmitDisclosureCommand` (default True, backwards-compatible)
> - `ConfirmDisclosure`, `RejectDisclosure`, `GetMergeImpact` use cases
> - DI wiring + 3 new endpoints: `POST .../confirm`, `POST .../reject`, `GET .../merge-impact/{tgt}`
> - 226 chem-reg unit tests passing
>
> **Frontend:**
> - **Merge preview page** (`/compounds/[id]/merge-preview/[disclosureId]`)
>   - Side-by-side source/target cards, expandable impact sections, blocker detection
>   - Confirm → merges + redirects to target; Reject → molecule stays undisclosed
>   - Human-readable breadcrumbs via `useBreadcrumbTrail`
> - **Inline disclosure** on compound detail overview tab (replaces popup dialog)
>   - "Disclose" on list navigates to `/compounds/{id}#disclose`, auto-opens form
>   - Sends `auto_approve: false`, redirects to merge preview on match
> - **Admin Operations tab** — admin-only (`useAuthzHasRole("admin")`), manual merge
> - **Merge button removed** from compound list
> - Types: `pending_confirmation` status, `MergeImpact`, hooks for confirm/reject/impact
>
> #### NEXT SESSION — Phase B: Unified Registration + Disclosure Wizard
>
> **Design doc section:** `docs/planning/merge-preview-design.md` → "Phase B Vision"
>
> Phase B is **not yet designed in detail**. The vision section captures:
> - Unified registration + disclosure wizard (7-step: Info → Structure → Processing → Merge Preview → Provenance → Batch → Review)
> - Single UI for both new registration and undisclosed disclosure
> - Bulk wizard merge confirmation review step
> - Disclosure provenance as separate aggregate/VO list
>
> **Before coding Phase B, design it first.** The current registration dialog
> (`molecule-registration-dialog.tsx`, 480 lines) and disclosure flow
> (now inline on overview tab) would be replaced by a single full-page wizard.
>
> #### Also Consider for Next Session
>
> - **Merge fe2 → main** — Phase A is stable, tested manually
> - **Pending disclosures visibility** — badge on dashboard or disclosure review list
>   for compounds stuck in `pending_confirmation` status
>
> #### What Else Needs Attention
>
> - **Complete 214K molecule import** — use resume script or start fresh
> - **Re-import molecules to populate cdd_batch_id** — existing batches don't have it
> - **Run plate import** against live vault (2,152 plates)
> - **Export file cleanup** — old chunk files on disk are never deleted
>
> ### Still Pending (from previous sessions)
>
> - **Bulk protocol import** — single protocol import works, need Temporal pipeline for bulk
> - **Import Wizard Phase 2** (runs + readout data) — designed not built
> - **Screening dashboard redesign** (global views, summary cards for `/assays`)
> - **Readout Column Customization** — per-protocol readout checkboxes in search
> - **Search revamp** — saved searches broken, cross-protocol selectivity + unified search UI
