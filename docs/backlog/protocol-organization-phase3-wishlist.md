# Protocol Organization — Phase 3 wishlist (deferred)

**Status:** deferred / wishlist · **Decided:** 2026-06-19 · **Branch context:** design-7

Phases 1–2 (create-time similarity + facets-without-forms) and **Phase 3 feature 1 (faceted library view)** are done and shipped on design-7. Together they deliver the spec's core mission — *prevent assay sprawl by design*: duplicates are flagged at creation, reuse ("log a run of this method") is the low-friction path, facets are captured without forms, and the catalog is navigable via the faceted Library view.

The items below were scoped in the design (`docs/superpowers/specs/2026-06-18-protocol-organization-design.md` §7) but are **deliberately not built** — they address *existing-mess cleanup* and *scale-time recall*, both genuinely deferrable. Pick any up later as its own brainstorm → spec → plan → build cycle.

## Deferred Phase-3 features

1. **Embedding recall channel** — in-process `sentence-transformers` (`all-MiniLM-L6-v2`) over a serialized fingerprint, app-side cosine on the blocked candidate set, `protocol_embedding_backfill` AsyncJob, hybrid RRF fusion.
   - *Why deferred:* marginal recall benefit at the current catalog size (pg_trgm + facet-Jaccard already cover the create-time keystone); commits the backend image to a multi-GB **torch** dependency. Real payoff is at thousands of protocols.
   - *Gate before starting:* settle the torch/sentence-transformers dependency decision (image size, deploy, the rdkit base image ships only rdkit+pg_trgm).

2. **Dedup / hygiene sweep** — `protocol_dedup_sweep` AsyncJob clustering near-duplicate protocols + near-dup category/readout values for steward review; staleness → **archive** (replaces the `z`-prefix sort hack).
   - *Why deferred:* the create-time prevention already stops *new* sprawl; the sweep cleans *existing* accumulation. Introduces a new archive mechanism (new `ProtocolStatus` value / migration), so it's its own cycle.

3. **Retroactive de-confliction tool** — one-shot: point at an imported mess (e.g. the 433-protocol CDD vault) → proposed canonical methods + run re-filing.
   - *Why deferred:* operational, only needed if/when that mess is imported into Cellar. Most naturally built after the dedup sweep (shares clustering logic).

*Explicitly out of scope (per spec §6.3):* LLM/NER auto-extraction of facets from free-text sentences — needs a model/runtime decision.

## Feature-1 (faceted library) polish — non-blocking

From the final whole-feature review (opus, merge-ready). None block use; revisit in a polish pass:

- **Project-switch retired pre-exclusion:** the "pre-exclude retired" default is computed once at mount (spec D7). Switching the project filter *inside* Library view to a project whose set newly includes retired protocols won't re-apply the pre-exclusion. Fix candidate: key `ProtocolLibraryView` by project so it remounts (also resets facets on project change — confirm that's the desired UX).
- **Row virtualization:** `GroupedProtocolList` renders the full grouped list into the DOM (no virtualization, unlike AG Grid). Fine at the spec's hundreds–thousands; add virtualization (the `@tanstack/react-virtual` pattern in `sar-analysis/components/scaffold-groups-list.tsx`) as the first move if a workspace pushes into many-thousands.
- **Minor polish:** `ChevronDown` doesn't rotate on Collapsible open/close (facet-sidebar + grouped-list); a 1-line ARIA-APG comment already documents the intentional `role="checkbox"` button warn; extra edge tests would be nice (tie-break / empty-list / null-ontology / organism dimension / count-badge assertion); `v as GroupBy` / `v as View` are unchecked but safe closed-enum casts.

## Pointers
- Spec: `docs/superpowers/specs/2026-06-18-protocol-organization-design.md` (§7 Phase 3)
- Feature-1 spec/plan: `docs/superpowers/specs/2026-06-19-protocol-faceted-library-design.md`, `docs/superpowers/plans/2026-06-19-protocol-faceted-library.md`
- Ledger (authoritative task/review trail): `.git/sdd/progress.md`
- Handoff: `docs/superpowers/HANDOFF-2026-06-18-protocol-organization.md`
