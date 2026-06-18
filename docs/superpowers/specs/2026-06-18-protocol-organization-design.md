# Protocol Organization — Preventing Assay Sprawl by Design

**Status:** Design (approved in brainstorm 2026-06-18) · **Scope:** Phase 1 + Phase 2 · **Branch:** design-7
**Context:** Screening & Assay (BC 02) · **Author:** brainstorm session

---

## 1. Problem

With hundreds of scientists, an assay/protocol catalog rots without anyone intending it to.
Scientists create near-identical protocols without checking for existing ones; per-run details
get baked into protocol names; free-text fields accumulate typos and casing variants. The result
is an unnavigable, duplicate-ridden namespace.

This is not hypothetical. An audit of the lab's external CDD vault (433 protocols, real data,
2026-06-18) shows the end state we must avoid:

- **Granularity overload.** ~433 "protocols" are really ~40–60 assay *methods* run many times.
  The `zBXL_RNAP` family (~35 entries) differs only by compound set (`CPQ811162`, `GSK4329-31`,
  `Janssen`) and timepoint (`Before`/`After`) — those are *runs*, not methods. Same for the
  Malate-dehydrogenase family (~40 entries = one enzyme × organism × detection × direction × mode).
- **Free-text entropy.** The `category` field has **30 distinct values for ~5 real concepts**:
  `Enzyme`(236) / `enzyme`(47) / `Enzyme assay`(2) / `Ezyme`(1, typo); `Whole Cell` in 8 spellings;
  targets (`MbtI`) and detection methods (`Biomol green`) misfiled as categories.
- **Clone-and-forget.** Literal names `Duplicate of …`, `Copy of …`; junk `test-1`, `Test Protocol`.
- **Sort hacks.** `z`/`zBXL` name prefixes so dead protocols sink in the alphabetical list — a
  manual workaround for having no archive mechanism.
- **Readout chaos.** 466 distinct readout names: `% inhibition`(151) / `% Inhibition`(19) /
  `%inhibition`(10); `Tm` / `ΔTm` / `Delta Tm`; doses baked into names (`inhibition-50uM`).

**The CDD vault is the cautionary tale, not the target of this work.** The goal is to design Cellar
so this entropy never accumulates in the first place.

## 2. Goals & non-goals

**Goals**
- Prevent duplicate/near-duplicate protocols *at the point of creation*, intelligently.
- Make reuse (and "log a run of an existing method") the path of least resistance.
- Capture the structured facets scientists currently bake into name strings — without forms.
- Keep the catalog navigable as it scales to thousands of protocols.

**Non-goals / explicit constraints** (from the user)
- **No naming police.** We never dictate or enforce naming conventions.
- **Never block.** Every intelligent surface is suggest-and-let-decide; the user can always proceed.
- **No forced taxonomy.** Vocabulary emerges and converges; it is not decreed up front.
- Not fixing the CDD vault's existing data (that is a separate, optional migration tool — Phase 3).

## 3. Design principles

1. **Capture structure without demanding it.** Extract/ground facets from what scientists already
   type; never hand them a taxonomy form. (Furnas 1987: spontaneous term agreement < 0.20 — forcing
   one canonical label fails 80–90% of the time anyway.)
2. **Make reuse the lowest-friction path.** "Log a run of this method" is one click; "create a new
   protocol" is the deliberate, dup-checked act. Behavior flows to the lowest point of friction.
3. **Suggest, never block; sweep entropy continuously.** A wrong suggestion costs a glance; a block
   costs trust. Above-threshold matches only, capped, dismissible (avoids "cry-wolf" fatigue, the
   documented failure mode of these UIs).

Grounded in prior art: the entity-resolution **blocking + matching** two-stage pipeline (structural
key = precision, fuzzy similarity = recall); the create-time "similar items" UX proven by Stack
Overflow / Quora / GitHub / Jira / Zendesk (all suggest, none block); the **method-vs-run** model
(protocols.io immutable versions + fork-with-lineage; Camunda/Temporal definition-vs-instance);
folksonomy→taxonomy convergence (autocomplete-at-entry is the single most effective consistency
nudge); the BioAssay Ontology (BAO) facet spine used by ChEMBL/PubChem.

## 4. Core concept — the Assay Fingerprint

Every protocol carries a normalized, structural signature derived from its **existing structured
content, not its name string**. The fingerprint is the spine: it is simultaneously the **dedup
blocking key**, the **facet set for browse/filter**, and (in Phase 3) the **embedding input**.

**Phase 1 fingerprint** (derivable today, no new data sources):

```jsonc
// protocols.fingerprint  (JSONB)
{
  "target_ids": ["<uuid>", ...],          // sorted; from protocol_targets
  "protocol_type": "biochemical",         // existing enum
  "readout_kinds": ["ic50", "hill slope", "% inhibition", "r squared"],
                                          // normalized readout-definition names (lower/trim/collapse-ws)
  "readout_data_types": ["dose_response", "numeric"],  // distinct ReadoutDataType set
  "v": 1                                  // fingerprint schema version (for re-derivation)
}
```

**Phase 2 adds grounded facets** (BAO/UniProt/NCBI-taxon via the existing BioPortal client):

```jsonc
{
  "...": "...phase-1 fields...",
  "organism": "NCBITaxon:1773",           // grounded, optional
  "assay_format": "BAO_0000019",          // biochemical/cell-based/...
  "detection": "BAO_0000035",             // fluorescence/luminescence/absorbance/thermal-shift...
  "stage": "hts" | "ic50" | "dsf"         // screening-campaign stage
}
```

**Derivation** is a pure function in the domain layer, `compute_fingerprint(protocol) -> dict`,
recomputed whenever structural fields change (create, add/remove readout, link/unlink target,
change type). It is stored, not computed per query, so similarity search is cheap.

> **Fingerprint ≠ molecular fingerprint.** This is a structural *assay* signature over
> targets + readout schema + type, unrelated to the RDKit/Tanimoto molecular fingerprints in
> `sar_analysis`.

## 5. The flows (UX spec)

### 5.1 Search-first creation + the keystone reroute (Phase 1)

As a scientist types the name/description in the create dialog, a debounced similarity search fires
and surfaces the top matches. When a match shares target(s) + readout schema, the **primary CTA is
"Log a run of this," not "create."**

```
⚡ This looks like a RUN of an existing method
  ◆ RNAP core IC50                              ✓ canonical
    biochemical · RNAP (core) · RiboGreen · IC50
    211 measurements · 18 runs · 6 scientists · steward: AK
    ▶ Log a run of this   (recommended)     ⑂ It's actually a new method
Other similar methods
  · RNAP holo IC50        biochemical · RiboGreen   92% ▸
  · RNAP core HTS assay   biochemical · RiboGreen   88% ▸
        Continue creating new anyway      Cancel
```

Incentive = **comparability** ("211 measurements"). Every escape hatch stays open — nothing blocks.

### 5.2 "Log a run" capture (Phase 1 — already supported by the data model)

Clicking "Log a run" routes to run creation, pre-filling the variation the scientist typed
(`GSK4329-31`, `Before`) as **structured run conditions** — the exact place CDD users had nothing:

```
Log a run · RNAP core IC50  (v3, locked)                       comparable ✓
  Run conditions   (vary per run — not part of the method)
    Compound set   │ GSK4329-31  │  ← parsed from typed text
    Timepoint      │ Before  ▾   │  ← parsed from typed text
  Readouts (inherited): IC50 · Hill slope · R² · % inhibition
        Create run        Back to matches
```

### 5.3 Facets without forms (Phase 2)

If it is genuinely new, we don't show a taxonomy form — we **ground & confirm**. Target/organism/
format/detection are resolved against ontologies (BioPortal) and shown as one-click confirm chips;
the raw text is always preserved alongside the resolved ID + a confidence flag.

```
New method — facets we detected
  Target      ✓ ArgB · ✓ ArgC        ↳ UniProt P9WPZ9          + add
  Organism    ✓ M. tuberculosis · NCBI:1773
  Format      ✓ biochemical · BAO_0000019
  Detection   ✓ NADPH / absorbance
  Category    │ Enzyme ▾ │  ← 286 methods use this; canonical suggestion
  Suggested name  ArgB · ArgC-coupled · NADPH · HTS    use this ▸
        Looks right — create        Edit details
```

### 5.4 Autocomplete-at-entry (Phase 2)

`category` and readout-name inputs autocomplete against the existing normalized vocabulary
(reusing the tag-autocomplete pattern), steering typed input toward existing canonical strings
*before a variant is born* — the single most effective convergence nudge in the literature.

## 6. Architecture & code anchors

All paths under `/Users/sidx/workspace/chem-vault2`. Patterns mirror existing files verbatim.

### 6.1 What already exists (de-risking)

| Capability | Status | Anchor |
|---|---|---|
| Per-run condition values (`{compound_set, timepoint, …}`) | **Exists** — JSONB | `…/screening_assay/models.py:302` (`RunModel.conditions`); `domain/screening_assay/run.py:251` (`Run.create(conditions=)`); `application/screening/create_run.py:47` |
| Protocol owns `ConditionDefinition` schema | Exists | `domain/screening_assay/protocol.py`; `ConditionDefinitionModel` |
| Ontology grounding (free text → BAO/GO term) | Exists | `infrastructure/external/bioportal/client.py`; `OntologySearchService` protocol; `OntologyTerm` VO; `application/screening/search_ontology.py`; `ontology_annotations` on Protocol + Set/Remove use cases |
| `pg_trgm` extension | **Installed** | migration `047_tagging.py:52` |
| Generic AsyncJob (for Phase 3 sweeps) | Exists, tested | `domain/shared/async_job.py`; `application/shared/async_job_runner.py` |
| Query/Command + Result + UoW + auth-guard pattern | Exists | `application/screening/get_protocol.py`, `create_protocol.py` |
| Debounced search hook + autocomplete UI | Exists | `shared/hooks/use-debounce.ts`; `features/workspace-config/hooks/use-ontology-search.ts`; `features/tagging/components/tag-autocomplete.tsx`; `shared/lib/timing.ts` |

### 6.2 What is net-new (Phase 1)

**Domain** — `domain/screening_assay/protocol.py`
- Add `fingerprint: dict | None` to `Protocol.__init__` and `create()` (alongside `ontology_annotations`).
- Add pure module function `compute_fingerprint(protocol) -> dict` (Phase 1 fields).
- Recompute on structural mutations (add/remove readout, link/unlink target, change type) — the
  aggregate already centralizes these via guarded methods; call `compute_fingerprint` there.

**Persistence** — migration `059_protocol_fingerprint.py` (after `058_sar_activity_projections`)
```python
def upgrade() -> None:
    op.add_column("protocols", sa.Column("fingerprint", JSONB(), nullable=True))
    # trigram index for fuzzy name matching (pg_trgm already installed via 047)
    op.execute(
        "CREATE INDEX ix_protocols_name_trgm ON protocols "
        "USING gin (name gin_trgm_ops)"
    )
    # GIN on fingerprint->target_ids for structural blocking
    op.execute(
        "CREATE INDEX ix_protocols_fp_targets ON protocols "
        "USING gin ((fingerprint -> 'target_ids'))"
    )
```
- Add `fingerprint` to `ProtocolModel` (`…/screening_assay/models.py`, after `recommended_hit_criteria`)
  and to the repository's `_to_model` / `_to_domain` mapping.
- One-time backfill of `fingerprint` for existing rows (small N; inline data migration or a thin script).

**Application** — `application/screening/find_similar_protocols.py` (mirror `get_protocol.py`)
- `FindSimilarProtocolsQuery(Query)` accepting a **draft signature** (the create case — the protocol
  does not exist yet): `workspace_id`, `name`, `protocol_type`, `target_ids`, `readout_names`,
  `threshold`, `limit`. (A `reference_protocol_id` variant is added in Phase 3 for hygiene/version.)
- `FindSimilarProtocols` use case: `require_workspace_role(auth, "viewer")` + `require_same_workspace`;
  returns `Result[list[ProtocolMatch], DomainError]` where `ProtocolMatch = {protocol summary,
  score, shared: {targets, readouts}, is_run_candidate: bool}`.
- `is_run_candidate` = shares ≥1 target AND readout-schema overlap ≥ τ — this drives the keystone
  "Log a run" CTA vs a plain "similar" listing.

**Repository** — `…/screening_assay/protocol_repository.py` + domain `repository.py` protocol
- `find_similar(workspace_id, *, target_ids, readout_names, name, type, limit) -> list[(summary, score, shared)]`.
- **Two-stage, in SQL** (not the N²-Python loop): (1) *block* — candidates = protocols sharing ≥1
  `target_id` (GIN on `fingerprint->target_ids`) OR `similarity(name, :name) > k` (trigram index)
  OR same type with ≥1 shared readout; (2) *score* the small candidate set — weighted Jaccard over
  {targets (high weight), readout_kinds, type} + `pg_trgm` name similarity, normalized to 0–1.

**Interface** — `interface/routes/protocols.py` + `interface/dependencies/_screening.py`
- `POST /api/v1/protocols/similar` (body = draft signature; POST because the protocol doesn't exist
  and the body is composite). Returns `list[SimilarProtocolResponse]` with `score`, `is_run_candidate`,
  `shared`, and summary fields (name, type, status, targets, run_count, last_run_date — reuse
  `list_protocol_summaries` stats).
- `FindSimilarProtocolsDep = Annotated[FindSimilarProtocols, Depends(_get_use_case(...))]`.

**DI** — `infrastructure/di/_screening.py`: register `FindSimilarProtocols` per-resolve-UoW
(mirror `_set_ontology_annotation`).

**Frontend**
- `hooks/use-protocols.ts` (or new `use-similar-protocols.ts`): `useSimilarProtocols(draft)` mirroring
  `useOntologySearch` — `useDebounce` (`SEARCH_DEBOUNCE_MS`), `enabled` on `name.length >= SEARCH_MIN_QUERY_LEN`,
  POSTs the draft signature. Add `SIMILAR_PROTOCOLS_KEY` to `query-keys.ts`.
- `components/create-protocol-dialog.tsx`: insert `<SimilarProtocolsPanel>` right after the name
  input (~line 414); reads `form.watch("name")`, `form.watch("type")`, `form.watch("target_ids")`,
  `form.watch("readout_definitions")`. Render ≤5 above-threshold matches; `is_run_candidate` →
  prominent "Log a run of this" that closes the create dialog and opens run-create pre-filled
  (existing `useCreateRun` + run-create route).
- Light client-side throttle/cap to avoid cry-wolf: only show when ≥1 match ≥ τ; collapse on dismiss.

### 6.3 Net-new (Phase 2)

- **Facet slots on the fingerprint** (`organism`, `assay_format`, `detection`, `stage`) — extend
  `compute_fingerprint` + the Protocol aggregate's `ontology_annotations` slots (the slot mechanism
  already exists; we add named slots for these facets and surface them in create).
- **Grounded facet chips** — new create-dialog section calling the existing `useOntologySearch`
  (BioPortal) scoped per facet (`BAO` for format/detection, `NCBITaxon` for organism); one-click
  assign → `SetOntologyAnnotation`. Raw text preserved + resolved ID + confidence (ChEMBL
  `standard_flag` pattern).
- **Autocomplete-at-entry** for `category` and readout names — reuse `tag-autocomplete.tsx` against
  a normalized value source (existing tag/category values, deduped via `pg_trgm`).
- **Provenance-aware name suggestion** — derive a structured default name from the fingerprint facets;
  one-click accept, fully editable, never enforced.
- **Open decision (flagged):** *automatic* extraction of all facets from a free-text sentence
  (mockup 5.3's "we detected") requires an LLM/NER pass. Phase 2 ships grounded chips + autocomplete
  **without** an LLM (fully in-house). LLM-assisted extraction is a later increment pending a
  model/runtime decision (would align with the local-model lean in §7).

## 7. Phase 3 (deferred — committed direction documented)

Not built now, but Phase 1's similarity interface is designed to accept these additively.

- **Embedding recall channel — committed: local model, app-side vectors.** In-process
  `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) embedding a serialized fingerprint signature
  (Ditto-style `COL name VAL … COL target VAL …`); embeddings stored as JSONB/`float[]` on
  `protocols`; cosine computed app-side (or via a small SQL function) over the *blocked* candidate
  set. **No external API, no custom Postgres image** (the rdkit cartridge ships only `rdkit` +
  `pg_trgm`; `vector` is not installable there, and at a few-thousand rows native ANN is unnecessary).
  Backfill/recompute via a new **AsyncJob** type (`protocol_embedding_backfill`) on the existing rail.
  Hybrid scoring = structural (precision) + trigram (codes) + embedding (semantic recall), fused with
  weighted RRF. Revisit pgvector-via-custom-image only at ~100k+ protocols.
- **Background dedup/hygiene sweep** — `protocol_dedup_sweep` AsyncJob clustering near-duplicates +
  near-duplicate `category`/readout values, surfaced to a steward for human-in-the-loop merge.
  Staleness → archive (replaces the `z` sort-hack). Usage-based ranking floats canon up.
- **Faceted library view** — facet sidebar + grouped list. **AG Grid Community cannot row-group**
  (confirmed), so this is a custom component, not a grid config.
- **Retroactive de-confliction tool** — point at an imported mess (e.g. 433 CDD protocols) → proposed
  canonical methods + run re-filing.

## 8. Testing strategy

Per the project's layer order (Domain → Persistence → Application → API → UI):

- **Domain (unit):** `compute_fingerprint` is pure — table-driven tests over the CDD-derived cases
  (RNAP family → same fingerprint modulo run conditions; MDH detection variants → distinct
  `readout_kinds`; `Duplicate of X` → high name-trigram but identical structural fingerprint).
- **Persistence (integration):** migration applies; trigram + GIN indexes used (EXPLAIN); `find_similar`
  blocking returns the right candidate set; fingerprint round-trips through the mapper.
- **Application (unit):** `FindSimilarProtocols` auth guards; `is_run_candidate` logic; threshold
  behavior; draft-signature (no reference protocol) path.
- **API:** `POST /protocols/similar` shape, workspace scoping, pagination/cap.
- **UI/E2E:** typing a near-duplicate surfaces the panel (debounced, ≤5, above-threshold); "Log a run"
  opens run-create pre-filled with parsed conditions; "create new anyway" always works (never blocked).

## 9. Risks & open decisions

1. **No vector infra today** — accepted; Phase 1+2 need none. Phase 3 commits to local-model app-side
   vectors (§7), avoiding both an external API and a custom DB image.
2. **Suggestion fatigue** — mitigated by above-threshold-only, ≤5 cap, dismissible, structural
   precision (not pure text). Threshold τ tunable; start conservative.
3. **"Canonical/steward/usage" surfaces** shown in mockups are **Phase 3** (need a stewardship +
   usage-count model). Phase 1 shows run_count/last_run_date (already available) but not "canonical"
   badges. Keep the create panel honest about what it knows.
4. **LLM facet extraction** (mockup 5.3 auto-detect) — open; Phase 2 ships grounded chips +
   autocomplete without an LLM. Decide a local NER/LLM path later (consistent with §7 lean).
5. **Condition parsing** — pre-filling `compound_set`/`timepoint` from typed text in 5.2 is
   best-effort; if parsing is uncertain, leave the run-condition fields blank for the scientist to
   fill. Never guess silently into a locked field.

## 10. Out of scope (this spec)

Fixing the CDD vault data; the faceted library UI; stewardship/canonical-badge model; embeddings and
the dedup sweep (all Phase 3); any naming enforcement; round-tripping back to CDD.
