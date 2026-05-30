# chemcellar User Documentation Site — Design

> Status: approved (brainstorm). Date: 2026-05-30. Branch: `docs1`.
> Audience for the *site*: scientists & biochemists (primary), portfolio managers, students new to pharma.
> This spec covers a **user-facing** docs site — distinct from the internal dev docs in `docs/` and from
> Sentinel's API-oriented docs.

## 1. Goals & non-goals

**Goals**
- A polished, user-focused documentation website for chemcellar ("Cellar").
- Teach **basic concepts** from scratch so students/newcomers can follow (cheminformatics, structures, assays, dose-response, SAR, compliance).
- Task-oriented **how-to guides** for every shipped feature.
- **Interactive widgets** that let readers play with real chemistry (render structures, calculate properties, explore dose-response curves, plate heatmaps, similarity).
- Three audience on-ramps (scientist / portfolio manager / student) into one shared body of content.

**Non-goals**
- API reference / SDK docs (that is Sentinel's space and the OpenAPI spec).
- Documenting **unbuilt Phase-3 features** (ELN, Markush/MMP/full SAR, Formulation & stability) as how-to guides — these appear only on a **Roadmap** page.
- Real UI screenshots in this pass — screenshot spots are marked with placeholders.

## 2. Tooling & location

- **Nextra (Next.js + MDX)** in a new top-level **`docs-site/`** folder.
- Own `package.json` (pnpm). Pin the Next.js version Nextra officially supports — **independent of the app's Next 16** to avoid bleeding-edge incompatibility. The docs site does not import from `frontend/` at build time; it **ports** the small set of chemistry helpers it needs.
- Theme: Nextra docs theme, dark/light toggle, full-text search, mermaid diagrams, copy-button code. Simple "chemcellar" text wordmark (no logo assets exist yet).
- Client-side chemistry: `@rdkit/rdkit` (WASM), `ketcher-*` (embeddable editor), `plotly.js` + `react-plotly.js` — same versions as `frontend/package.json`.

## 3. Audience strategy

One body of content; three **"Start here" on-ramp pages** that route readers:
- **Scientist / biochemist** → registration, screening, analysis guides.
- **Portfolio manager** → projects, collections, campaigns, export/reporting.
- **Student / newcomer** → Concepts primers first, then a guided "first molecule" walkthrough.

## 4. Information architecture (page inventory)

Paths are relative to `docs-site/pages/` (or `content/` per Nextra version). Each leaf is one `.mdx`.

### Introduction / on-ramps
- `index.mdx` — what chemcellar is; the big-picture workflow (register → organize → screen → analyze → report); links to on-ramps.
- `for-scientists.mdx`, `for-portfolio-managers.mdx`, `for-students.mdx`

### Getting Started
- `getting-started/index.mdx` — overview
- `getting-started/logging-in.mdx` — Sentinel auth, choosing a workspace
- `getting-started/navigating.mdx` — UI tour (nav, search, dashboards)
- `getting-started/first-molecule.mdx` — end-to-end "register your first molecule" walkthrough

### Concepts (primers — student-focused)
- `concepts/index.mdx` — cheminformatics & what a compound registry is
- `concepts/chemical-structures.mdx` — SMILES, InChI, InChIKey, canonicalization, stereochemistry, tautomers *(embeds `SmilesAnnotator`, `StructureViewer`)*
- `concepts/molecular-properties.mdx` — MW, logP, TPSA, HBD/HBA; computed descriptors vs. predicted properties *(embeds `PropertyCalculator`)*
- `concepts/registration-and-identity.mdx` — deduplication, registration numbers, why identity matters
- `concepts/undisclosed-molecules.mdx` — disclosure & merge lifecycle
- `concepts/batches-and-samples.mdx` — batch vs. sample, lots, amount & concentration
- `concepts/assays-and-screening.mdx` — protocols, plates, wells, readouts, targets *(embeds `PlateHeatmapDemo`)*
- `concepts/dose-response.mdx` — IC50/EC50, curves, Hill slope, qualifiers, potency *(embeds `DoseResponseExplorer`)*
- `concepts/sar-and-similarity.mdx` — fingerprints, Tanimoto, substructure, scaffolds *(embeds `SimilarityDemo`)*
- `concepts/projects-collections-campaigns.mdx` — organizing research
- `concepts/compliance.mdx` — audit trail, e-signatures, 21 CFR Part 11, data lock

### Guides (shipped features only)
- Registration: `guides/registration/{index,drawing-structures,bulk-registration,identifiers,disclosure-and-merge,synthesis-routes}.mdx`
- Search: `guides/search/{index,structure-search,similarity-search,saved-searches}.mdx`
- Inventory: `guides/inventory/{index,storage,sample-requests,shipments,synthesis-requests}.mdx`
- Screening: `guides/screening/{index,plate-templates,runs,plate-data,dose-response,approval-and-data-lock}.mdx`
- Research Org: `guides/research-organization/{projects,collections,screen-campaigns}.mdx`
- Import/Export: `guides/import.mdx` (external platforms / data sources), `guides/export.mdx` (CSV/XLSX/SDF, plate layouts), `guides/attachments.mdx`

### Administration
- `administration/{index,workspace-config,organizations,controlled-vocabularies,data-sources,users-and-roles,admin-delete}.mdx`
  (`users-and-roles` links out to the Sentinel docs).

### Reference
- `reference/glossary.mdx` — large, student-focused glossary (all key terms)
- `reference/chemistry-standards.mdx` — canonicalization/normalization standards (ChEMBL/PubChem/CAS alignment), registration business rules
- `reference/faq.mdx`
- `reference/roadmap.mdx` — "Coming soon": ELN, Markush/MMP/full SAR, Formulation & stability

## 5. Interactive widgets

React components in `docs-site/components/`, embedded in MDX. Each ports/reuses logic from `frontend/`:

| Widget | Does | Reuses |
|---|---|---|
| `StructureViewer` | Input/select SMILES → render 2D structure | `rdkit-loader.ts`, `structure-renderer.tsx` |
| `PropertyCalculator` | SMILES → MW/logP/TPSA/HBD/HBA live | RDKit.js descriptors |
| `DoseResponseExplorer` | Drag IC50 / Hill slope → live 4-param curve | Plotly; port dose-response chart logic |
| `PlateHeatmapDemo` | Interactive 96/384-well plate, hover wells | SVG heatmap pattern from screening UI |
| `SimilarityDemo` | Tanimoto between two structures | RDKit.js Morgan fingerprints |
| `SmilesAnnotator` | Hover parts of a SMILES string to learn syntax | static + RDKit.js render |

All widgets must be **client-only** (`'use client'` / dynamic import, `ssr: false`) because RDKit/Ketcher/Plotly need the browser. A shared `RdkitProvider` loads the WASM module once.

## 6. Content conventions (style guide — produced by scaffold)

- Voice: clear, friendly, second person ("you"). Define every domain term on first use; link to the glossary.
- Each guide opens with **who it's for** + **what you'll accomplish**, then numbered steps.
- Use Nextra callouts (note/tip/warning) for tips and 21 CFR/data-lock cautions.
- Mark UI captures with `> 📷 *Screenshot: <description>*` placeholders.
- Embed widgets with a one-line intro and a "try it" caption.
- Never reference competitor product names (code integration names OK). Use "external screening platform" phrasing.

## 7. Orchestration plan (multi-agent workflow)

1. **Scaffold (1 agent, barrier):** create `docs-site/` Nextra project (own `package.json`, theme, search, mermaid), the nav/`_meta` skeleton for the full IA, a `STYLE_GUIDE.md`, a `WIDGETS.md` embed-reference, the `RdkitProvider`, and **stub** widget components with final prop signatures so writers can embed them.
2. **Fan-out (parallel):**
   - ~15 **content-writer agents**, one per page cluster (each writes several MDX files). Each receives the style guide, the widget embed reference, and the relevant `docs/domain-model/*.md` as source-of-truth. **Shipped features only.**
   - 6 **widget-builder agents**, one per widget, implementing against the stub signatures.
   - File paths are disjoint, so no write conflicts; no worktree isolation needed.
3. **Stitch & verify (1 agent, barrier):** finalize all `_meta` nav files, run `pnpm install && pnpm build`, fix broken links/imports, run a completeness pass against this inventory, report what's missing.

## 8. Risks & mitigations

- **Nextra vs. Next 16:** mitigated by pinning the docs-site to a Nextra-supported Next version, isolated from the app.
- **RDKit WASM in MDX/SSR:** all widgets client-only via dynamic import; single shared loader.
- **Scope/token volume:** ~45 pages + 6 widgets. Clustered fan-out keeps agent count ~23. Roadmap-stub policy avoids writing throwaway guides for unbuilt features.
- **Documenting unbuilt UI:** content writers are restricted to shipped features (per `docs/implementation-status.md`); Phase-3 items live only on the Roadmap page.
