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
7. **Before ending** — updates "Current Session Notes" below with a brief handoff if work needs continuation

**Layer order per context:** Domain -> Domain tests -> Persistence -> Integration tests -> Application -> API -> API tests -> UI -> E2E tests

## Current Session Notes

_Per-conversation handoff. Add a brief status block when ending a session that needs continuation; keep prior handoffs out of this file once the work is shipped._

### 2026-05-11 — Screen Campaign feature, Phase 5 complete on `fe2`

**Spec:** `docs/superpowers/specs/2026-05-10-screen-campaign-design.md`
**Plan:** `docs/superpowers/plans/2026-05-10-screen-campaign.md` (10 phases, 40 tasks)
**Execution mode:** subagent-driven (one implementer + spec reviewer + quality reviewer per task)

**Shipped this session (12 commits, `001a18de..c2dda618`):**
- Refactor: extracted shared test fakes to `tests/unit/application/research_organization/_helpers.py` (`001a18de`) — `FakeUnitOfWork`, `fake_auth`, `make_campaign_repo`, `make_collection_repo`, `FakeResolver`. 11 campaign test files migrated, behaviour identical.
- Task 5.2: ManageCampaignChannels — three commits (`3838dd91`, `405afd35`, `fe6034ea`) for add / update / remove.
- Task 5.3: ReseedCampaign (`06ba68a2`).
- Task 5.4: ManageCampaignResults (`bb1d6a17`) — single commit, 4 sub-use-cases (SetResultDecision, OverrideResultCell, AddResultRow, RemoveResultRow).
- Task 5.5: RefreshFromSources + RecomputeChannel (`dc2fda68`).
- Task 5.6: CloseCampaign (`1979090b` impl + `4931b721` fix). Stub e-sig design — caller supplies `signature_id`. Both unit tests (12) and integration test (1). Required four load-bearing deviations from the spec pseudocode — see "Close-campaign architecture notes" below.
- Task 5.7: SupersedeCampaign (`99d0bc48`).
- Task 5.8: GetPublishedCampaign query (`67fff714` impl + `c2dda618` cleanup).

**Test state:** 2027 unit tests pass (1922 baseline + 105 new), 13+ integration tests pass (incl. one new `test_close_campaign.py`). Zero regressions.

**Phase 5 complete. Next: Phase 6** — API routes in `interface/routes/campaigns.py` (15 endpoints) + DAIKON published-JSON-contract schema test. Then Phases 7–9 frontend (orval regen → list page → builder UI with AG Grid pivot → closed view + supersede + Playwright). Then Phase 10 docs.

**Open follow-ups (surface before / during Phase 6):**

1. **Latent unique-constraint bug in 3 use cases.** `RefreshFromSources`, `RecomputeChannel`, and `UpdateCampaignChannel` all do re-resolve via `result.remove_measurement_for_channel(...)` + `result.add_measurement(<fresh-id measurement>)`. Against a real DB the cascade reconciler does DELETE+INSERT in the same flush — the **non-deferrable** unique index `uq_campaign_measurement_result_channel` (migration 027) fires per-INSERT and would collide with the existing row. `CloseCampaign` fixed this by reusing the existing measurement's id (`new_m.id = old_m.id` → cascade does UPDATE not DELETE+INSERT). Apply the same pattern to the three other use cases before any integration test exercises them. Unit tests don't catch it because they don't touch SQL.

2. **`get_published_campaign.py` TODOs** that block the DAIKON contract from being fully populated:
   - `closed_by.name` — needs Sentinel user resolver (no User repo in this codebase).
   - `signature.signed_at` — needs an `ElectronicSignatureRepository` lookup; the audit-compliance domain has the type but no application-layer query yet.
   - `BatchRepository.find_by_ids` doesn't exist — currently loops `find_by_id`.
   - Uses `require_editor`; should be `require_viewer` once that guard exists.

3. **SavedSearch source kind** still returns `Failure(ValidationError("…not yet supported"))` in CreateCampaign and ReseedCampaign. Wire SavedSearch execution into the resolver before exposing this source kind in the Phase 6 API.

4. **Signature service**. CloseCampaign takes `signature_id` directly in the command (caller-supplies stub). When the API layer lands in Phase 6, the route is responsible for capturing the signature (re-auth challenge → ElectronicSignature → pass the id). The `signature_meaning: str | None` field on `CloseCampaignCommand` is a placeholder for the future audit-log integration.

**Close-campaign architecture notes (load-bearing for any future close-flow work):**
- **Two-phase save** is required. The migration-027 PG trigger `reject_locked_campaign_write` fires `BEFORE INSERT/UPDATE/DELETE` on `campaign_measurement` and rejects any write when the parent campaign is not DRAFT. So close runs: save-as-DRAFT → flush → `campaign.close()` → save-as-CLOSED. (Spec said close-then-save; the trigger blocks that.)
- **Measurement id preservation during re-resolve** (see follow-up #1) — close was the first use case to need this and got it right.
- **Collection save-before-freeze.** `SQLAlchemyCollectionRepository.add_molecules` queries the persisted `is_frozen` flag (not the in-memory aggregate). Order in close: `Collection.create(...)` → save (still unfrozen) → `add_molecules(...)` → `coll.freeze(derived_from_campaign_id=campaign.id)` → save again. The aggregate is frozen in-memory after `add_molecules` so the membership operations succeed before the persisted row reflects the freeze.
- **Inline pre-validation** of "no channels" / "no results" before the first DRAFT save — same error strings as `Campaign.close()` so the caller sees one consistent message.
- **ND unit repair**: any non-override measurement whose `unit == "-"` (the resolver's ND placeholder) is rebuilt at close with the real `ReadoutDefinition.unit` (when non-empty), preserving id and all source-snapshot fields. The protocols already loaded for the source_protocols snapshot are reused — no double-fetch.

**Carry-over gotchas from the previous handoff (still relevant):**
- `CampaignMeasurement.__post_init__` rejects empty `unit`. (Close repairs ND placeholders; other use cases don't, by design.)
- `Collection.freeze(derived_from_campaign_id=...)` requires a real campaign id (FK from migration 027). Save the Campaign before freezing the Collection.
- `ProtocolModel.version` column is named `protocol_version` (not `version`).
- `ReadoutData` uses split columns (`value_numeric`, `value_qualifier`, `value_text`, `is_outlier`) — not a single QualifiedValue JSONB. Resolver SQL handles this.
- Test fixture pattern: use the existing `uow` fixture + `SQLAlchemyXRepository(uow)` instantiation per `tests/integration/test_database.py`; the plan referenced a non-existent `uow_factory` fixture.

**Use-case scaffolding pattern** (established by `create_campaign.py`):
- Frozen `@dataclass(kw_only=True)` Command extending `application.shared.command.Command`.
- `__call__(self, input, auth=None) -> Result[T, DomainError]` — auth optional for system actors.
- Constructor uses kw-only deps (`uow`, repos, `dispatcher: EventDispatcherProtocol`).
- `require_editor(auth)` first; auth carries workspace_id implicitly.
- Work inside `async with self._uow:`, then dispatch events outside.

**Out of scope for v1 (per spec §11):** DAIKON transport mechanism, external CSV import bypassing Runs, cross-campaign SAR queries.

To resume: read this block + the spec + the plan, then dispatch implementer for Task 5.2.

Long-lived state (current branch, what's shipped, what's next, operational backlog) lives in `~/.claude` memory — see `MEMORY.md` for the index.
