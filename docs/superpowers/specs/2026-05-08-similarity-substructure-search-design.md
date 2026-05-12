# Similarity & Substructure Search — Design

**Date:** 2026-05-08
**Status:** Approved (brainstorming) → ready for implementation plan
**Scope:** Surgical upgrade of similarity + substructure search on the existing RDKit cartridge, plus a pluggable fingerprint-algorithm registry. Dev mode — no backward compatibility required for existing data or saved searches.

---

## Background

The current implementation already runs on the RDKit Postgres cartridge with a Morgan `bfp` column and a GiST index. It works, but has gaps the literature (Riniker/Landrum 2013, Probst 2018, Capecchi/Reymond 2020, the 2025 pretrained-embedding benchmarks) and operational reading make obvious:

- Morgan is computed with cartridge `morganbv_fp(...)` which doesn't expose `useChirality`. Stereoisomers collide in similarity scores even though InChIKey-based registration treats them as distinct molecules.
- User SMARTS is fed to `mol_from_smarts` without `mol_adjust_query_properties` — silent aromaticity-perception bugs lurk.
- No support for tautomer-aware (generalized) substructure matching (`@>>`).
- No support for Tversky similarity (the asymmetric metric that makes "find big molecules containing this fragment" actually work).
- No scaffold-hopping / pharmacophore-flavored similarity (FCFP).
- Four other fingerprints (RDKit topological, MACCS, AtomPair, TopologicalTorsion) are computed in Python on every registration and never persisted or queried — pure CPU waste.
- Hardcoded `LIMIT 100` on similarity results; should use the existing keyset cursor pagination.

The literature, summarized opinionatedly: in 2026, **Morgan/ECFP4 + Tanimoto remains the gold standard for production small-molecule similarity**. Every "we beat ECFP" paper either wins by 2–4 percentage points or wins on out-of-distribution data (peptides, metabolites). The one fingerprint genuinely worth offering as a secondary lens is **FCFP**, because pharmacophore-style abstraction finds bioisosteric matches Morgan misses. Learned embeddings (ChemBERTa, MolFormer, etc.) tie or lose to ECFP4 on every recent benchmark. **Tversky(α=1, β=0)** is a free win for fragment-in-target queries. Don't add FPSim2 / pgvector / vector DBs — the cartridge handles 1–5M comfortably and they'd be a second source of truth.

## Goals

1. Fix the latent bugs (chirality, SMARTS hygiene).
2. Add three opinionated user-facing search modes that cover ~95% of medicinal-chemistry use cases.
3. Introduce a pluggable `FingerprintAlgorithm` registry so adding MAP4 / a learned embedding later is a one-file change.
4. Drop dead-weight fingerprints.
5. Replace `LIMIT 100` with proper threshold-gated cursor pagination.

## Non-goals

- FPSim2 / pgvector / Milvus integration. Defer until we cross ~5M registrations.
- Learned embeddings (ChemBERTa, MolFormer). Revisit only if users specifically ask for scaffold-hopping at <0.4 Tanimoto where FCFP isn't enough.
- 3D similarity / shape matching. Out of scope for this work.
- A new bounded context. The existing chemical_registration + sar_analysis split is fine.

## Registration-path safety

This is the only constraint where getting it wrong is dangerous, so it's pinned first.

**Registration deduplication is and remains InChIKey-only.** It does not consult any fingerprint. Verified at:

- `application/chemical_registration/register_molecule.py:269-272` — `find_by_inchi_key`
- `application/chemical_registration/disclosure_service.py:157-159` — same call
- `infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py:193-205` — exact-match SQL
- `infrastructure/rdkit/standardizer.py:135-139` — InChIKey is generated stereo-aware via RDKit's `MolToInchi` → `InchiToInchiKey`

Flipping Morgan from `useChirality=False` → `useChirality=True` therefore has zero effect on dedup. This is asserted by an explicit regression test in §6.

---

## Architecture

Three-layer split following the existing DDD/clean-architecture pattern.

### Domain layer (`domain/sar_analysis/`)

```python
# fingerprint_algorithm.py
class FingerprintAlgorithm(Protocol):
    name: str                # "morgan", "fcfp"
    column_name: str         # "morgan_bfp", "fcfp_bfp" — the bfp column to query
    cartridge_query_fn: str  # e.g. "morganbv_fp" — wraps the query molecule in SQL

# similarity_metric.py
class TanimotoMetric: ...
class TverskyMetric:
    alpha: float
    beta: float
SimilarityMetric = TanimotoMetric | TverskyMetric

# search_modes.py
class SearchMode(StrEnum):
    SIMILAR = "similar"
    SCAFFOLD_HOP = "scaffold_hop"
    FRAGMENT_IN_TARGET = "fragment_in_target"

MODE_DEFAULTS: dict[SearchMode, ModeConfig] = {
    SearchMode.SIMILAR:            ModeConfig(algorithm="morgan", metric=TanimotoMetric(), threshold=0.7),
    SearchMode.SCAFFOLD_HOP:       ModeConfig(algorithm="fcfp",   metric=TanimotoMetric(), threshold=0.55),
    SearchMode.FRAGMENT_IN_TARGET: ModeConfig(algorithm="morgan", metric=TverskyMetric(1.0, 0.0), threshold=0.7),
}
```

The domain layer holds metadata + the mode→algorithm mapping. It does **not** import RDKit. Use cases compose searches by referencing algorithm names; infrastructure resolves them through the registry.

### Infrastructure layer (`infrastructure/rdkit/fingerprints/`)

```
registry.py        # FingerprintRegistry — Lagom-injected; dict[str, FingerprintAlgorithm]
morgan.py          # MorganAlgorithm: useChirality=True, radius=2, fpSize=2048
fcfp.py            # FCFPAlgorithm: featMorgan via cartridge featmorganbv_fp, radius=2, fpSize=2048
```

The registry is exposed via DI. Adding MAP4 later is one new file plus one DI registration line.

### Persistence layer (`infrastructure/persistence/sqlalchemy/chemical_registration/`)

`search_query_composer.py` gains a `_compose_similarity` helper that takes `(algorithm, metric, threshold, smiles)` and emits the right SQL fragment. Examples:

- Morgan + Tanimoto, t=0.7:
  ```sql
  morgan_bfp % morganbv_fp(mol_from_smiles(:q))
  ORDER BY tanimoto_sml(morgan_bfp, morganbv_fp(mol_from_smiles(:q))) DESC
  ```
- FCFP + Tanimoto:
  ```sql
  fcfp_bfp % featmorganbv_fp(mol_from_smiles(:q), 2)
  ORDER BY tanimoto_sml(fcfp_bfp, featmorganbv_fp(mol_from_smiles(:q), 2)) DESC
  ```
- Morgan + Tversky(1, 0):
  ```sql
  tversky_sml(morgan_bfp, morganbv_fp(mol_from_smiles(:q)), 1.0, 0.0) >= :t
  ORDER BY tversky_sml(morgan_bfp, morganbv_fp(mol_from_smiles(:q)), 1.0, 0.0) DESC
  ```

`rdkit.tanimoto_threshold` is set per-query (in the same transaction) for the Tanimoto `%` operator path.

**Tversky index caveat:** the cartridge's Tversky support uses GUCs (`rdkit.tversky_threshold`, plus implicit α/β tied to the `?` operator) which makes per-query α/β parameterization awkward. The simplest correct shape — `tversky_sml(...) >= :t` in WHERE — does **not** hit the GiST index and will table-scan the bfp column. This is acceptable at current scale but should be benchmarked during implementation; if the FRAGMENT_IN_TARGET path is too slow on the demo dataset, fall back to a two-step plan (Tanimoto-prefilter at a low threshold, then Tversky re-rank) rather than fighting the cartridge's GUC contract.

For substructure:
- Every user-supplied SMARTS / SMILES query goes through `mol_adjust_query_properties(mol_from_smarts(:s))` before matching.
- Generalized matching uses `mol_to_xqmol(...)` + `@>>` instead of `@>`.

### Interface layer (`interface/api/v1/search/`)

Single endpoint `POST /search/execute` keeps its envelope but the structure clause becomes a Pydantic discriminated union (see API §). New small endpoint `GET /search/algorithms` returns the registry contents so the frontend renders mode choices dynamically.

---

## Schema & migration

One Alembic migration. No backfill of existing data — dev mode, demo loaders rebuild on next run.

1. **Add column** `fcfp_bfp bfp` on `molecules`, nullable.
2. **Create GiST index** `ix_molecules_fcfp_bfp ON molecules USING gist (fcfp_bfp)`.
3. **Drop the achiral cartridge trigger** `compute_morgan_bfp` from migration 001.
4. **Stop computing `morgan_bfp` in the database trigger.** Application-side: `StructureProcessor.process()` computes `morgan_bfp` bytes in Python with `useChirality=True` and writes them as part of the molecule INSERT.
5. **Add a small cartridge trigger for FCFP only** — `featmorganbv_fp(mol_from_smiles(NEW.smiles), 2)`. FCFP doesn't need stereo expressivity (pharmacophore abstraction is intrinsically achiral-flavored), so cartridge-trigger compute is fine.

Rationale for the asymmetry (Python for Morgan, trigger for FCFP): the cartridge `morganbv_fp` doesn't expose `useChirality`. Computing in Python is the only way to get stereo-aware Morgan into a `bfp` column. FCFP has no equivalent need, so the simpler trigger pattern stays.

**Cleanup of dead-weight fingerprints (same migration or sibling):**

- Delete from `infrastructure/rdkit/fingerprint_generator.py`: `_rdkit_gen`, `_atom_pair_gen`, `_torsion_gen`, MACCS computation. Keep only Morgan + FCFP generators.
- Replace the `fingerprints: dict[str, list[int]]` field on `ProcessedStructureDTO` with a typed `Fingerprints` value object (`morgan: bytes, fcfp: bytes`).
- Drop the `fp_rdkit` LargeBinary column from `molecules` (currently nullable and unused).

---

## API surface

### `POST /api/v1/search/execute`

Structure clause becomes a discriminated union. The rest of the request envelope (saved-search-id mode, pagination cursor, protocol_columns enrichment) is unchanged.

```python
class ExactMatch(BaseModel):
    kind: Literal["exact"]
    smiles: str

class SubstructureMatch(BaseModel):
    kind: Literal["substructure"]
    smiles_or_smarts: str
    generalized: bool = False  # @>> + mol_to_xqmol when True

class SimilarityMatch(BaseModel):
    kind: Literal["similarity"]
    smiles: str
    mode: SearchMode                       # default UI sends only this + threshold
    threshold: float | None = None         # None → mode default
    # Power-user overrides — UI does not send these:
    algorithm: str | None = None           # "morgan" | "fcfp"
    metric: MetricSpec | None = None       # tanimoto | tversky(α, β)

StructureClause = Annotated[
    ExactMatch | SubstructureMatch | SimilarityMatch,
    Field(discriminator="kind"),
]
```

If `mode` is sent and `algorithm`/`metric` are also sent, the explicit overrides win (with a warning logged). If only `mode` is sent, the registry-resolved defaults are used.

### `SimilarityScore` on responses

Each row's similarity score now carries which algorithm + metric produced it:

```python
class SimilarityScore(BaseModel):
    value: float
    algorithm: str   # "morgan" | "fcfp"
    metric: str      # "tanimoto" | "tversky(1.0,0.0)"
```

### `GET /api/v1/search/algorithms`

Returns the registry contents. Frontend renders mode radios from this — no FE-side hardcoded list.

```json
{
  "modes": [
    {"name": "similar", "label": "Similar", "description": "Find molecules with the same overall shape",
     "default_threshold": 0.7, "algorithm": "morgan", "metric": "tanimoto"},
    {"name": "scaffold_hop", "label": "Scaffold hop", "description": "Looser match — finds bioisosteric replacements",
     "default_threshold": 0.55, "algorithm": "fcfp", "metric": "tanimoto"},
    {"name": "fragment_in_target", "label": "Contains my fragment", "description": "Big molecules that contain features of this query",
     "default_threshold": 0.7, "algorithm": "morgan", "metric": "tversky(1.0,0.0)"}
  ],
  "algorithms": [
    {"name": "morgan", "description": "Circular topological FP (ECFP4-equivalent), stereo-aware"},
    {"name": "fcfp", "description": "Pharmacophore-flavored circular FP"}
  ]
}
```

### Pagination

The hardcoded `LIMIT 100` is removed. Similarity uses the same keyset cursor pagination (`cursor = molecule_id`) already used elsewhere. The threshold gates recall; cursor handles size.

### Saved searches

The query dict gains a required `mode` field for similarity clauses. Dev mode — existing demo saved searches are regenerated by demo-loader, no migration shim.

---

## UI

Two changes only. No new pages.

### `compound-search-bar.tsx` (quick search)

The existing "name / exact / substructure / similarity" type dropdown stays. Selecting "similarity" silently maps to `SearchMode.SIMILAR` with the registry's default threshold. No new UI controls in the quick search.

### `search-query-builder.tsx` — structure section

**Similarity tab:**

```
[ Ketcher / SMILES box                              ]

Mode:  ( ) Similar              "Find molecules with the same overall shape"
       ( ) Scaffold hop         "Looser match — finds bioisosteric replacements"
       ( ) Contains my fragment "Big molecules that contain features of this query"

Threshold: [——————●———] 0.70
Anchors:  0.4 loose · 0.7 similar · 0.85 near-analog
```

The mode radios and tooltip text come from `GET /search/algorithms` — no hardcoded mode list in the FE. Threshold default updates when the mode changes.

**Substructure tab:** add an `Allow tautomer / link-node matches` checkbox. Default off (matches current behavior). Flips `generalized: true` on the request.

No fingerprint or metric selectors are exposed in the UI. Power-user overrides are API-only.

---

## Testing

### Unit (domain)

- Mode → (algorithm, metric, threshold) mapping table is a frozen dict; one parametrized test per mode confirms it.
- `TverskyMetric` validation: α and β both ≥ 0; one parametrized test per invalid case.

### Integration (cartridge — uses real Postgres + RDKit)

- One round-trip test per (algorithm × metric) combination on a small fixture: register a known set of molecules, search with each mode, assert the expected ordering.
- **Stereo regression:** register `C[C@H](O)c1ccccc1` and `C[C@@H](O)c1ccccc1`; verify their `morgan_bfp` bytes differ; verify a Morgan/Tanimoto similarity query against either ranks the matching enantiomer above the opposite one.
- **Stereo dedup pin:** registering the two enantiomers above produces two distinct molecule rows (InChIKey differs). Direct assertion against `find_by_inchi_key` to belt-and-suspender the registration-path safety claim.
- **SMARTS hygiene:** register one aromatic ring; query with three forms that should be equivalent under aromaticity perception (`c1ccccc1`, `C1=CC=CC=C1`, `[c]1[c][c][c][c][c]1`); all three must match. This exercises `mol_adjust_query_properties`.
- **Generalized substructure:** register a tautomer pair (e.g. 2-pyridone ↔ 2-hydroxypyridine); confirm `@>` finds only the exact tautomer, `@>>` finds both.

### API

- Discriminated-union request validation: missing `kind`, unknown `kind`, threshold out of range (>1 or <0), unknown `algorithm` name → 422 with field-level errors.
- `/search/algorithms` snapshot test — any registry change must be deliberate.

### Performance smoke (manual, not CI)

Run on the demo dataset; record p50/p95 latency for each mode at its default threshold. No production observability changes — Sentry already captures errors. A dev-only `LOG_LEVEL=DEBUG` log line emits `(algorithm, threshold, candidates_screened, results_returned, ms)` per similarity query for ad-hoc tuning.

---

## Error handling boundaries

- Invalid SMILES at API boundary → 422 with `field=smiles, message="failed RDKit parse"`.
- Invalid SMARTS at API boundary → 422 (caught when `mol_adjust_query_properties` returns null).
- Unknown algorithm name in request → 422 listing valid algorithm names from the registry.
- Cartridge unavailable / extension dropped → 500 with structured log; this is a fatal misconfiguration, not a user-facing error path.

---

## Out-of-scope (explicitly deferred)

- **FPSim2 / pgvector / Milvus.** Cartridge handles current scale. Revisit when we cross ~5M registrations or start shipping all-vs-all similarity matrix features (Phase 4 SAR work).
- **MAP4, MHFP6, learned embeddings.** Registry leaves the door open; ship none of them now. The benchmark literature does not justify the operational cost at <10M molecules.
- **3D shape similarity** (ROCS-style). Out of scope; would require conformer storage and a different acceleration path.
- **Cross-protocol selectivity search revamp.** Tracked separately in the search-revamp memory entry; orthogonal to this work.

---

## Implementation note: file/folder layout

New files:

- `backend/src/cellar/domain/sar_analysis/fingerprint_algorithm.py`
- `backend/src/cellar/domain/sar_analysis/similarity_metric.py`
- `backend/src/cellar/domain/sar_analysis/search_modes.py`
- `backend/src/cellar/infrastructure/rdkit/fingerprints/__init__.py`
- `backend/src/cellar/infrastructure/rdkit/fingerprints/registry.py`
- `backend/src/cellar/infrastructure/rdkit/fingerprints/morgan.py`
- `backend/src/cellar/infrastructure/rdkit/fingerprints/fcfp.py`
- `backend/src/cellar/interface/api/v1/search/algorithms.py` (new endpoint)
- New Alembic migration in `backend/alembic/versions/`

Modified files:

- `backend/src/cellar/infrastructure/rdkit/fingerprint_generator.py` — strip dead fingerprints, use registry
- `backend/src/cellar/infrastructure/rdkit/standardizer.py` — wire stereo-aware Morgan compute
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py` — drop `LIMIT 100`, parameterize by algorithm
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py` — discriminated-union routing, `mol_adjust_query_properties`, `@>>` support
- `backend/src/cellar/interface/api/v1/search/execute.py` — discriminated-union request types
- `backend/src/cellar/infrastructure/di/` — register fingerprint algorithms
- `frontend/src/features/research-organization/components/search-query-builder.tsx` — mode radios, generalized substructure toggle
- `frontend/orval` regeneration after API schema change

Deleted:

- The `compute_morgan_bfp` trigger and its supporting code in migration 001 (replaced by the new migration).
- The four unused fingerprint generators in `fingerprint_generator.py`.
- The `fp_rdkit` LargeBinary column on `molecules`.
