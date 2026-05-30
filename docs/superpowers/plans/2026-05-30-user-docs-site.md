# chemcellar User Docs Site — Implementation Plan

Spec: `docs/superpowers/specs/2026-05-30-user-docs-site-design.md`
Execution: multi-agent Workflow (scaffold → parallel content+widgets → stitch/verify).

## Phase 1 — Scaffold (1 agent, barrier)
Create `docs-site/`:
- Nextra (Next.js + MDX) project, own `package.json` pinned to a Nextra-supported Next version.
- Docs theme: dark/light, search, mermaid, copy code, "chemcellar" wordmark.
- Full nav/`_meta` skeleton matching the IA (empty page placeholders).
- `docs-site/STYLE_GUIDE.md` — voice, page templates, callouts, screenshot placeholder convention, glossary-link rule, no-competitor-names rule.
- `docs-site/WIDGETS.md` — final prop signatures + import paths + usage snippet for each widget.
- `components/RdkitProvider.tsx` + stub widget components (`StructureViewer`, `PropertyCalculator`, `DoseResponseExplorer`, `PlateHeatmapDemo`, `SimilarityDemo`, `SmilesAnnotator`) with final signatures, client-only.
- Deps: `@rdkit/rdkit`, `ketcher-*`, `plotly.js`, `react-plotly.js` matched to `frontend/package.json`.

## Phase 2 — Fan-out (parallel)
### Content writer clusters (~15 agents) — shipped features only
1. Home + on-ramps (`index`, `for-scientists`, `for-portfolio-managers`, `for-students`)
2. Getting Started (4 pages)
3. Concepts: structures & properties (index, chemical-structures, molecular-properties)
4. Concepts: identity & lifecycle (registration-and-identity, undisclosed-molecules)
5. Concepts: inventory & screening (batches-and-samples, assays-and-screening, dose-response)
6. Concepts: analysis/org/compliance (sar-and-similarity, projects-collections-campaigns, compliance)
7. Guides/Registration (6 pages)
8. Guides/Search (4 pages)
9. Guides/Inventory (5 pages)
10. Guides/Screening (6 pages)
11. Guides/Research-Organization (3 pages)
12. Guides/Import + Export + Attachments (3 pages)
13. Administration (7 pages)
14. Reference: Glossary + Chemistry standards
15. Reference: FAQ + Roadmap

Each agent gets: `STYLE_GUIDE.md`, `WIDGETS.md`, the matching `docs/domain-model/*.md` source, and `docs/implementation-status.md` (to stay within shipped features).

### Widget builders (6 agents)
One per widget, implemented against Phase-1 stub signatures, porting from `frontend/src/shared/lib/rdkit/*` and `chemistry/*`.

## Phase 3 — Stitch & verify (1 agent, barrier)
- Finalize all `_meta` nav files.
- `pnpm install && pnpm build` in `docs-site/`; fix broken imports/links.
- Completeness pass vs. the IA inventory; report gaps.

## Acceptance
- `docs-site/` builds cleanly.
- Every IA page exists with real content (no TODO bodies).
- All 6 widgets render client-side without SSR errors.
- No how-to guides for unbuilt features; Roadmap lists them.
