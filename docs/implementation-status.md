# Implementation Status

## Phase 0: Foundation (Sessions 1-8)
- [x] S01 — Project scaffolding (dirs, pyproject.toml, package.json, Docker Compose, CI skeleton)
- [x] S02 — Shared kernel (Entity, AggregateRoot, DomainEvent, DomainError, all VOs, Repository Protocol, enums)
- [x] S03 — Database infrastructure (async engine, SA base, UoW, generic repo, Alembic, RDKit extension, testcontainers)
- [x] S04 — Auth integration (Sentinel JWT middleware, RequestContext, permission decorators, app bootstrap)
- [x] S05 — Domain events + audit (EventDispatcher, AuditOperation/Entry/Signature, audit SA models, append-only triggers)
- [x] S06 — Frontend skeleton (Next.js 16, App Router, Sentinel auth flow, app shell, shadcn/ui dark mode)
- [x] S07 — DI container + app layer (Lagom composition root, UseCase protocol, Result-to-HTTP mapping)
- [x] S08 — Testing infrastructure (conftest, factory-boy, test helpers, CI pipeline green)

## Phase 1: Core Contexts (Sessions 9-32)

**Workspace Config (07):**
- [x] S09 — Domain + persistence (Organization, WorkspaceSettings, ControlledVocabulary, SA models, repos, migration)
- [x] S10 — API + UI (CRUD endpoints, admin pages)

**Chemical Registration (01):**
- [x] S11 — Molecule domain model (aggregate, identifiers, mixtures, relationships, state machines, events)
- [x] S12 — RDKit + chembl-structure-pipeline (standardizer, fingerprints, substructure matching, cartridge SQL)
- [x] S13 — Persistence (SA models, MoleculeRepository with RDKit queries, migration with mol/GiST/GIN)
- [x] S14 — MoleculeRegistrationService (Railway: standardize->dedup->create, QC threshold, custom fields)
- [x] S15 — Registration API + basic UI (POST/GET molecules, search, AG Grid list, Ketcher, detail page)
- [x] S16 — Disclosure domain (DisclosureRequest, BulkDisclosure, persistence, migration 006)
- [x] S17 — Merge service (MergeEvent, safety checks, side-effect registry, snapshot, tombstone)
- [x] S18 — Disclosure/Merge API + UI (DisclosureService, REST endpoints, frontend dialogs)
- [x] S19 — Synthesis routes (SynthesisRoute aggregate, DAG validation, service, persistence + API) [post-MVP]
- [x] S20 — Advanced (BulkRegistration, file parsing, lifecycle management)

**Inventory (03):**
- [x] S21 — Domain (Batch, Sample, StorageLocation, state machines, amount tracking, low stock)
- [x] S22 — Persistence + basic API (SA models, repos, migration, CRUD)
- [x] S23 — SampleRequest + Shipment (state machines, chain-of-custody) [post-MVP]
- [x] S24 — SynthesisRequest (10-state machine, assignment, fulfillment) [post-MVP]
- [x] S25 — API completion + UI (inventory dashboard, sample list, storage browser)
- [x] S26 — Synthesis Request UI [post-MVP]

**Screening & Assay (02):**
- [x] S27 — Protocol domain (Protocol aggregate, Target, PlateTemplate, ProtocolVersioningService)
- [x] S28 — Run domain + data lock (Run, ReadoutData, DoseResponseCurve, DataLockGuard, DataLockingService)
- [x] S29 — Persistence (SA models, repositories, migration 009)
- [x] S30 — API (Protocol CRUD, Run lifecycle, ReadoutData, DoseResponseCurve, lock/unlock, 22 endpoints)
- [x] S31 — Frontend protocols + runs (list/detail/create, status badges, approval workflow)
- [x] S32 — Frontend data viz (plate heatmap SVG, dose-response Plotly, activity data table)

## Phase 2: Core Workflow Completion (Reprioritized 2026-04-05)

> Reprioritized to complete core workflow loop (register -> organize -> screen -> search -> export).
> Spec: `docs/planning/phase2-core-workflow-design.md`

**Fingerprints + Indexed Similarity Search (#33):**
- [x] S33a — morgan_bfp column + DB trigger + GiST index (migration 015), integration tests
- [x] S33b — Similarity search uses pre-computed index, API returns Tanimoto scores, frontend card layout with structure + score

**Research Organization — Backend (#37):**
- [x] S37a — Domain models (Project, Collection with join table, SavedSearch)
- [x] S37b — Persistence + CollectionMergeSideEffect + integration tests
- [x] S37c — Use cases + API (Project CRUD, Collection CRUD + membership, SavedSearch CRUD)

**Research Organization — Frontend + Plates (#39, #59):**
- [x] S39a — Project + Collection UI (list/detail/create, bulk-add molecules)
- [x] S39b — SavedSearch UI (save/execute/edit searches)
- [x] S-PLATE — PlateTemplate CRUD API + UI, visual plate map builder, wire into Run creation

**Export + Search (#60, #61):**
- [x] S-EXPORT — AG Grid CSV/Excel export (shared component), SDF export backend endpoint
- [x] S-SEARCH — SavedSearch execution engine, combined structure+property search, AG Grid column prefs, cursor pagination

## Phase 3: Enhancement Contexts + Cross-Cutting (Restructured 2026-04-05)

**Temporal Workflows:**
- [ ] S49 — Temporal bulk ops (BulkRegistration, BulkDisclosure, MMP batch computation, async SAR)
- [ ] S50 — Temporal complex lifecycles (SynthesisRequest, Disclosure, Stability, PredictedProperties)

**Real-Time + Observability:**
- [ ] S51 — WebSocket real-time (Valkey pub/sub, useWebSocket, Sonner, notification center)
- [ ] S52 — Observability (structlog, OpenTelemetry, Grafana Tempo, Prometheus)

**ELN (deferred from Phase 2):**
- [ ] S38 — ELN domain (ELNEntry, ELNTemplate, LinkedEntityRef, signing workflow)
- [ ] S40 — ELN UI (Tiptap, custom extensions)
- [ ] S41 — ELN templates + polish

**Markush + MMP (deferred from Phase 2, requires Temporal):**
- [ ] S34 — Markush domain (MarkushDefinition, SMARTS validation, MarkushMatch)
- [ ] S35 — Markush services + API (MarkushSearchService, MarkushEnumerationService)
- [ ] S36 — SAR frontend (Markush editor, MMP viz, transformation table)

**Formulation & Drug Product (deferred from Phase 2):**
- [ ] S43 — Formulation domain (aggregate, ExcipientCatalog, versioning, merge handler)
- [ ] S44 — FormulationBatch + StabilityStudy
- [ ] S45 — Persistence + API
- [ ] S46 — Frontend recipes
- [ ] S47 — Frontend batch + stability
- [ ] S48 — Tests + polish

**CI/CD + Testing + Polish:**
- [ ] S53 — CI/CD finalization (full GitHub Actions, pre-commit, openapi-diff)
- [ ] S54 — E2E tests (Playwright: registration, screening, disclosure, merge, bulk upload)
- [ ] S55 — Search + filtering enhancements (beyond Phase 2 scope)
- [x] S56 — File storage + attachments (fsspec, Attachment entity, upload/download, react-dropzone)
- [ ] S57 — Advanced frontend (dashboard charts, compound detail tabs, comparison, SAR scatter)
- [ ] S58 — Performance + security (EXPLAIN ANALYZE, caching, rate limiting, sanitization, CORS)

## Phase Gates & Testing Milestones

| Gate | After | Criteria |
|------|-------|---------|
| T0 | S06 | Frontend renders, backend health check passes |
| G0 | S08 | `docker compose up && pytest && pnpm dev` all work |
| T1 | S10 | Workspace Config CRUD works end-to-end |
| G1 | S15 | Molecules can be registered, searched, viewed |
| T2 | S15 | Chemical registration API tests pass |
| G2 | S18 | Disclosure + merge works |
| T3 | S18 | Disclosure/merge tests pass |
| G3 | S25 | Inventory CRUD + UI works |
| T4 | S25 | Inventory tests pass |
| G4 | S32 | **MVP complete** — screening done, full demo possible |
| T5 | S32 | All Phase 1 tests pass |
| G5 | Post-S32 | Non-MVP Phase 1 sessions (19, 20, 23, 24, 26) done |
| G6 | S33b | Similarity search sub-second at 500K via pre-computed fingerprints |
| G7 | S37c | Projects + Collections + SavedSearch API works end-to-end |
| G8 | S-PLATE | Full UI for organizing research, plate template management complete |
| G9 | S-SEARCH | **Core workflow complete** — register -> organize -> screen -> search -> export |

## Cross-Cutting Operational Features

| Feature | Date | Status | Notes |
|---------|------|--------|-------|
| Admin Hard Delete (Tier 1 + Tier 2) | 2026-05-08 | SHIPPED | Generic hard-delete use case + RESTRICT guard (Tier 1) for all 23 registered entity types; cascade preview + force-delete (Tier 2) for Protocol/Run/Plate subtrees. FK-coverage gate (test_fk_coverage.py) enforces every FK is categorised. Admin UI wired into entity detail pages. |
| Screen Campaign (Phases 1-10) | 2026-05-11 | SHIPPED | See detail below. |
| Summary Results Import | 2026-06-02 | SHIPPED | Purely-additive, well-less `ReadoutData` import for wide-format summary files (compound/batch ref + endpoint readout columns; no plate/well). Reached via the "Import Summary Results" entry on the Run page (split button alongside plate "Import Run File", which is untouched). Lightweight wizard (Upload → Map → Preview → Confirm) offering only Compound Ref / Batch Ref / Readout / Ignore roles; writes well-less `ReadoutData` (`well_id = NULL`) into the current Run via the existing `BulkCreateReadoutData` resolver (opt-in upsert mode). Re-import upserts on `(run_id, molecule_id, batch_id, readout_definition_id)` — latest file wins. Backed by `POST /runs/{id}/preview-summary-file` (parse + suggest readout-def matches + dry-run) + `POST /runs/{id}/import-summary-file` (commit). Plan: `docs/superpowers/plans/2026-06-02-summary-results-import.md`. |
| Summary Import — identifier resolution + 4-step Preview | 2026-06-02 | SHIPPED | Follow-up hardening of Summary Results Import. (a) `compound_ref` now resolves **identifier-aware** via `molecule_repo.find_by_identifier` (name / synonym / external id / custom identifier / registration number), mirroring the plate import path — previously it matched only the `CC-…` registration number, so files keyed by custom identifiers (e.g. `SACC-*`) failed to resolve. Resolution lives in `application/screening/summary_import_resolver.py` (`build_compound_index` / `build_batch_index` async repo builders + pure `plan_summary_rows` planner). (b) The wizard is now a true 4-step flow (Upload → Map → **Preview** → Confirm) where Preview is a server-side dry-run forecasting matched/unmatched refs and insert-vs-update counts WITHOUT writing, backed by `POST /runs/{id}/resolve-summary-file` (`PreviewSummaryImport` use case). Verified end-to-end on real dev data (GlcB-9 file, `SACC-*` identifiers, Daikon Legacy run): 31/31 rows matched, 0 unmatched, 31 values_to_insert. Plan: `docs/superpowers/plans/2026-06-02-summary-results-import.md`. |

## Screen Campaign Feature (Branch `fe2`, 2026-05-11)

Spec: `docs/superpowers/specs/2026-05-10-screen-campaign-design.md`
Plan: `docs/superpowers/plans/2026-05-10-screen-campaign.md`

- [x] SC-Phase-1 — `Collection.is_frozen` + `derived_from_campaign_id` + Alembic migration 026. Freeze guard blocks membership changes on frozen collections. FK from `collections.derived_from_campaign_id → campaign.id ON DELETE SET NULL`. Commits: `3552174f`–`0a44e6c6` (approx.)
- [x] SC-Phase-2 — Campaign domain: aggregate root, CampaignChannel/CampaignResult/CampaignMeasurement entities, CompoundSource VO (four kinds), CampaignStatus enum, domain events (CampaignCreated, CampaignClosed, CampaignSuperseded, CampaignPublishedCollectionCreated), lock guard, CampaignRepository protocol.
- [x] SC-Phase-3 — SQLAlchemy ORM models, Alembic migration 027. Migration includes: PG defense-in-depth trigger blocking writes to non-DRAFT campaigns; non-deferrable unique index `(result_id, channel_id)` on `campaign_measurement`; FK from `collections.derived_from_campaign_id → campaign.id ON DELETE SET NULL`. Full `SQLAlchemyCampaignRepository` with cascade reconciliation + id-preservation pattern for measurements.
- [x] SC-Phase-4 — `ChannelResolutionService` (application) + `SQLChannelResolutionQuery` (infrastructure). Query joins `readout_data`/`dose_response_curve` → `run` → `protocol`, extracts `z_prime` from `qc_metrics` JSONB. Integration tests pass.
- [x] SC-Phase-5 — All application use cases (10 total):
  - `CreateCampaign` — commit `0666340b`
  - `ManageCampaignChannels` — add / update / remove channel
  - `ReseedCampaign` — re-resolves compound list from source
  - `ManageCampaignResults` — set compound decisions
  - `RefreshFromSources` — re-resolves measurements from Runs (commit `80e9ebed` fixed latent id-preservation constraint bug)
  - `RecomputeChannel` — re-resolve a single channel
  - `CloseCampaign` — e-sig + source_protocols snapshot + optional frozen Collection emit
  - `SupersedeCampaign` — e-sig + supersedes link
  - `GetPublishedCampaign` — read model with batch + molecule details
  - `UpdateCampaignMetadata` — name / description / publishes_collection edits
- [x] SC-Phase-6 — Campaign API routes (15 endpoints) + DAIKON contract JSON-schema test. Routes: create, list-by-project, get, update-metadata, add/update/remove-channel, reseed, refresh, set-result-decision, close, supersede, get-published.
- [x] SC-Phase-7 — Frontend foundation: orval regen for Campaign API client, route scaffold under `(dashboard)/screen-campaign/`, campaign list page with AG Grid.
- [x] SC-Phase-8 — Frontend builder UI: channel configurator panel, compound pivot AG Grid (per-compound rows × per-channel columns), result decision panel, re-resolve trigger, status badge, close-campaign dialog with e-sig confirmation.
- [x] SC-Phase-9 — Frontend closed view + supersede flow. Playwright E2E deferred — `frontend/tests/e2e/screen-campaign.spec.ts.TODO` stub left for follow-up (Playwright setup not present in CI).
- [x] SC-Phase-10 — Documentation: Campaign aggregate section in `docs/domain-model/05-research-organization.md`, spec back-link added, implementation-status updated (this entry).

### Open Follow-ups (carry to next iteration)

- **SavedSearch compound source not wired** — `SavedSearchSource` in `CreateCampaign` and `ReseedCampaign` returns `Failure(ValidationError)`; SavedSearch execution needs to be wired into the resolver before exposing this source kind in the API.
- **E-signature is a stub** — `CloseCampaignCommand.signature_id` is caller-supplied; the frontend generates `crypto.randomUUID()`. Real Sentinel-backed signing not yet implemented.
- **Audit `signed_at` + `closed_by.name`** — `GetPublishedCampaign` has TODOs for resolving the human-readable name via Sentinel and the `signed_at` timestamp from the AuditOperation.
- **`BatchRepository.find_by_ids` missing** — `GetPublishedCampaign` loops `find_by_id` per batch; a bulk lookup method should be added to avoid N+1 queries.
- **Decision-panel notes field ignored** — `SetResultDecision` does not accept a `notes` field; the frontend Decision Panel sends notes that the backend currently silently drops. Extend the use case or remove the notes UI in cleanup.
- **`RecomputeChannel` has no dedicated route** — the use case is wired in DI but no API route exposes it directly; it is callable indirectly via UpdateCampaignChannel re-resolve in practice.
- **Playwright E2E deferred** — `frontend/tests/e2e/screen-campaign.spec.ts.TODO` stub left; requires Playwright infrastructure to be set up in CI first.
- **Latent id-preservation constraint bug FIXED** — `RefreshFromSources` / `RecomputeChannel` / `UpdateCampaignChannel` had a constraint violation when re-resolving; fixed in commit `80e9ebed` with the id-preservation pattern.
