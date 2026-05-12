# Similarity & Substructure Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stereo-aware Morgan, FCFP scaffold-hop mode, Tversky fragment-in-target mode, generalized substructure with SMARTS hygiene, and a pluggable `FingerprintAlgorithm` registry — on the existing RDKit cartridge.

**Architecture:** Domain holds the `FingerprintAlgorithm` Protocol + `SearchMode` mapping. Infrastructure holds the registry plus `MorganAlgorithm` (Python-side, stereo-aware) and `FCFPAlgorithm` (cartridge-trigger). Persistence routes a typed query shape (discriminated union) to the right SQL fragment. UI exposes three named modes; API exposes raw algorithm/metric for power users. One Alembic migration handles schema changes; dev mode means no data backfill.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 async, asyncpg, Postgres 16 + RDKit cartridge, Pydantic v2, Alembic, Lagom DI, Next.js 16/React 19/orval-generated client.

**Spec:** [`docs/superpowers/specs/2026-05-08-similarity-substructure-search-design.md`](../specs/2026-05-08-similarity-substructure-search-design.md)

---

## File Structure

**New files (backend):**

| Path | Responsibility |
|---|---|
| `backend/src/cellar/domain/sar_analysis/fingerprint_algorithm.py` | `FingerprintAlgorithm` Protocol — name, `bfp` column to query, cartridge query function |
| `backend/src/cellar/domain/sar_analysis/similarity_metric.py` | `Tanimoto`, `Tversky` value objects + `SimilarityMetric` union |
| `backend/src/cellar/domain/sar_analysis/search_modes.py` | `SearchMode` enum + `MODE_DEFAULTS` mapping table |
| `backend/src/cellar/infrastructure/rdkit/fingerprints/__init__.py` | Package init |
| `backend/src/cellar/infrastructure/rdkit/fingerprints/registry.py` | `FingerprintRegistry` — DI-injected dict[str, FingerprintAlgorithm] |
| `backend/src/cellar/infrastructure/rdkit/fingerprints/morgan.py` | `MorganAlgorithm` — stereo-aware Python compute, ECFP4-equivalent |
| `backend/src/cellar/infrastructure/rdkit/fingerprints/fcfp.py` | `FCFPAlgorithm` — pharmacophore-flavored, cartridge-managed (no Python compute) |
| `backend/src/cellar/interface/routes/search_algorithms.py` | New `GET /api/v1/search/algorithms` endpoint |
| `backend/alembic/versions/020_search_algorithms_overhaul.py` | Migration: drop unused fp columns, drop achiral Morgan trigger, add fcfp_bfp + GiST + new triggers |

**Modified files (backend):**

| Path | Change |
|---|---|
| `backend/src/cellar/infrastructure/rdkit/fingerprint_generator.py` | Strip to Morgan-only; `useChirality=True`; expose registry |
| `backend/src/cellar/application/chemical_registration/protocols.py` | Replace `fingerprints: dict` with `fp_morgan_chiral: bytes` on `ProcessedStructureDTO` |
| `backend/src/cellar/infrastructure/rdkit/structure_processor.py` | Use new typed Fingerprints field |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py` | Drop `fp_rdkit`, `fp_maccs`, `fp_topological_torsion`, `fp_atom_pair` |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py` | Re-route `_structure_clause` for new query shape; SMARTS hygiene; `@>>` |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py` | Drop `LIMIT 100` from `search_similarity`; algorithm/metric parameters; Tversky GUC handling |
| `backend/src/cellar/interface/routes/search.py` | Discriminated-union request; per-row similarity score with algorithm + metric |
| `backend/src/cellar/infrastructure/di/` (existing module) | Register `FingerprintRegistry` |

**Modified files (frontend):**

| Path | Change |
|---|---|
| `frontend/src/features/research-organization/components/search-query-builder.tsx` | Mode radios for similarity; `Allow tautomer / link-node matches` checkbox for substructure |
| `frontend/src/features/chemical-registration/components/compound-search-bar.tsx` | Map quick-search "similarity" to `SearchMode.SIMILAR` (no UI change) |
| `frontend/src/shared/api/` (orval-generated) | Regenerate after API schema change |

**Deleted (or reduced):**

- The `compute_morgan_bfp` cartridge trigger (defined in migration 001) — replaced by a new trigger that copies bytes through `bfp_from_binary_text`.
- `fp_rdkit`, `fp_maccs`, `fp_topological_torsion`, `fp_atom_pair` columns on `molecules`.
- The four corresponding generators in `FingerprintGenerator`.

---

## Phase A — Domain primitives (TDD)

### Task 1: SimilarityMetric value objects

**Files:**
- Create: `backend/src/cellar/domain/sar_analysis/similarity_metric.py`
- Test: `backend/tests/unit/domain/sar_analysis/test_similarity_metric.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/sar_analysis/test_similarity_metric.py
import pytest

from cellar.domain.sar_analysis.similarity_metric import (
    Tanimoto,
    Tversky,
    serialize_metric,
)


def test_tanimoto_singleton_serializes_to_string() -> None:
    assert serialize_metric(Tanimoto()) == "tanimoto"


def test_tversky_serializes_with_alpha_and_beta() -> None:
    metric = Tversky(alpha=1.0, beta=0.0)
    assert serialize_metric(metric) == "tversky(1.0,0.0)"


def test_tversky_rejects_negative_alpha() -> None:
    with pytest.raises(ValueError, match="alpha must be >= 0"):
        Tversky(alpha=-0.1, beta=0.5)


def test_tversky_rejects_negative_beta() -> None:
    with pytest.raises(ValueError, match="beta must be >= 0"):
        Tversky(alpha=0.5, beta=-0.1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/unit/domain/sar_analysis/test_similarity_metric.py -v`
Expected: `ModuleNotFoundError: No module named 'cellar.domain.sar_analysis.similarity_metric'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/src/cellar/domain/sar_analysis/similarity_metric.py
"""Similarity metric value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Tanimoto:
    """Symmetric Jaccard-style similarity. The default."""


@dataclass(frozen=True)
class Tversky:
    """Asymmetric similarity with alpha/beta weights.

    ``Tversky(alpha=1.0, beta=0.0)`` answers "is A a feature-subset of B?",
    i.e. fragment-in-target search. ``alpha == beta == 1`` reduces to Jaccard.
    """

    alpha: float
    beta: float

    def __post_init__(self) -> None:
        if self.alpha < 0:
            raise ValueError(f"alpha must be >= 0, got {self.alpha}")
        if self.beta < 0:
            raise ValueError(f"beta must be >= 0, got {self.beta}")


SimilarityMetric = Union[Tanimoto, Tversky]


def serialize_metric(metric: SimilarityMetric) -> str:
    """Stable string form for API responses and logs."""
    if isinstance(metric, Tanimoto):
        return "tanimoto"
    if isinstance(metric, Tversky):
        return f"tversky({metric.alpha},{metric.beta})"
    raise TypeError(f"Unknown metric: {metric!r}")
```

Also create `backend/tests/unit/domain/sar_analysis/__init__.py` (empty) and `backend/src/cellar/domain/sar_analysis/__init__.py` if not present.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/unit/domain/sar_analysis/test_similarity_metric.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/sar_analysis/similarity_metric.py \
        backend/tests/unit/domain/sar_analysis/test_similarity_metric.py \
        backend/src/cellar/domain/sar_analysis/__init__.py \
        backend/tests/unit/domain/sar_analysis/__init__.py
git commit -m "feat(domain): add Tanimoto + Tversky similarity metric VOs"
```

---

### Task 2: FingerprintAlgorithm Protocol

**Files:**
- Create: `backend/src/cellar/domain/sar_analysis/fingerprint_algorithm.py`
- Test: `backend/tests/unit/domain/sar_analysis/test_fingerprint_algorithm.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/sar_analysis/test_fingerprint_algorithm.py
from cellar.domain.sar_analysis.fingerprint_algorithm import (
    FingerprintAlgorithm,
)


class _FakeAlgorithm:
    name = "fake"
    column_name = "fake_bfp"
    cartridge_query_fn = "fake_fp"


def test_protocol_attributes_match() -> None:
    alg: FingerprintAlgorithm = _FakeAlgorithm()
    assert alg.name == "fake"
    assert alg.column_name == "fake_bfp"
    assert alg.cartridge_query_fn == "fake_fp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/unit/domain/sar_analysis/test_fingerprint_algorithm.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/src/cellar/domain/sar_analysis/fingerprint_algorithm.py
"""FingerprintAlgorithm Protocol -- domain-level abstraction for similarity FPs.

Implementations live in infrastructure/rdkit/fingerprints/*. Domain code
references algorithms only via name; the registry resolves names to impls.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FingerprintAlgorithm(Protocol):
    """Metadata for a fingerprint algorithm.

    Pure metadata + SQL fragments. Actual fingerprint computation lives in
    infrastructure; this Protocol only exposes what the query layer needs.
    """

    @property
    def name(self) -> str:  # e.g. "morgan", "fcfp"
        ...

    @property
    def column_name(self) -> str:  # bfp column to query, e.g. "morgan_bfp"
        ...

    @property
    def cartridge_query_fn(self) -> str:
        """SQL function name that wraps a query molecule into a bfp.

        e.g. ``morganbv_fp`` for Morgan, ``featmorganbv_fp`` for FCFP.
        Implementations must produce SQL like
        ``<cartridge_query_fn>(mol_from_smiles(:q))`` (the radius arg is
        appended by the composer where applicable).
        """
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/unit/domain/sar_analysis/test_fingerprint_algorithm.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/sar_analysis/fingerprint_algorithm.py \
        backend/tests/unit/domain/sar_analysis/test_fingerprint_algorithm.py
git commit -m "feat(domain): add FingerprintAlgorithm Protocol"
```

---

### Task 3: SearchMode enum + MODE_DEFAULTS table

**Files:**
- Create: `backend/src/cellar/domain/sar_analysis/search_modes.py`
- Test: `backend/tests/unit/domain/sar_analysis/test_search_modes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/domain/sar_analysis/test_search_modes.py
import pytest

from cellar.domain.sar_analysis.search_modes import (
    MODE_DEFAULTS,
    ModeConfig,
    SearchMode,
)
from cellar.domain.sar_analysis.similarity_metric import Tanimoto, Tversky


def test_three_modes_exist() -> None:
    assert {m.value for m in SearchMode} == {"similar", "scaffold_hop", "fragment_in_target"}


@pytest.mark.parametrize(
    "mode,algorithm,metric_type,threshold",
    [
        (SearchMode.SIMILAR, "morgan", Tanimoto, 0.7),
        (SearchMode.SCAFFOLD_HOP, "fcfp", Tanimoto, 0.55),
        (SearchMode.FRAGMENT_IN_TARGET, "morgan", Tversky, 0.7),
    ],
)
def test_mode_defaults(
    mode: SearchMode, algorithm: str, metric_type: type, threshold: float
) -> None:
    config: ModeConfig = MODE_DEFAULTS[mode]
    assert config.algorithm == algorithm
    assert isinstance(config.metric, metric_type)
    assert config.threshold == threshold


def test_fragment_in_target_uses_tversky_alpha_one_beta_zero() -> None:
    config = MODE_DEFAULTS[SearchMode.FRAGMENT_IN_TARGET]
    assert isinstance(config.metric, Tversky)
    assert config.metric.alpha == 1.0
    assert config.metric.beta == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/unit/domain/sar_analysis/test_search_modes.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/src/cellar/domain/sar_analysis/search_modes.py
"""User-facing search modes and their (algorithm, metric, threshold) defaults.

This is the ONLY place mode-to-algorithm mappings live. Adding a 4th mode
is one new entry here plus an algorithm impl in infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cellar.domain.sar_analysis.similarity_metric import (
    SimilarityMetric,
    Tanimoto,
    Tversky,
)


class SearchMode(StrEnum):
    SIMILAR = "similar"                      # broad match
    SCAFFOLD_HOP = "scaffold_hop"            # bioisosteric replacements
    FRAGMENT_IN_TARGET = "fragment_in_target"  # big molecules containing this fragment


@dataclass(frozen=True)
class ModeConfig:
    """Default (algorithm, metric, threshold) for a search mode."""

    algorithm: str
    metric: SimilarityMetric
    threshold: float
    label: str
    description: str


MODE_DEFAULTS: dict[SearchMode, ModeConfig] = {
    SearchMode.SIMILAR: ModeConfig(
        algorithm="morgan",
        metric=Tanimoto(),
        threshold=0.7,
        label="Similar",
        description="Find molecules with the same overall shape",
    ),
    SearchMode.SCAFFOLD_HOP: ModeConfig(
        algorithm="fcfp",
        metric=Tanimoto(),
        threshold=0.55,
        label="Scaffold hop",
        description="Looser match — finds bioisosteric replacements",
    ),
    SearchMode.FRAGMENT_IN_TARGET: ModeConfig(
        algorithm="morgan",
        metric=Tversky(alpha=1.0, beta=0.0),
        threshold=0.7,
        label="Contains my fragment",
        description="Big molecules that contain features of this query",
    ),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/unit/domain/sar_analysis/test_search_modes.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/sar_analysis/search_modes.py \
        backend/tests/unit/domain/sar_analysis/test_search_modes.py
git commit -m "feat(domain): add SearchMode enum + MODE_DEFAULTS table"
```

---

## Phase B — Infrastructure registry + algorithms

### Task 4: MorganAlgorithm (stereo-aware, Python-side compute)

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/fingerprints/__init__.py` (empty)
- Create: `backend/src/cellar/infrastructure/rdkit/fingerprints/morgan.py`
- Test: `backend/tests/unit/infrastructure/rdkit/fingerprints/test_morgan.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/infrastructure/rdkit/fingerprints/test_morgan.py
from rdkit import Chem

from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm


def test_metadata() -> None:
    alg = MorganAlgorithm()
    assert alg.name == "morgan"
    assert alg.column_name == "morgan_bfp"
    assert alg.cartridge_query_fn == "morganbv_fp"


def test_compute_bytes_returns_256_bytes_for_2048_bit_fp() -> None:
    alg = MorganAlgorithm()
    mol = Chem.MolFromSmiles("CCO")
    fp_bytes = alg.compute_bytes(mol)
    # 2048 bits / 8 = 256 bytes
    assert len(fp_bytes) == 256


def test_chirality_distinguishes_enantiomers() -> None:
    alg = MorganAlgorithm()
    r = Chem.MolFromSmiles("C[C@H](O)c1ccccc1")
    s = Chem.MolFromSmiles("C[C@@H](O)c1ccccc1")
    assert alg.compute_bytes(r) != alg.compute_bytes(s), (
        "Enantiomers must produce different bytes when useChirality=True"
    )


def test_achiral_smiles_independent_of_input_form() -> None:
    alg = MorganAlgorithm()
    a = Chem.MolFromSmiles("c1ccccc1")
    b = Chem.MolFromSmiles("C1=CC=CC=C1")
    assert alg.compute_bytes(a) == alg.compute_bytes(b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/unit/infrastructure/rdkit/fingerprints/test_morgan.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/src/cellar/infrastructure/rdkit/fingerprints/__init__.py
```

```python
# backend/src/cellar/infrastructure/rdkit/fingerprints/morgan.py
"""Morgan / ECFP4-equivalent fingerprint, computed in Python with stereo awareness.

The cartridge ``morganbv_fp`` does not expose ``useChirality``. To get
stereo-aware Morgan into a ``bfp`` column, we compute in Python and let a
DB trigger lift the bytes via ``bfp_from_binary_text``.
"""

from __future__ import annotations

from rdkit.Chem import rdFingerprintGenerator
from rdkit.DataStructs import ExplicitBitVect


class MorganAlgorithm:
    name = "morgan"
    column_name = "morgan_bfp"
    cartridge_query_fn = "morganbv_fp"

    def __init__(self) -> None:
        self._gen = rdFingerprintGenerator.GetMorganGenerator(
            radius=2, fpSize=2048, includeChirality=True
        )

    def compute_bytes(self, mol: object) -> bytes:
        fp: ExplicitBitVect = self._gen.GetFingerprint(mol)  # type: ignore[arg-type]
        return fp.ToBinary()
```

> **Note on RDKit naming:** in modern `rdFingerprintGenerator.GetMorganGenerator`, the kwarg is `includeChirality` (not `useChirality`). Both `ExplicitBitVect.ToBinary()` and `bfp_from_binary_text` use the cartridge's binary format. If `len(bytes) != 256` in the test above, the binary format is different — switch to manual byte-packing via `_fp_to_bytes` (see migration task 8 for the helper).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/unit/infrastructure/rdkit/fingerprints/test_morgan.py -v`
Expected: 4 passed. If `test_compute_bytes_returns_256_bytes_for_2048_bit_fp` fails because RDKit's `ToBinary` includes a header, switch to:

```python
def compute_bytes(self, mol: object) -> bytes:
    fp = self._gen.GetFingerprint(mol)
    bs = fp.ToBitString()
    return bytes(int(bs[i : i + 8], 2) for i in range(0, len(bs), 8))
```

and re-run. The DB trigger choice in Task 10 must match this byte format.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/fingerprints/__init__.py \
        backend/src/cellar/infrastructure/rdkit/fingerprints/morgan.py \
        backend/tests/unit/infrastructure/rdkit/fingerprints/__init__.py \
        backend/tests/unit/infrastructure/rdkit/fingerprints/test_morgan.py
git commit -m "feat(infra): MorganAlgorithm with stereo-aware Python compute"
```

---

### Task 5: FCFPAlgorithm (cartridge-managed, no Python compute)

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/fingerprints/fcfp.py`
- Test: `backend/tests/unit/infrastructure/rdkit/fingerprints/test_fcfp.py`

FCFP doesn't need Python-side compute (its pharmacophore abstraction is intrinsically achiral-flavored). Only metadata is shipped here; the DB trigger will compute it from `smiles` via cartridge `featmorganbv_fp`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/infrastructure/rdkit/fingerprints/test_fcfp.py
from cellar.infrastructure.rdkit.fingerprints.fcfp import FCFPAlgorithm


def test_metadata() -> None:
    alg = FCFPAlgorithm()
    assert alg.name == "fcfp"
    assert alg.column_name == "fcfp_bfp"
    assert alg.cartridge_query_fn == "featmorganbv_fp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/unit/infrastructure/rdkit/fingerprints/test_fcfp.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/src/cellar/infrastructure/rdkit/fingerprints/fcfp.py
"""FCFP -- pharmacophore-flavored circular fingerprint.

Fully cartridge-managed (no Python compute). The DB trigger writes
``fcfp_bfp`` from ``smiles`` via ``featmorganbv_fp(mol_from_smiles(...), 2)``.
This algorithm is metadata only; it has no ``compute_bytes`` method.
"""

from __future__ import annotations


class FCFPAlgorithm:
    name = "fcfp"
    column_name = "fcfp_bfp"
    cartridge_query_fn = "featmorganbv_fp"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/unit/infrastructure/rdkit/fingerprints/test_fcfp.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/fingerprints/fcfp.py \
        backend/tests/unit/infrastructure/rdkit/fingerprints/test_fcfp.py
git commit -m "feat(infra): FCFPAlgorithm metadata (cartridge-managed)"
```

---

### Task 6: FingerprintRegistry

**Files:**
- Create: `backend/src/cellar/infrastructure/rdkit/fingerprints/registry.py`
- Test: `backend/tests/unit/infrastructure/rdkit/fingerprints/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/infrastructure/rdkit/fingerprints/test_registry.py
import pytest

from cellar.infrastructure.rdkit.fingerprints.fcfp import FCFPAlgorithm
from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm
from cellar.infrastructure.rdkit.fingerprints.registry import (
    FingerprintRegistry,
    UnknownAlgorithmError,
)


def test_default_registry_has_morgan_and_fcfp() -> None:
    registry = FingerprintRegistry.default()
    assert set(registry.names()) == {"morgan", "fcfp"}
    assert isinstance(registry.get("morgan"), MorganAlgorithm)
    assert isinstance(registry.get("fcfp"), FCFPAlgorithm)


def test_get_unknown_algorithm_raises() -> None:
    registry = FingerprintRegistry.default()
    with pytest.raises(UnknownAlgorithmError, match="map4"):
        registry.get("map4")


def test_register_adds_new_algorithm() -> None:
    registry = FingerprintRegistry()

    class _MyAlg:
        name = "custom"
        column_name = "custom_bfp"
        cartridge_query_fn = "custom_fp"

    registry.register(_MyAlg())
    assert "custom" in registry.names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/unit/infrastructure/rdkit/fingerprints/test_registry.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/src/cellar/infrastructure/rdkit/fingerprints/registry.py
"""FingerprintRegistry -- runtime lookup from algorithm name to impl."""

from __future__ import annotations

from cellar.domain.sar_analysis.fingerprint_algorithm import FingerprintAlgorithm
from cellar.infrastructure.rdkit.fingerprints.fcfp import FCFPAlgorithm
from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm


class UnknownAlgorithmError(KeyError):
    """Raised when a query references an algorithm not in the registry."""


class FingerprintRegistry:
    def __init__(self) -> None:
        self._algos: dict[str, FingerprintAlgorithm] = {}

    @classmethod
    def default(cls) -> FingerprintRegistry:
        registry = cls()
        registry.register(MorganAlgorithm())
        registry.register(FCFPAlgorithm())
        return registry

    def register(self, algorithm: FingerprintAlgorithm) -> None:
        self._algos[algorithm.name] = algorithm

    def get(self, name: str) -> FingerprintAlgorithm:
        try:
            return self._algos[name]
        except KeyError as exc:
            valid = ", ".join(sorted(self._algos)) or "<empty>"
            raise UnknownAlgorithmError(
                f"Unknown fingerprint algorithm: {name!r}. Valid: {valid}"
            ) from exc

    def names(self) -> list[str]:
        return list(self._algos)

    def all(self) -> list[FingerprintAlgorithm]:
        return list(self._algos.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/unit/infrastructure/rdkit/fingerprints/test_registry.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/fingerprints/registry.py \
        backend/tests/unit/infrastructure/rdkit/fingerprints/test_registry.py
git commit -m "feat(infra): FingerprintRegistry with default Morgan + FCFP"
```

---

### Task 7: Wire registry into Lagom DI

**Files:**
- Modify: `backend/src/cellar/infrastructure/di/__init__.py` (or wherever the container is built — search for `FingerprintGenerator` registration as a hint)

- [ ] **Step 1: Locate the existing DI container build site**

Run: `rg -n 'FingerprintGenerator' backend/src/cellar/infrastructure/di/`
Expected: a single registration line. If the file lacks a dedicated DI module for fingerprints, register `FingerprintRegistry.default()` next to where `FingerprintGenerator` is currently bound.

- [ ] **Step 2: Add the registration**

```python
# pseudo-diff in the DI container builder
from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry

# ... existing code ...
container[FingerprintRegistry] = FingerprintRegistry.default()
```

- [ ] **Step 3: Verify the container builds**

Run: `uv run python -c "from cellar.infrastructure.di import build_container; c = build_container(); from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry; print(sorted(c[FingerprintRegistry].names()))"`
Expected: `['fcfp', 'morgan']`

(If `build_container` is named differently, adjust. Look in `backend/src/cellar/infrastructure/di/` for the entry point.)

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/infrastructure/di/
git commit -m "feat(di): register FingerprintRegistry with Morgan + FCFP"
```

---

## Phase C — Schema migration + cleanup

### Task 8: Strip FingerprintGenerator to Morgan-only with chirality

**Files:**
- Modify: `backend/src/cellar/infrastructure/rdkit/fingerprint_generator.py`
- Modify: `backend/tests/unit/infrastructure/rdkit/test_fingerprint_generator.py` (find and update; if absent, create)

- [ ] **Step 1: Find the existing tests**

Run: `rg -n 'FingerprintGenerator' backend/tests/`
Note any tests that assert dict keys like `"rdkit"`, `"maccs"`, etc. — those need updating.

- [ ] **Step 2: Update or add the test for the new shape**

```python
# backend/tests/unit/infrastructure/rdkit/test_fingerprint_generator.py
from rdkit import Chem

from cellar.infrastructure.rdkit.fingerprint_generator import FingerprintGenerator


def test_generates_only_morgan_chiral() -> None:
    gen = FingerprintGenerator()
    mol = Chem.MolFromSmiles("CCO")
    result = gen.compute(mol)
    assert set(result.__dataclass_fields__) == {"morgan"}
    assert isinstance(result.morgan, bytes)
    assert len(result.morgan) == 256  # 2048 bits / 8


def test_chirality_distinguishes_enantiomers() -> None:
    gen = FingerprintGenerator()
    r = gen.compute(Chem.MolFromSmiles("C[C@H](O)c1ccccc1")).morgan
    s = gen.compute(Chem.MolFromSmiles("C[C@@H](O)c1ccccc1")).morgan
    assert r != s
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest backend/tests/unit/infrastructure/rdkit/test_fingerprint_generator.py -v`
Expected: `AttributeError` or test failure (the new structure doesn't exist yet).

- [ ] **Step 4: Replace the implementation**

```python
# backend/src/cellar/infrastructure/rdkit/fingerprint_generator.py
"""Stereo-aware Morgan fingerprint generation."""

from __future__ import annotations

from dataclasses import dataclass

from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm


@dataclass(frozen=True)
class Fingerprints:
    """Computed fingerprints for a single molecule.

    Only Morgan is computed in Python (stereo-aware). FCFP is computed by
    a Postgres trigger from the canonical SMILES.
    """

    morgan: bytes


class FingerprintGenerator:
    """Generates stereo-aware Morgan fingerprint bytes."""

    def __init__(self, morgan: MorganAlgorithm | None = None) -> None:
        self._morgan = morgan or MorganAlgorithm()

    def compute(self, mol: object) -> Fingerprints:
        return Fingerprints(morgan=self._morgan.compute_bytes(mol))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest backend/tests/unit/infrastructure/rdkit/test_fingerprint_generator.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/infrastructure/rdkit/fingerprint_generator.py \
        backend/tests/unit/infrastructure/rdkit/test_fingerprint_generator.py
git commit -m "refactor(infra): strip FingerprintGenerator to stereo-aware Morgan only"
```

---

### Task 9: Update ProcessedStructureDTO + StructureProcessor for new Fingerprints VO

**Files:**
- Modify: `backend/src/cellar/application/chemical_registration/protocols.py`
- Modify: `backend/src/cellar/infrastructure/rdkit/structure_processor.py`
- Find/update tests for both.

- [ ] **Step 1: Find existing references**

Run: `rg -n 'ProcessedStructureDTO\|fingerprints:' backend/src/ backend/tests/`
Note every site that reads `.fingerprints["morgan"]`, `.fingerprints["maccs"]`, etc. They all need updating.

- [ ] **Step 2: Update the DTO**

In `backend/src/cellar/application/chemical_registration/protocols.py`, replace the `fingerprints: dict[str, bytes]` field on `ProcessedStructureDTO`:

```python
# Old:
# fingerprints: dict[str, bytes]

# New:
from cellar.infrastructure.rdkit.fingerprint_generator import Fingerprints
# (Note: this introduces an application -> infrastructure import; if the
# project's lint blocks this, move Fingerprints into application/ as a
# domain-shaped DTO. The simplest path is to define a local
# ApplicationFingerprintsDTO mirroring the one bytes field.)

fingerprints: Fingerprints
```

If the application layer is forbidden from importing infrastructure (check `pyproject.toml` lint config and existing patterns), instead define the DTO locally in `protocols.py`:

```python
@dataclass(frozen=True)
class FingerprintsDTO:
    morgan: bytes


# in ProcessedStructureDTO:
fingerprints: FingerprintsDTO
```

and update `FingerprintGenerator.compute` to return that DTO (or have `StructureProcessor` adapt). Pick the path that matches existing layer-rule enforcement.

- [ ] **Step 3: Update StructureProcessor**

In `backend/src/cellar/infrastructure/rdkit/structure_processor.py:79`, replace:

```python
fingerprints = self._fp_gen.generate_all(std_mol.mol)
```

with:

```python
fingerprints = self._fp_gen.compute(std_mol.mol)
```

And in step 6 (the DTO build), pass `fingerprints` directly (no dict-keys lookup).

- [ ] **Step 4: Update every consumer**

For each site flagged in Step 1, replace `fingerprints["morgan"]` with `fingerprints.morgan`. Delete any code reading `fingerprints["rdkit"]`, `["maccs"]`, `["topological_torsion"]`, `["atom_pair"]`.

- [ ] **Step 5: Run the full backend test suite**

Run: `uv run pytest backend/tests/ -x --ff`
Expected: all tests pass (or the only failures are in the consumers you missed — fix and rerun).

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/chemical_registration/protocols.py \
        backend/src/cellar/infrastructure/rdkit/structure_processor.py \
        backend/src/cellar/  # any consumer files updated
git commit -m "refactor(app): use Fingerprints VO instead of dict on ProcessedStructureDTO"
```

---

### Task 10: Alembic migration — schema overhaul

**Files:**
- Create: `backend/alembic/versions/020_search_algorithms_overhaul.py`

- [ ] **Step 1: Generate the migration skeleton**

Run: `cd backend && uv run alembic revision -m "search algorithms overhaul"`
This produces `020_search_algorithms_overhaul.py` (or similar). Move/rename to match the file path above.

- [ ] **Step 2: Write the migration**

```python
# backend/alembic/versions/020_search_algorithms_overhaul.py
"""search algorithms overhaul: stereo-aware Morgan + FCFP + cleanup.

- Drop unused Python-side fingerprint columns (fp_rdkit, fp_maccs,
  fp_topological_torsion, fp_atom_pair).
- Drop the achiral cartridge trigger that computed morgan_bfp from smiles.
- Replace with a trigger that lifts Python-computed bytes (in fp_morgan)
  into morgan_bfp via bfp_from_binary_text.
- Add fcfp_bfp column with cartridge trigger from smiles + GiST index.

Revision ID: 020_search_algorithms_overhaul
Revises: 019_pos_control_signal_on_protocol
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "020_search_algorithms_overhaul"
down_revision = "019_pos_control_signal_on_protocol"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop unused Python-side fingerprint columns.
    op.drop_column("molecules", "fp_rdkit")
    op.drop_column("molecules", "fp_maccs")
    op.drop_column("molecules", "fp_topological_torsion")
    op.drop_column("molecules", "fp_atom_pair")

    # 2. Drop the old achiral Morgan trigger and helper function.
    op.execute("DROP TRIGGER IF EXISTS trg_compute_morgan_bfp ON molecules")
    op.execute("DROP FUNCTION IF EXISTS compute_morgan_bfp()")

    # 3. New trigger: lift Python-computed bytes (fp_morgan) into morgan_bfp.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_morgan_bfp() RETURNS trigger AS $$
        BEGIN
            IF NEW.fp_morgan IS NULL THEN
                NEW.morgan_bfp := NULL;
            ELSE
                NEW.morgan_bfp := bfp_from_binary_text(NEW.fp_morgan);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sync_morgan_bfp
        BEFORE INSERT OR UPDATE OF fp_morgan ON molecules
        FOR EACH ROW EXECUTE FUNCTION sync_morgan_bfp();
        """
    )

    # 4. Add fcfp_bfp + GiST index + cartridge-managed trigger.
    op.execute("ALTER TABLE molecules ADD COLUMN fcfp_bfp bfp")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION compute_fcfp_bfp() RETURNS trigger AS $$
        BEGIN
            IF NEW.smiles IS NULL THEN
                NEW.fcfp_bfp := NULL;
            ELSE
                NEW.fcfp_bfp := featmorganbv_fp(mol_from_smiles(NEW.smiles), 2);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_compute_fcfp_bfp
        BEFORE INSERT OR UPDATE OF smiles ON molecules
        FOR EACH ROW EXECUTE FUNCTION compute_fcfp_bfp();
        """
    )
    op.execute(
        "CREATE INDEX ix_molecules_fcfp_bfp ON molecules USING gist (fcfp_bfp)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_molecules_fcfp_bfp")
    op.execute("DROP TRIGGER IF EXISTS trg_compute_fcfp_bfp ON molecules")
    op.execute("DROP FUNCTION IF EXISTS compute_fcfp_bfp()")
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS fcfp_bfp")

    op.execute("DROP TRIGGER IF EXISTS trg_sync_morgan_bfp ON molecules")
    op.execute("DROP FUNCTION IF EXISTS sync_morgan_bfp()")

    # Restore the original achiral Morgan trigger from migration 001.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION compute_morgan_bfp() RETURNS trigger AS $$
        BEGIN
            IF NEW.smiles IS NULL THEN
                NEW.morgan_bfp := NULL;
            ELSE
                NEW.morgan_bfp := morganbv_fp(mol_from_smiles(NEW.smiles));
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_compute_morgan_bfp
        BEFORE INSERT OR UPDATE OF smiles ON molecules
        FOR EACH ROW EXECUTE FUNCTION compute_morgan_bfp();
        """
    )

    # Restore deleted columns.
    op.add_column("molecules", sa.Column("fp_atom_pair", sa.LargeBinary, nullable=True))
    op.add_column("molecules", sa.Column("fp_topological_torsion", sa.LargeBinary, nullable=True))
    op.add_column("molecules", sa.Column("fp_maccs", sa.LargeBinary, nullable=True))
    op.add_column("molecules", sa.Column("fp_rdkit", sa.LargeBinary, nullable=True))
```

> **Caveat — verify the original trigger names.** Read `backend/alembic/versions/001_001_initial_schema.py` lines 968-993 first; the trigger / function names above (`trg_compute_morgan_bfp`, `compute_morgan_bfp`) are guesses that match common conventions. If the actual names differ, update both `upgrade()` (the DROP) and `downgrade()` (the CREATE) accordingly.

- [ ] **Step 3: Apply migration locally**

Run: `cd backend && uv run alembic upgrade head`
Expected: completes without error. Spot-check:
- `\d molecules` in psql shows `morgan_bfp bfp`, `fcfp_bfp bfp`, `fp_morgan bytea`, no `fp_rdkit/fp_maccs/etc.`
- `\dx rdkit` confirms cartridge still installed.
- `SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid = 'molecules'::regclass` lists `trg_sync_morgan_bfp` and `trg_compute_fcfp_bfp`.

- [ ] **Step 4: Test downgrade then upgrade roundtrip**

```bash
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: both succeed; spot-check above still holds after the second upgrade.

- [ ] **Step 5: Update the SQLAlchemy model**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py:70-74`, delete the dead column declarations:

```python
# Delete:
# fp_rdkit: Mapped[bytes | None] = mapped_column(LargeBinary)
# fp_maccs: Mapped[bytes | None] = mapped_column(LargeBinary)
# fp_topological_torsion: Mapped[bytes | None] = mapped_column(LargeBinary)
# fp_atom_pair: Mapped[bytes | None] = mapped_column(LargeBinary)
```

Keep `fp_morgan: Mapped[bytes | None]` — that's now the source for the trigger.

- [ ] **Step 6: Run the full backend test suite**

Run: `uv run pytest backend/tests/ -x --ff`
Expected: all green. Any code that referenced the dropped columns must already have been cleaned in Task 9; if a stragler appears, fix it now.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/020_search_algorithms_overhaul.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py
git commit -m "feat(db): migration 020 — stereo-aware Morgan + FCFP, drop unused fp columns"
```

---

## Phase D — Persistence layer (similarity)

### Task 11: New similarity SQL composer with algorithm + metric routing

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py`
- Test: `backend/tests/unit/infrastructure/persistence/sqlalchemy/chemical_registration/test_search_query_composer.py`

- [ ] **Step 1: Write a failing test for the new shape**

```python
# backend/tests/unit/infrastructure/persistence/sqlalchemy/chemical_registration/test_search_query_composer.py
# (extend the existing test file if present)
import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)


@pytest.fixture()
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


def _structure_query(criterion: dict) -> dict:
    return {"criteria": [{"type": "structure", **criterion}]}


def test_similarity_morgan_tanimoto_compiles(workspace_id) -> None:
    clause = compose_criteria(
        _structure_query(
            {"kind": "similarity", "smiles": "CCO", "algorithm": "morgan",
             "metric": {"kind": "tanimoto"}, "threshold": 0.7}
        ),
        workspace_id=workspace_id,
    )
    sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "morgan_bfp % morganbv_fp" in sql
    assert "mol_from_smiles" in sql


def test_similarity_fcfp_tanimoto_compiles(workspace_id) -> None:
    clause = compose_criteria(
        _structure_query(
            {"kind": "similarity", "smiles": "CCO", "algorithm": "fcfp",
             "metric": {"kind": "tanimoto"}, "threshold": 0.55}
        ),
        workspace_id=workspace_id,
    )
    sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "fcfp_bfp" in sql
    assert "featmorganbv_fp" in sql


def test_similarity_tversky_uses_function_form(workspace_id) -> None:
    clause = compose_criteria(
        _structure_query(
            {"kind": "similarity", "smiles": "c1ccccc1", "algorithm": "morgan",
             "metric": {"kind": "tversky", "alpha": 1.0, "beta": 0.0},
             "threshold": 0.7}
        ),
        workspace_id=workspace_id,
    )
    sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "tversky_sml" in sql
    assert "1.0" in sql and "0.0" in sql


def test_substructure_passes_through_mol_adjust_query_properties(workspace_id) -> None:
    clause = compose_criteria(
        _structure_query({"kind": "substructure", "smiles_or_smarts": "c1ccccc1"}),
        workspace_id=workspace_id,
    )
    sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "mol_adjust_query_properties" in sql


def test_substructure_generalized_uses_xqmol_and_double_arrow(workspace_id) -> None:
    clause = compose_criteria(
        _structure_query(
            {"kind": "substructure", "smiles_or_smarts": "OC1=CC=CC=N1",
             "generalized": True}
        ),
        workspace_id=workspace_id,
    )
    sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "@>>" in sql
    assert "mol_to_xqmol" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/unit/infrastructure/persistence/sqlalchemy/chemical_registration/test_search_query_composer.py -v -k similarity_morgan or substructure`
Expected: 5 failures (the new query shape isn't routed yet).

- [ ] **Step 3: Replace `_structure_clause` and add helpers**

Replace lines 169-187 of `search_query_composer.py`:

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py
# (replace _structure_clause; keep all other code unchanged)

from cellar.domain.sar_analysis.search_modes import MODE_DEFAULTS, SearchMode
from cellar.domain.sar_analysis.similarity_metric import (
    Tanimoto,
    Tversky,
    serialize_metric,
)
from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry

# Module-level singleton; DI override is fine for tests.
_default_registry = FingerprintRegistry.default()


def _structure_clause(criterion: dict[str, Any]) -> ColumnElement:
    kind = criterion.get("kind") or criterion.get("search_type")  # accept legacy alias

    if kind == "exact":
        inchi_key = criterion["inchi_key"]
        return MoleculeModel.inchi_key == inchi_key

    if kind == "substructure":
        return _substructure_clause(criterion)

    if kind == "similarity":
        return _similarity_clause(criterion)

    msg = f"Unknown structure kind: {kind!r}"
    raise ValueError(msg)


def _substructure_clause(criterion: dict[str, Any]) -> ColumnElement:
    query_text = criterion.get("smiles_or_smarts") or criterion.get("smarts")
    if not query_text:
        raise ValueError("substructure requires smiles_or_smarts (or legacy smarts)")
    generalized = bool(criterion.get("generalized", False))

    if generalized:
        sql = (
            "mol_from_smiles(smiles) @>> "
            "mol_to_xqmol(mol_adjust_query_properties(mol_from_smarts(:q)))"
        )
    else:
        sql = (
            "mol_from_smiles(smiles) @> "
            "mol_adjust_query_properties(mol_from_smarts(:q))"
        )
    return text(sql).bindparams(sa.bindparam("q", value=query_text, type_=sa.String))


def _resolve_algorithm_and_metric(
    criterion: dict[str, Any],
) -> tuple[str, object, float]:
    """Resolve (algorithm_name, metric_obj, threshold) from a similarity criterion.

    Priority: explicit algorithm/metric/threshold override mode defaults.
    """
    algorithm: str | None = criterion.get("algorithm")
    metric_payload: dict | None = criterion.get("metric")
    threshold: float | None = criterion.get("threshold")

    mode_value = criterion.get("mode")
    if mode_value is not None:
        mode = SearchMode(mode_value)
        defaults = MODE_DEFAULTS[mode]
        algorithm = algorithm or defaults.algorithm
        threshold = threshold if threshold is not None else defaults.threshold
        if metric_payload is None:
            metric = defaults.metric
        else:
            metric = _parse_metric(metric_payload)
    else:
        if algorithm is None:
            raise ValueError("similarity requires either mode or algorithm")
        if metric_payload is None:
            raise ValueError("similarity without mode requires explicit metric")
        if threshold is None:
            raise ValueError("similarity without mode requires explicit threshold")
        metric = _parse_metric(metric_payload)

    if not (0.0 <= float(threshold) <= 1.0):
        raise ValueError(f"threshold must be in [0,1], got {threshold}")

    return algorithm, metric, float(threshold)


def _parse_metric(payload: dict[str, Any]) -> object:
    kind = payload.get("kind", "tanimoto")
    if kind == "tanimoto":
        return Tanimoto()
    if kind == "tversky":
        return Tversky(alpha=float(payload["alpha"]), beta=float(payload["beta"]))
    raise ValueError(f"Unknown metric kind: {kind!r}")


def _similarity_clause(criterion: dict[str, Any]) -> ColumnElement:
    smiles = criterion["smiles"]
    algorithm_name, metric, threshold = _resolve_algorithm_and_metric(criterion)
    algo = _default_registry.get(algorithm_name)
    column = algo.column_name
    fn = algo.cartridge_query_fn
    radius_arg = ", 2" if fn == "featmorganbv_fp" else ""

    if isinstance(metric, Tanimoto):
        # GiST `%` operator + tanimoto_threshold GUC
        sql = f"{column} % {fn}(mol_from_smiles(:sim_q){radius_arg})"
    elif isinstance(metric, Tversky):
        # No operator hits the GiST index; use function-form. See spec §Tversky caveat.
        sql = (
            f"tversky_sml({column}, {fn}(mol_from_smiles(:sim_q){radius_arg}), "
            f"{metric.alpha}, {metric.beta}) >= {threshold}"
        )
    else:
        raise ValueError(f"Unknown metric: {metric!r}")

    return text(sql).bindparams(sa.bindparam("sim_q", value=smiles, type_=sa.String))
```

> **Note:** existing callers of the old `search_type` shape continue to work because `_structure_clause` accepts both `kind` and the legacy `search_type` key — but for `similarity` and `substructure`, the new fields (`mode`, `smiles_or_smarts`) are required. Saved searches in dev get regenerated; no in-place migration of stored query dicts is needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/unit/infrastructure/persistence/sqlalchemy/chemical_registration/test_search_query_composer.py -v`
Expected: all green (existing + new).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py \
        backend/tests/unit/infrastructure/persistence/sqlalchemy/chemical_registration/test_search_query_composer.py
git commit -m "feat(persistence): route similarity/substructure via algorithm registry + SMARTS hygiene"
```

---

### Task 12: Tanimoto threshold GUC — extend for both columns

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py:202-216`

The `_set_similarity_threshold` helper currently sets `rdkit.tanimoto_threshold` once. For Tversky, no GUC is needed (the `>=` filter is in WHERE). The existing helper stays mostly the same but should walk into nested groups too.

- [ ] **Step 1: Add a test for nested-group threshold extraction**

```python
# In an existing or new molecule_reader integration test file:
async def test_set_similarity_threshold_walks_into_groups(session) -> None:
    from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
        _set_similarity_threshold,
    )

    query = {
        "criteria": [
            {
                "type": "group",
                "logic": "and",
                "criteria": [
                    {"type": "structure", "kind": "similarity", "smiles": "CCO",
                     "mode": "similar", "threshold": 0.42},
                ],
            }
        ]
    }
    await _set_similarity_threshold(session, query)
    res = await session.execute(text("SHOW rdkit.tanimoto_threshold"))
    assert float(res.scalar_one()) == 0.42
```

- [ ] **Step 2: Run test (should fail because the helper doesn't recurse)**

Run: `uv run pytest backend/tests/integration/persistence/test_molecule_reader_threshold.py -v` (or wherever you placed it).

- [ ] **Step 3: Update `_set_similarity_threshold` to recurse and to handle Tanimoto-only**

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py

async def _set_similarity_threshold(session: AsyncSession, query: dict[str, Any]) -> None:
    """Set rdkit.tanimoto_threshold once, based on the first Tanimoto similarity
    clause encountered (recursively walks groups). No-op for Tversky-only
    similarity clauses (those use function-form WHERE filters).
    """
    threshold = _find_first_tanimoto_threshold(query.get("criteria", []))
    if threshold is None:
        return
    await session.execute(text(f"SET rdkit.tanimoto_threshold = {threshold}"))


def _find_first_tanimoto_threshold(criteria: list[dict[str, Any]]) -> float | None:
    for criterion in criteria:
        ctype = criterion.get("type")
        if ctype == "structure":
            kind = criterion.get("kind") or criterion.get("search_type")
            if kind != "similarity":
                continue
            metric = criterion.get("metric") or {"kind": "tanimoto"}
            mode = criterion.get("mode")
            # Tversky doesn't use the GUC.
            if metric.get("kind") == "tversky":
                continue
            if mode == "fragment_in_target":
                continue  # mode default is Tversky
            t = criterion.get("threshold")
            if t is None and mode is not None:
                from cellar.domain.sar_analysis.search_modes import (
                    MODE_DEFAULTS,
                    SearchMode,
                )
                t = MODE_DEFAULTS[SearchMode(mode)].threshold
            if t is None:
                continue
            return float(t)
        if ctype == "group":
            nested = _find_first_tanimoto_threshold(criterion.get("criteria", []))
            if nested is not None:
                return nested
    return None
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest backend/tests/ -k threshold -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py \
        backend/tests/  # the new test file
git commit -m "feat(persistence): recurse into groups when setting tanimoto threshold; skip for Tversky"
```

---

### Task 13: Drop LIMIT 100 from `search_similarity`; pass algorithm/metric

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py:43-95`

The direct path (`search_substructure` and `search_similarity` on `SQLAlchemyMoleculeReader`) is used by the `SearchMolecules` use case. The advanced path goes through `search_by_query` + the composer. Both must be updated.

- [ ] **Step 1: Add a test that asserts no LIMIT 100**

```python
# backend/tests/integration/persistence/test_search_similarity_pagination.py
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

# Assume you have fixtures for: workspace_id, session_factory, registered molecules.

@pytest.mark.asyncio
async def test_similarity_returns_more_than_100_when_threshold_is_low(
    workspace_id, session_factory, register_n_molecules
):
    # Register 150 molecules that all match a permissive query.
    await register_n_molecules(150, base_smiles="CCCCO")

    from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
        SQLAlchemyMoleculeReader,
    )
    reader = SQLAlchemyMoleculeReader(session_factory)
    results = await reader.search_similarity(
        workspace_id, smiles="CCCCO", threshold=0.0, limit=200,
    )
    assert len(results) >= 100  # the old hardcoded ceiling is gone
```

- [ ] **Step 2: Run test (should fail because of `LIMIT 100`)**

- [ ] **Step 3: Update `search_similarity` signature**

```python
# backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py

from cellar.domain.sar_analysis.search_modes import MODE_DEFAULTS, SearchMode
from cellar.domain.sar_analysis.similarity_metric import (
    SimilarityMetric,
    Tanimoto,
    Tversky,
)
from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry

# Replace the existing search_similarity:

async def search_similarity(
    self,
    workspace_id: uuid.UUID,
    smiles: str,
    *,
    mode: SearchMode = SearchMode.SIMILAR,
    threshold: float | None = None,
    algorithm: str | None = None,
    metric: SimilarityMetric | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[tuple[Molecule, float]]:
    """Similarity search with mode-driven defaults + algorithm/metric overrides."""
    defaults = MODE_DEFAULTS[mode]
    algorithm_name = algorithm or defaults.algorithm
    metric = metric or defaults.metric
    threshold = float(threshold if threshold is not None else defaults.threshold)
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"threshold must be in [0,1], got {threshold}")

    registry = FingerprintRegistry.default()
    algo = registry.get(algorithm_name)
    column = algo.column_name
    fn = algo.cartridge_query_fn
    radius_arg = ", 2" if fn == "featmorganbv_fp" else ""

    async with self._session_factory() as session:
        if isinstance(metric, Tanimoto):
            await session.execute(
                text(f"SET rdkit.tanimoto_threshold = {threshold}")
            )
            score_sql = (
                f"tanimoto_sml({column}, {fn}(mol_from_smiles(:q){radius_arg})) AS similarity"
            )
            where_sql = f"{column} % {fn}(mol_from_smiles(:q){radius_arg})"
        elif isinstance(metric, Tversky):
            score_sql = (
                f"tversky_sml({column}, {fn}(mol_from_smiles(:q){radius_arg}), "
                f"{metric.alpha}, {metric.beta}) AS similarity"
            )
            where_sql = (
                f"tversky_sml({column}, {fn}(mol_from_smiles(:q){radius_arg}), "
                f"{metric.alpha}, {metric.beta}) >= {threshold}"
            )
        else:
            raise ValueError(f"Unknown metric: {metric!r}")

        stmt = (
            select(MoleculeModel, text(score_sql))
            .where(
                MoleculeModel.workspace_id == workspace_id,
                MoleculeModel.merged_into_id.is_(None),
                text(where_sql),
            )
            .params(q=smiles)
            .order_by(text("similarity DESC"))
        )
        if cursor_id is not None:
            stmt = stmt.where(MoleculeModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        return [(model_to_molecule(row[0]), float(row[1])) for row in result.all()]
```

- [ ] **Step 4: Update the use case caller**

In `backend/src/cellar/application/chemical_registration/search_molecules.py`, update the call site to pass the new kwargs (defaulting to mode-driven behavior). Search for `.search_similarity(` and update.

- [ ] **Step 5: Run tests**

Run: `uv run pytest backend/tests/ -x --ff -k similarity`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py \
        backend/src/cellar/application/chemical_registration/search_molecules.py \
        backend/tests/integration/persistence/test_search_similarity_pagination.py
git commit -m "feat(persistence): mode-driven similarity, drop LIMIT 100, support Tversky"
```

---

## Phase E — Integration tests (cartridge round-trip)

These run against a real Postgres + RDKit cartridge. The codebase already has `backend/tests/integration/test_fingerprint_index.py` — extend or sit alongside it.

### Task 14: Stereo regression test (Morgan-with-chirality)

**Files:**
- Create: `backend/tests/integration/search/test_stereo_regression.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/integration/search/test_stereo_regression.py
"""Verify that stereo-aware Morgan distinguishes enantiomers in similarity."""

import pytest

from cellar.domain.sar_analysis.search_modes import SearchMode
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)


@pytest.mark.asyncio
async def test_enantiomer_morgan_bytes_differ(register_molecule, session_factory):
    """Direct DB read: the two enantiomers store different morgan_bfp bytes."""
    r = await register_molecule(smiles="C[C@H](O)c1ccccc1", name="R-1-phenylethanol")
    s = await register_molecule(smiles="C[C@@H](O)c1ccccc1", name="S-1-phenylethanol")
    assert r.fp_morgan != s.fp_morgan


@pytest.mark.asyncio
async def test_enantiomers_dedup_as_distinct_molecules(register_molecule):
    r = await register_molecule(smiles="C[C@H](O)c1ccccc1", name="R")
    s = await register_molecule(smiles="C[C@@H](O)c1ccccc1", name="S")
    assert r.id != s.id  # InChIKey differs → two rows


@pytest.mark.asyncio
async def test_similarity_ranks_matching_enantiomer_higher(
    workspace_id, session_factory, register_molecule,
):
    r = await register_molecule(smiles="C[C@H](O)c1ccccc1", name="R")
    s = await register_molecule(smiles="C[C@@H](O)c1ccccc1", name="S")
    reader = SQLAlchemyMoleculeReader(session_factory)

    # Query with R; expect R ranked above S.
    results = await reader.search_similarity(
        workspace_id, smiles="C[C@H](O)c1ccccc1",
        mode=SearchMode.SIMILAR, threshold=0.0, limit=10,
    )
    by_name = {mol.name: score for mol, score in results}
    assert by_name["R"] > by_name["S"], (
        "Stereo-aware Morgan must score the matching enantiomer higher"
    )
```

- [ ] **Step 2: Run test (should pass; if it fails the trigger or compute is wrong)**

Run: `uv run pytest backend/tests/integration/search/test_stereo_regression.py -v`
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/search/test_stereo_regression.py \
        backend/tests/integration/search/__init__.py
git commit -m "test(integration): pin stereo-aware Morgan similarity ranking"
```

---

### Task 15: SMARTS hygiene round-trip

**Files:**
- Create: `backend/tests/integration/search/test_smarts_hygiene.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/integration/search/test_smarts_hygiene.py
"""mol_adjust_query_properties must normalize aromaticity perception."""

import pytest

from cellar.application.research_organization.execute_search import (
    ExecuteSearchQuery,
)


@pytest.mark.asyncio
async def test_three_benzene_smarts_all_match(register_molecule, execute_search, auth):
    await register_molecule(smiles="c1ccccc1", name="benzene")

    for query_text in ("c1ccccc1", "C1=CC=CC=C1", "[c]1[c][c][c][c][c]1"):
        q = ExecuteSearchQuery(
            workspace_id=auth.workspace_id,
            query={
                "criteria": [{
                    "type": "structure",
                    "kind": "substructure",
                    "smiles_or_smarts": query_text,
                }],
            },
        )
        page = (await execute_search(q, auth=auth)).unwrap()
        names = [m.name for m in page.items]
        assert "benzene" in names, f"SMARTS {query_text!r} did not match benzene"
```

- [ ] **Step 2: Run test**

Run: `uv run pytest backend/tests/integration/search/test_smarts_hygiene.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/search/test_smarts_hygiene.py
git commit -m "test(integration): SMARTS aromaticity hygiene via mol_adjust_query_properties"
```

---

### Task 16: Generalized substructure tautomer test

**Files:**
- Create: `backend/tests/integration/search/test_generalized_substructure.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/integration/search/test_generalized_substructure.py
"""@>> with mol_to_xqmol matches tautomers that @> misses."""

import pytest

from cellar.application.research_organization.execute_search import (
    ExecuteSearchQuery,
)


@pytest.mark.asyncio
async def test_pyridone_tautomers(register_molecule, execute_search, auth):
    # 2-pyridone (keto form, registered)
    await register_molecule(smiles="O=C1NC=CC=C1", name="2-pyridone")

    # Query with 2-hydroxypyridine (enol form).
    base = {
        "type": "structure", "kind": "substructure",
        "smiles_or_smarts": "OC1=CC=CC=N1",
    }

    # Strict @> may miss the keto tautomer.
    strict_q = ExecuteSearchQuery(
        workspace_id=auth.workspace_id,
        query={"criteria": [{**base, "generalized": False}]},
    )
    strict_results = (await execute_search(strict_q, auth=auth)).unwrap()
    strict_names = [m.name for m in strict_results.items]

    # Generalized @>> finds it.
    loose_q = ExecuteSearchQuery(
        workspace_id=auth.workspace_id,
        query={"criteria": [{**base, "generalized": True}]},
    )
    loose_results = (await execute_search(loose_q, auth=auth)).unwrap()
    loose_names = [m.name for m in loose_results.items]

    assert "2-pyridone" in loose_names
    # If both find it, the test still passes meaningfully — the assertion is
    # that generalized never misses what strict finds.
    if "2-pyridone" in strict_names:
        assert "2-pyridone" in loose_names
```

- [ ] **Step 2: Run test**

Run: `uv run pytest backend/tests/integration/search/test_generalized_substructure.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/search/test_generalized_substructure.py
git commit -m "test(integration): generalized substructure finds tautomer matches"
```

---

### Task 17: All-three-modes round-trip

**Files:**
- Create: `backend/tests/integration/search/test_search_modes_roundtrip.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/integration/search/test_search_modes_roundtrip.py
"""Each SearchMode round-trips through the cartridge with sensible ranking."""

import pytest

from cellar.domain.sar_analysis.search_modes import SearchMode
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)


@pytest.fixture()
async def small_corpus(register_molecule):
    """Three molecules with different similarity profiles to ethanol."""
    await register_molecule(smiles="CCO", name="ethanol")
    await register_molecule(smiles="CC(C)O", name="isopropanol")
    await register_molecule(smiles="c1ccccc1", name="benzene")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(SearchMode))
async def test_each_mode_returns_results(
    mode, small_corpus, workspace_id, session_factory,
):
    reader = SQLAlchemyMoleculeReader(session_factory)
    results = await reader.search_similarity(
        workspace_id, smiles="CCO", mode=mode, threshold=0.0, limit=10,
    )
    names = [mol.name for mol, _ in results]
    # ethanol is exact-match for "Similar"; appears for all modes at threshold=0.
    assert "ethanol" in names
    # benzene should rank below ethanol in SIMILAR mode (different topology).
    if mode == SearchMode.SIMILAR:
        order = {n: i for i, n in enumerate(names)}
        assert order["ethanol"] < order["benzene"]
```

- [ ] **Step 2: Run test**

Run: `uv run pytest backend/tests/integration/search/test_search_modes_roundtrip.py -v`
Expected: 3 parametrized cases pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/search/test_search_modes_roundtrip.py
git commit -m "test(integration): all three SearchModes round-trip through cartridge"
```

---

## Phase F — API

### Task 18: Pydantic discriminated-union request types

**Files:**
- Modify: `backend/src/cellar/interface/routes/search.py`
- Test: `backend/tests/api/test_search_request_validation.py`

- [ ] **Step 1: Write request-validation tests**

```python
# backend/tests/api/test_search_request_validation.py
import pytest
from fastapi.testclient import TestClient


def _post_search(client: TestClient, body: dict, auth_headers: dict) -> "Response":
    return client.post("/api/v1/search/execute", json=body, headers=auth_headers)


def test_unknown_kind_returns_422(client, auth_headers):
    body = {"query": {"criteria": [{"type": "structure", "kind": "fancy"}]}}
    r = _post_search(client, body, auth_headers)
    assert r.status_code == 422


def test_similarity_threshold_out_of_range_returns_422(client, auth_headers):
    body = {"query": {"criteria": [{
        "type": "structure", "kind": "similarity", "smiles": "CCO",
        "mode": "similar", "threshold": 1.5,
    }]}}
    r = _post_search(client, body, auth_headers)
    assert r.status_code == 422


def test_unknown_algorithm_returns_422(client, auth_headers):
    body = {"query": {"criteria": [{
        "type": "structure", "kind": "similarity", "smiles": "CCO",
        "algorithm": "map4_v9", "metric": {"kind": "tanimoto"}, "threshold": 0.7,
    }]}}
    r = _post_search(client, body, auth_headers)
    assert r.status_code == 422


def test_invalid_smiles_returns_422(client, auth_headers):
    body = {"query": {"criteria": [{
        "type": "structure", "kind": "similarity", "smiles": "XYZ-NOT-A-SMILES",
        "mode": "similar",
    }]}}
    r = _post_search(client, body, auth_headers)
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests (should fail until validation exists)**

- [ ] **Step 3: Add the discriminated-union schema**

```python
# backend/src/cellar/interface/routes/search.py — add near the top, before ExecuteSearchBody

from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, model_validator
from rdkit import Chem

from cellar.domain.sar_analysis.search_modes import MODE_DEFAULTS, SearchMode
from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry

_registry = FingerprintRegistry.default()


class _MetricTanimoto(BaseModel):
    kind: Literal["tanimoto"] = "tanimoto"


class _MetricTversky(BaseModel):
    kind: Literal["tversky"]
    alpha: float = Field(ge=0.0)
    beta: float = Field(ge=0.0)


_MetricSpec = Annotated[
    Union[_MetricTanimoto, _MetricTversky], Field(discriminator="kind")
]


class _ExactMatch(BaseModel):
    kind: Literal["exact"]
    smiles: str

    @model_validator(mode="after")
    def _check(self) -> "_ExactMatch":
        if Chem.MolFromSmiles(self.smiles) is None:
            raise ValueError("smiles failed RDKit parse")
        return self


class _SubstructureMatch(BaseModel):
    kind: Literal["substructure"]
    smiles_or_smarts: str
    generalized: bool = False

    @model_validator(mode="after")
    def _check(self) -> "_SubstructureMatch":
        # Either SMILES or SMARTS must be parseable.
        if (Chem.MolFromSmiles(self.smiles_or_smarts) is None
                and Chem.MolFromSmarts(self.smiles_or_smarts) is None):
            raise ValueError("smiles_or_smarts failed RDKit parse")
        return self


class _SimilarityMatch(BaseModel):
    kind: Literal["similarity"]
    smiles: str
    mode: SearchMode | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    algorithm: str | None = None
    metric: _MetricSpec | None = None

    @model_validator(mode="after")
    def _check(self) -> "_SimilarityMatch":
        if Chem.MolFromSmiles(self.smiles) is None:
            raise ValueError("smiles failed RDKit parse")
        if self.mode is None and (self.algorithm is None or self.metric is None
                                  or self.threshold is None):
            raise ValueError(
                "either mode is required, or algorithm + metric + threshold must all be set"
            )
        if self.algorithm is not None and self.algorithm not in _registry.names():
            raise ValueError(
                f"unknown algorithm: {self.algorithm!r}; valid: {sorted(_registry.names())}"
            )
        return self


_StructureClause = Annotated[
    Union[_ExactMatch, _SubstructureMatch, _SimilarityMatch],
    Field(discriminator="kind"),
]
```

The `query` dict on `ExecuteSearchBody` continues to be `dict[str, Any]` because it carries non-structure clauses (text/property/etc.) that are validated downstream. Structure clauses are validated at the service boundary by adapting through the discriminated union — the simplest hook is to walk `query["criteria"]`, find any `{"type": "structure"}` entries, and validate each via `TypeAdapter(_StructureClause).validate_python(criterion_minus_type)`.

Add this validation step into `ExecuteSearchBody`'s body parsing. Either subclass or post-init walk:

```python
class ExecuteSearchBody(BaseModel):
    query: dict[str, Any] | None = None
    saved_search_id: uuid.UUID | None = None
    protocol_columns: list[str] | None = None

    @model_validator(mode="after")
    def _validate_structure_clauses(self) -> "ExecuteSearchBody":
        if self.query is None:
            return self
        from pydantic import TypeAdapter
        adapter = TypeAdapter(_StructureClause)

        def walk(criteria: list[dict]) -> None:
            for c in criteria:
                if c.get("type") == "structure":
                    payload = {k: v for k, v in c.items() if k != "type"}
                    adapter.validate_python(payload)
                elif c.get("type") == "group":
                    walk(c.get("criteria", []))

        walk(self.query.get("criteria", []))
        return self
```

- [ ] **Step 4: Run tests (should pass)**

Run: `uv run pytest backend/tests/api/test_search_request_validation.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/interface/routes/search.py \
        backend/tests/api/test_search_request_validation.py
git commit -m "feat(api): discriminated-union validation for structure search clauses"
```

---

### Task 19: New `GET /api/v1/search/algorithms` endpoint

**Files:**
- Create: `backend/src/cellar/interface/routes/search_algorithms.py`
- Modify: `backend/src/cellar/interface/main.py` (or wherever routers register — find by `include_router`)
- Test: `backend/tests/api/test_search_algorithms.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/api/test_search_algorithms.py
def test_algorithms_endpoint_returns_modes_and_algorithms(client, auth_headers):
    r = client.get("/api/v1/search/algorithms", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()

    mode_names = {m["name"] for m in body["modes"]}
    assert mode_names == {"similar", "scaffold_hop", "fragment_in_target"}

    similar = next(m for m in body["modes"] if m["name"] == "similar")
    assert similar["algorithm"] == "morgan"
    assert similar["metric"] == "tanimoto"
    assert similar["default_threshold"] == 0.7
    assert similar["label"] == "Similar"
    assert similar["description"]

    algorithm_names = {a["name"] for a in body["algorithms"]}
    assert algorithm_names == {"morgan", "fcfp"}
```

- [ ] **Step 2: Run test (404)**

- [ ] **Step 3: Implement the endpoint**

```python
# backend/src/cellar/interface/routes/search_algorithms.py
"""GET /api/v1/search/algorithms -- frontend renders mode radios from this."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.domain.sar_analysis.search_modes import MODE_DEFAULTS, SearchMode
from cellar.domain.sar_analysis.similarity_metric import serialize_metric
from cellar.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry

router = APIRouter(prefix="/api/v1/search", tags=["search"])
_registry = FingerprintRegistry.default()

_ALGORITHM_DESCRIPTIONS = {
    "morgan": "Circular topological FP (ECFP4-equivalent), stereo-aware",
    "fcfp": "Pharmacophore-flavored circular FP",
}


class _ModeInfo(BaseModel):
    name: str
    label: str
    description: str
    default_threshold: float
    algorithm: str
    metric: str


class _AlgorithmInfo(BaseModel):
    name: str
    description: str


class _AlgorithmsResponse(BaseModel):
    modes: list[_ModeInfo]
    algorithms: list[_AlgorithmInfo]


@router.get("/algorithms", response_model=_AlgorithmsResponse)
async def list_algorithms() -> _AlgorithmsResponse:
    modes = [
        _ModeInfo(
            name=mode.value,
            label=cfg.label,
            description=cfg.description,
            default_threshold=cfg.threshold,
            algorithm=cfg.algorithm,
            metric=serialize_metric(cfg.metric),
        )
        for mode, cfg in MODE_DEFAULTS.items()
    ]
    algorithms = [
        _AlgorithmInfo(
            name=a.name,
            description=_ALGORITHM_DESCRIPTIONS.get(a.name, ""),
        )
        for a in _registry.all()
    ]
    return _AlgorithmsResponse(modes=modes, algorithms=algorithms)
```

- [ ] **Step 4: Register the router**

In `backend/src/cellar/interface/main.py` (find by `include_router`), add:

```python
from cellar.interface.routes import search_algorithms
app.include_router(search_algorithms.router)
```

- [ ] **Step 5: Run test**

Run: `uv run pytest backend/tests/api/test_search_algorithms.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/interface/routes/search_algorithms.py \
        backend/src/cellar/interface/main.py \
        backend/tests/api/test_search_algorithms.py
git commit -m "feat(api): GET /search/algorithms exposes registry contents"
```

---

## Phase G — Frontend

### Task 20: Regenerate orval types

**Files:**
- Run orval against the updated OpenAPI schema.

- [ ] **Step 1: Start the backend so the OpenAPI spec is fresh**

Run: `cd backend && uv run uvicorn cellar.interface.main:app --reload &` (or use the dev compose if that's the project pattern).

- [ ] **Step 2: Regenerate types**

Run: `cd frontend && pnpm run codegen` (or `pnpm orval` — check `package.json` scripts).
Expected: a non-empty diff under `frontend/src/shared/api/` (or wherever orval emits). New types: `_SimilarityMatch`, `_SubstructureMatch`, `_AlgorithmsResponse`, etc.

- [ ] **Step 3: Type-check the frontend**

Run: `cd frontend && pnpm run typecheck`
Expected: no errors. If there are, the consumer code (search-query-builder etc.) is using old types — fix in Task 21.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/shared/api/
git commit -m "chore(frontend): regenerate orval client for new search schema"
```

---

### Task 21: Search-query-builder mode radios + threshold slider

**Files:**
- Modify: `frontend/src/features/research-organization/components/search-query-builder.tsx`

- [ ] **Step 1: Add a `useSearchAlgorithms` hook**

In `frontend/src/features/research-organization/hooks/use-search-algorithms.ts` (create if absent):

```ts
import { useQuery } from "@tanstack/react-query";
import { listSearchAlgorithms } from "@/shared/api/generated/search";

export function useSearchAlgorithms() {
  return useQuery({
    queryKey: ["search-algorithms"],
    queryFn: () => listSearchAlgorithms(),
    staleTime: Infinity,  // registry is effectively static
  });
}
```

(Adjust import path to whatever orval generates.)

- [ ] **Step 2: Update the structure section**

In `search-query-builder.tsx`, find the similarity branch. Replace the existing single threshold slider with:

```tsx
import { useSearchAlgorithms } from "../hooks/use-search-algorithms";

function SimilarityControls({
  value,
  onChange,
}: {
  value: { mode: string; threshold: number };
  onChange: (next: { mode: string; threshold: number }) => void;
}) {
  const { data } = useSearchAlgorithms();
  const modes = data?.modes ?? [];
  const currentMode = modes.find(m => m.name === value.mode);

  return (
    <div className="space-y-3">
      <RadioGroup
        value={value.mode}
        onValueChange={mode => {
          const m = modes.find(x => x.name === mode);
          onChange({ mode, threshold: m?.default_threshold ?? value.threshold });
        }}
      >
        {modes.map(m => (
          <RadioGroupItem key={m.name} value={m.name}>
            <div>
              <div className="font-medium">{m.label}</div>
              <div className="text-sm text-muted-foreground">{m.description}</div>
            </div>
          </RadioGroupItem>
        ))}
      </RadioGroup>

      <div className="space-y-1">
        <Label>Threshold: {value.threshold.toFixed(2)}</Label>
        <Slider
          min={0} max={1} step={0.01}
          value={[value.threshold]}
          onValueChange={([t]) => onChange({ ...value, threshold: t })}
        />
        <div className="text-xs text-muted-foreground">
          0.4 loose · 0.7 similar · 0.85 near-analog
        </div>
      </div>
    </div>
  );
}
```

Wire it into the existing similarity branch of the query builder, replacing the prior single slider.

- [ ] **Step 3: Build the request payload correctly**

When emitting the criterion to the API, include `kind: "similarity"`, `smiles`, `mode`, `threshold`. Drop the legacy `search_type: "similarity"`.

- [ ] **Step 4: Type-check + manual smoke**

Run: `cd frontend && pnpm run typecheck && pnpm run dev`
Open the search builder, pick each mode, run a search, verify results.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/research-organization/components/search-query-builder.tsx \
        frontend/src/features/research-organization/hooks/use-search-algorithms.ts
git commit -m "feat(frontend): mode radios + threshold defaults from /search/algorithms"
```

---

### Task 22: Substructure tab — generalized toggle

**Files:**
- Modify: `frontend/src/features/research-organization/components/search-query-builder.tsx`

- [ ] **Step 1: Add the checkbox**

Inside the substructure branch, add:

```tsx
<Checkbox
  checked={value.generalized ?? false}
  onCheckedChange={checked => onChange({ ...value, generalized: !!checked })}
>
  Allow tautomer / link-node matches
</Checkbox>
```

And ensure the request payload uses `kind: "substructure"`, `smiles_or_smarts`, `generalized`.

- [ ] **Step 2: Manual smoke**

Run a substructure search with a tautomer query (`OC1=CC=CC=N1`) twice — once with the box unchecked, once with it checked. Confirm the second returns the keto tautomer if registered.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/research-organization/components/search-query-builder.tsx
git commit -m "feat(frontend): generalized substructure toggle (mol_to_xqmol via @>>)"
```

---

### Task 23: Compound-search-bar quick path stays on default mode

**Files:**
- Modify: `frontend/src/features/chemical-registration/components/compound-search-bar.tsx`

The quick-search bar's "similarity" option should send `{kind: "similarity", smiles, mode: "similar"}` and let the backend defaults handle threshold.

- [ ] **Step 1: Update the request shape**

Find the similarity-emit code in `compound-search-bar.tsx` and change `{search_type: "similarity", smiles, threshold: 0.7}` to `{kind: "similarity", smiles, mode: "similar"}`.

- [ ] **Step 2: Manual smoke**

Type a SMILES into the quick-search bar, hit "Similarity" — confirm results return.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/chemical-registration/components/compound-search-bar.tsx
git commit -m "feat(frontend): quick-search similarity defaults to SearchMode.SIMILAR"
```

---

## Phase H — Smoke + close-out

### Task 24: Manual perf smoke + dev-mode debug log

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py`

- [ ] **Step 1: Add a debug log line**

Inside `search_similarity` and inside the composer-driven path, after the query executes, emit a structlog DEBUG line:

```python
import structlog
log = structlog.get_logger(__name__)

log.debug(
    "similarity_query",
    algorithm=algorithm_name,
    metric=serialize_metric(metric),
    threshold=threshold,
    candidates_screened=...  # row count if cheap; otherwise omit
    results_returned=len(results),
    elapsed_ms=...,
)
```

Use `time.perf_counter()` to measure. If `candidates_screened` is expensive, just omit it.

- [ ] **Step 2: Run a manual smoke**

Load demo data: `cd backend && uv run python -m cellar.demo_data.load` (or the project's loader entry point — check `demo-data/loaders/`).

With `LOG_LEVEL=DEBUG`, run each mode against a known SMILES via curl:

```bash
TOKEN=...
curl -s -H "Authorization: Bearer $TOKEN" \
  -X POST http://localhost:8000/api/v1/search/execute \
  -d '{"query":{"criteria":[{"type":"structure","kind":"similarity","smiles":"CCO","mode":"similar"}]}}' \
  | jq '.items | length'
```

Repeat for `scaffold_hop` and `fragment_in_target`. Record p50/p95 from the debug logs.

- [ ] **Step 3: Document numbers in a brief follow-up note**

Add a single line at the end of the spec doc:

```markdown
## Smoke results (2026-XX-XX)
- SIMILAR (Morgan/Tanimoto, threshold=0.7) — p50 X ms, p95 Y ms on N molecules
- SCAFFOLD_HOP (FCFP/Tanimoto, threshold=0.55) — p50 X ms, p95 Y ms
- FRAGMENT_IN_TARGET (Morgan/Tversky, threshold=0.7) — p50 X ms, p95 Y ms
```

If FRAGMENT_IN_TARGET p95 is more than 5× slower than SIMILAR (the Tversky GiST caveat from the spec), open a follow-up backlog item to layer the Tanimoto-prefilter strategy.

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py \
        docs/superpowers/specs/2026-05-08-similarity-substructure-search-design.md
git commit -m "feat(observability): debug log + smoke results for new search modes"
```

---

## Self-Review

**Spec coverage:**

- §Architecture (domain primitives) → Tasks 1, 2, 3 ✓
- §Architecture (registry + algorithms) → Tasks 4, 5, 6, 7 ✓
- §Schema & migration → Tasks 8, 9, 10 ✓
- §Persistence (similarity routing, Tversky) → Tasks 11, 12, 13 ✓
- §Persistence (substructure hygiene + generalized) → Task 11 (in `_substructure_clause`) ✓
- §API (discriminated union + algorithms endpoint) → Tasks 18, 19 ✓
- §UI (mode radios, threshold defaults, generalized toggle, quick-search defaults) → Tasks 21, 22, 23 ✓
- §Testing (stereo regression, dedup pin, SMARTS hygiene, generalized SS, mode round-trip, request validation) → Tasks 14, 15, 16, 17, 18, 19 ✓
- §Registration-path safety → Task 14 dedup-pin sub-test ✓
- §Tversky GiST caveat → Task 24 perf smoke + spec note ✓
- §Out-of-scope (FPSim2, MAP4, embeddings, 3D) → Not implemented (correct).

**Placeholder scan:** every code block contains executable code. No "TBD", "TODO", or "implement later". The Task 7 DI registration says "search for `FingerprintGenerator`" because the exact DI module name was not in the files I read; this is a directed exploration step, not a placeholder.

**Type consistency:**
- `MorganAlgorithm.name == "morgan"`, `column_name == "morgan_bfp"`, `cartridge_query_fn == "morganbv_fp"` — used consistently in registry, composer, and reader.
- `FCFPAlgorithm.name == "fcfp"`, `column_name == "fcfp_bfp"`, `cartridge_query_fn == "featmorganbv_fp"` — same.
- `SearchMode` values (`"similar"`, `"scaffold_hop"`, `"fragment_in_target"`) used in MODE_DEFAULTS, API enum binding, and FE radios.
- `serialize_metric()` produces `"tanimoto"` and `"tversky(α,β)"` — used in /algorithms response and debug logs.

**Scope check:** one implementation plan, ~24 bite-sized tasks. No orthogonal cleanup. Stays inside the spec's surgical-upgrade-plus-registry scope.
