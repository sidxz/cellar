# SAR Decomposition — Async Job + Endpoints (Part 1b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the async-job + HTTP-endpoints layer on top of the Part 1a decomposition foundation: version-aware hashing, batched member streaming, `StartDecompositionRun`/`RunDecomposition` use cases, Temporal workflow/activity + Null fallback + DI, and the four decomposition routes including the paginated `/rows` read-model.

**Architecture:** Mirrors the scaffold-tree async-job slice exactly (cache → inline ≤threshold → 202+Temporal job; Null asyncio fallback in dev; poll + cancel). Two deliberate divergences carried from the spec: (1) the job input carries the **source** (`collection_id` XOR a bounded `molecule_ids` list), re-expanded at run time so a >100K collection never materializes through Temporal history; (2) the result is read back as **SQL pages over assignment rows ⋈ molecules**, not a JSONB blob.

**Tech Stack:** Python 3.13 · SQLAlchemy 2.0 async · RDKit (`rdRGroupDecomposition`) · Temporal · Lagom DI · dry-python/returns · FastAPI · pytest (`asyncio_mode=auto`, testcontainers `uow` fixture, httpx `AsyncClient` api fixture). All commands run from `backend/`.

**Spec:** `docs/superpowers/specs/2026-06-11-sar-full-collection-coverage-design.md` (§4 backend compute & endpoints; this is the second half of Unit A — the activity-projection Pair 2 is a separate Part 2 plan).

**Handoff:** `docs/superpowers/specs/2026-06-15-sar-part1b-async-job-handoff.md`.

**Locked decisions (from brainstorming 2026-06-15):**
- Inline cutoff = **200 members** (`inline_threshold` default; below ⇒ sync READY run, above ⇒ 202 job).
- Member fetch = **sibling** `fetch_for_decomposition -> (id, smiles, version)` (the shared `fetch_for_scaffold_tree` is untouched).
- `/rows` v1 = **sort all columns** (physchem/reg#/name + `rgroups->>'Rn'`); `filter` param accepted but its AG-Grid mapping is deferred to Unit B.
- NULL-smiles members are **surfaced as unmatched, never dropped** (honest totals). Merged molecules (`merged_into_id IS NOT NULL`) are **excluded** from membership and from `/rows` (matches the molecule reader's visibility).
- `StartDecompositionRun` returns the bare `RGroupDecompositionRun` header; the route maps `READY→200`, else `→202`.
- The old synchronous `POST /api/v1/sar/r-group-decomposition` is **replaced, no shim**.

**No migration in Part 1b** — migration `057` (Part 1a) already created `rgroup_decomposition_runs` + `rgroup_assignments`. Confirm `alembic heads` is still `057_rgroup_decomposition_runs` before starting; if not, STOP and reconcile.

**Commit convention:** Every commit uses explicit pathspec (`git commit ... -- <paths>`) because the working tree may carry unrelated staged work, and ends with the trailer:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
(shown inline in each commit step below).

---

## File Structure

**Create (application):**
- `src/cellar/application/sar_analysis/hashing.py` — pure `compute_membership_hash`, `sha256_hex`.
- `src/cellar/application/sar_analysis/decomposition_members.py` — `MoleculeDecompositionFetcher` + `CollectionMemberIdReader` Protocols + `DecompositionMemberStream`.
- `src/cellar/application/sar_analysis/start_decomposition_run.py` — `RGroupDecompositionOrchestrator` Protocol, `StartDecompositionRunInput`, `StartDecompositionRun`.
- `src/cellar/application/sar_analysis/run_decomposition.py` — `RunDecomposition` + pure `ready_counts`.
- `src/cellar/application/sar_analysis/get_decomposition_run.py` — `GetDecompositionRunInput`, `GetDecompositionRun`.
- `src/cellar/application/sar_analysis/cancel_decomposition_run.py` — `CancelDecompositionRunInput`, `CancelDecompositionRun`.
- `src/cellar/application/sar_analysis/decomposition_rows.py` — `DecompositionRow`, `DecompositionRowSort`, `DecompositionRowReader` Protocol, `FetchDecompositionRowsInput/Output`, `FetchDecompositionRows`.

**Create (infrastructure):**
- `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py` — `SQLAlchemyDecompositionRowReader`.
- `src/cellar/infrastructure/temporal/workflows/rgroup_decomposition.py` — workflow + input dataclass.
- `src/cellar/infrastructure/temporal/activities/rgroup_decomposition.py` — activity + input dataclass.
- `src/cellar/infrastructure/temporal/orchestrators/rgroup_decomposition.py` — Temporal + Null orchestrators + runner Protocol.

**Modify:**
- `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py` — add `canonical_core_smiles`.
- `src/cellar/application/sar_analysis/rgroup_decomposition.py` — replace the dead functional `RGroupDecomposer` port with streaming ports `StreamingDecomposer` + `RGroupSession`.
- `src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py` — add `fetch_for_decomposition`.
- `src/cellar/infrastructure/di/_sar_analysis.py` — remove `DecomposeRGroups` + functional `RGroupDecomposer`; add all new registrations + Null orchestrator fallback.
- `src/cellar/interface/dependencies/_sar_analysis.py` — drop `DecomposeRGroupsDep`; add four new Deps.
- `src/cellar/interface/routes/sar_analysis.py` — replace the sync endpoint with the four new routes.
- `src/cellar/infrastructure/temporal/worker.py` — register workflow + activity.
- `src/cellar/interface/app.py` — lifespan orchestrator binding.
- `tests/unit/infrastructure/di/test_sar_analysis_wiring.py` — update wiring assertions.

**Delete:**
- `src/cellar/application/sar_analysis/decompose_rgroups.py` (use case removed).
- `tests/unit/application/sar_analysis/test_decompose_rgroups.py` (if present — old use-case test).

**Test (create):**
- `tests/unit/application/sar_analysis/test_hashing.py`
- `tests/unit/application/sar_analysis/test_decomposition_members.py`
- `tests/unit/application/sar_analysis/test_start_decomposition_run.py`
- `tests/unit/application/sar_analysis/test_run_decomposition.py`
- `tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py`
- `tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py`
- `tests/integration/persistence/chemical_registration/test_fetch_for_decomposition.py`
- `tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py`

**Test (modify):**
- `tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py` — append `canonical_core_smiles` test.
- `tests/api/test_sar_analysis_routes.py` — replace contents with the new endpoint tests.

---

## Task 0: Pre-flight

- [ ] **Step 1: Confirm the migration head + Part 1a seams are present**

Run: `cd backend && uv run alembic heads && uv run python -c "from cellar.infrastructure.rdkit.streaming_rgroup_decomposer import StreamingRGroupDecomposer; from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun; from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository; print('seams ok')"`
Expected: head is `057_rgroup_decomposition_runs`; prints `seams ok`. If the head differs, STOP and reconcile before continuing.

---

## Task 1: Pure hashing helpers

**Files:**
- Create: `src/cellar/application/sar_analysis/hashing.py`
- Test: `tests/unit/application/sar_analysis/test_hashing.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_hashing.py`:

```python
from __future__ import annotations

import uuid

from cellar.application.sar_analysis.hashing import (
    compute_membership_hash,
    sha256_hex,
)


def test_membership_hash_is_order_independent():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    h1 = compute_membership_hash([(a, 1), (b, 1), (c, 1)])
    h2 = compute_membership_hash([(c, 1), (a, 1), (b, 1)])
    assert h1 == h2


def test_membership_hash_is_version_aware():
    a, b = uuid.uuid4(), uuid.uuid4()
    base = compute_membership_hash([(a, 1), (b, 1)])
    bumped = compute_membership_hash([(a, 2), (b, 1)])
    assert base != bumped  # a merge / structure-correction bumps version -> miss


def test_membership_hash_changes_on_membership_change():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    two = compute_membership_hash([(a, 1), (b, 1)])
    three = compute_membership_hash([(a, 1), (b, 1), (c, 1)])
    assert two != three


def test_membership_hash_empty_is_stable():
    assert compute_membership_hash([]) == compute_membership_hash([])


def test_sha256_hex_is_deterministic_and_distinct():
    assert sha256_hex("c1ccccc1") == sha256_hex("c1ccccc1")
    assert sha256_hex("c1ccccc1") != sha256_hex("c1ccncc1")
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_hashing.py -v`
Expected: FAIL — `ModuleNotFoundError: ...hashing`.

- [ ] **Step 3: Implement the helpers**

Create `src/cellar/application/sar_analysis/hashing.py`:

```python
"""Pure hashing helpers for decomposition-run cache keys.

``compute_membership_hash`` folds ``(molecule_id, version)`` pairs into a stable,
order-independent SHA-256. It is **version-aware**: a merge or structure
correction bumps a member's ``version`` -> new hash -> cache miss -> recompute.
This removes the need for explicit invalidation handlers (the id-only
``compute_ids_hash`` in ``build_scaffold_network`` is deliberately NOT reused —
it cannot see a version change).

Both functions are pure (no RDKit, no I/O) so they live in the application layer.
Core-SMILES canonicalization is RDKit and lives in infrastructure; the caller
feeds the canonical string to ``sha256_hex``.
"""

from __future__ import annotations

import hashlib
from uuid import UUID


def compute_membership_hash(pairs: list[tuple[UUID, int]]) -> str:
    """SHA-256 of the sorted ``"id:version"`` strings. Order-independent."""
    payload = "\n".join(sorted(f"{mid}:{version}" for mid, version in pairs))
    return hashlib.sha256(payload.encode()).hexdigest()


def sha256_hex(text: str) -> str:
    """SHA-256 hex digest of ``text`` (used for the canonical core hash)."""
    return hashlib.sha256(text.encode()).hexdigest()
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_hashing.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): pure membership + core hash helpers" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/hashing.py tests/unit/application/sar_analysis/test_hashing.py
```

---

## Task 2: Core canonicalization + streaming-decomposer ports

The application layer must not import RDKit. It depends on the `StreamingDecomposer` Protocol (canonicalize + open a session); the concrete `StreamingRGroupDecomposer` (infra) implements it. We repurpose the now-dead `rgroup_decomposition.py` port module (its only consumer, `DecomposeRGroups`, is deleted in Task 10).

**Files:**
- Modify: `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py` (add `canonical_core_smiles`)
- Modify: `src/cellar/application/sar_analysis/rgroup_decomposition.py` (replace functional port with streaming ports)
- Test: `tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py` (append)

- [ ] **Step 1: Write the failing canonicalization test**

Append to `tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py`:

```python
def test_canonical_core_smiles_is_stable_across_equivalent_inputs():
    dec = StreamingRGroupDecomposer()
    # Two equivalent ways to write pyridine -> identical RDKit canonical SMILES.
    assert dec.canonical_core_smiles("c1ccncc1") == dec.canonical_core_smiles("n1ccccc1")


def test_canonical_core_smiles_distinguishes_different_cores():
    dec = StreamingRGroupDecomposer()
    assert dec.canonical_core_smiles("c1ccccc1") != dec.canonical_core_smiles("c1ccncc1")


def test_canonical_core_smiles_falls_back_to_stripped_raw_when_unparseable():
    dec = StreamingRGroupDecomposer()
    assert dec.canonical_core_smiles("  not-a-smiles  ") == "not-a-smiles"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py -k canonical -v`
Expected: FAIL — `AttributeError: 'StreamingRGroupDecomposer' object has no attribute 'canonical_core_smiles'`.

- [ ] **Step 3: Add `canonical_core_smiles` to the infra decomposer**

In `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py`, the file already imports `from rdkit import Chem`. Add this method to the `StreamingRGroupDecomposer` class (the factory at the bottom), next to `session`:

```python
    def canonical_core_smiles(self, core_smiles: str) -> str:
        """RDKit-canonical core SMILES; stable cache key for one core.

        Falls back to the stripped raw string when RDKit cannot parse it — an
        unparseable core still gets a deterministic (if non-canonical) key, and
        the decomposition itself fails closed downstream (all unmatched).
        """
        mol = Chem.MolFromSmiles(core_smiles)
        if mol is None:
            return core_smiles.strip()
        return Chem.MolToSmiles(mol)
```

- [ ] **Step 4: Replace the dead functional port with streaming ports**

Overwrite `src/cellar/application/sar_analysis/rgroup_decomposition.py` entirely:

```python
"""Application-layer ports for streaming R-group decomposition.

The concrete impl lives in
``cellar.infrastructure.rdkit.streaming_rgroup_decomposer.StreamingRGroupDecomposer``
and is wired via DI. The application layer depends only on these Protocols + the
domain result VO so the layer rule (application MUST NOT import infrastructure)
holds.

``RGroupSession`` accumulates molecules across batches and labels them
consistently only at ``finish()`` — the streaming-correctness keystone (one
shared RDKit object across batches; memory is O(matched set)).
"""

from __future__ import annotations

from typing import Any, Protocol

from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult


class RGroupSession(Protocol):
    def add(self, molecule_id: Any, smiles: str) -> bool: ...

    def finish(self) -> RGroupDecompositionResult: ...


class StreamingDecomposer(Protocol):
    def canonical_core_smiles(self, core_smiles: str) -> str: ...

    def session(self, *, core_smiles: str) -> RGroupSession: ...
```

- [ ] **Step 5: Run the decomposer tests + import-linter**

Run: `cd backend && uv run pytest tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py -v && uv run lint-imports`
Expected: all PASS; import-linter clean (the application port imports only the domain VO).

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): canonical-core hash input + streaming decomposer ports" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py src/cellar/application/sar_analysis/rgroup_decomposition.py tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py
```

---

## Task 3: Sibling fetcher `fetch_for_decomposition`

A new lean projection `(id, smiles, version)` for membership-hashing + the decomposer feed. Unlike `fetch_for_scaffold_tree`, it does **not** drop NULL-smiles rows (they must count as unmatched members) and it **excludes merged molecules** (`merged_into_id IS NULL`, matching the molecule reader's visibility and keeping membership consistent with `/rows`).

**Files:**
- Modify: `src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py`
- Test: `tests/integration/persistence/chemical_registration/test_fetch_for_decomposition.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/persistence/chemical_registration/test_fetch_for_decomposition.py`:

```python
"""Integration test for SQLAlchemyMoleculeRepository.fetch_for_decomposition."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)


async def _seed_org(uow, ws: uuid.UUID) -> uuid.UUID:
    org_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :n, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws, "n": f"org-{org_id.hex[:6]}"},
    )
    return org_id


async def _seed_molecule(
    uow,
    ws: uuid.UUID,
    org_id: uuid.UUID,
    *,
    reg: str,
    smiles: str | None,
    version: int = 1,
    merged_into_id: uuid.UUID | None = None,
) -> uuid.UUID:
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, smiles, version, originating_org_id, merged_into_id) VALUES "
            "(:id, :ws, :r, :r, 'small_molecule', :smi, :v, :org, :merged)"
        ),
        {
            "id": mol_id,
            "ws": ws,
            "r": reg,
            "smi": smiles,
            "v": version,
            "org": org_id,
            "merged": merged_into_id,
        },
    )
    return mol_id


@pytest.mark.asyncio
async def test_fetch_for_decomposition_returns_id_smiles_version(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        a = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1", version=3)
        b = await _seed_molecule(uow, ws, org, reg="CV-B", smiles="Clc1ccccc1", version=1)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        rows = await repo.fetch_for_decomposition(molecule_ids=[a, b], workspace_id=ws)

    by_id = {mid: (smi, ver) for (mid, smi, ver) in rows}
    assert by_id[a] == ("Fc1ccccc1", 3)
    assert by_id[b] == ("Clc1ccccc1", 1)


@pytest.mark.asyncio
async def test_fetch_for_decomposition_keeps_null_smiles_members(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        structureless = await _seed_molecule(uow, ws, org, reg="CV-N", smiles=None)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        rows = await repo.fetch_for_decomposition(molecule_ids=[structureless], workspace_id=ws)

    assert len(rows) == 1
    assert rows[0][0] == structureless
    assert rows[0][1] is None  # surfaced (will become an unmatched member), not dropped


@pytest.mark.asyncio
async def test_fetch_for_decomposition_excludes_merged_and_other_workspace(uow):
    ws = uuid.uuid4()
    other_ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        target = uuid.uuid4()
        merged = await _seed_molecule(
            uow, ws, org, reg="CV-M", smiles="CCO", merged_into_id=target
        )
        other_org = await _seed_org(uow, other_ws)
        foreign = await _seed_molecule(uow, other_ws, other_org, reg="CV-F", smiles="CCN")
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        rows = await repo.fetch_for_decomposition(
            molecule_ids=[merged, foreign], workspace_id=ws
        )

    assert rows == []  # merged excluded; foreign workspace excluded


@pytest.mark.asyncio
async def test_fetch_for_decomposition_empty_input_returns_empty(uow):
    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        assert await repo.fetch_for_decomposition(molecule_ids=[], workspace_id=uuid.uuid4()) == []
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/chemical_registration/test_fetch_for_decomposition.py -v`
Expected: FAIL — `AttributeError: ...has no attribute 'fetch_for_decomposition'`. (Requires Docker — testcontainers spins up Postgres.)

- [ ] **Step 3: Add the method**

In `src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py`, add `fetch_for_decomposition` next to the existing `fetch_for_scaffold_tree` (it already imports `select` and `MoleculeModel`):

```python
    async def fetch_for_decomposition(
        self, *, molecule_ids: list[uuid.UUID], workspace_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str | None, int]]:
        """Lean projection ``(id, smiles, version)`` for decomposition runs.

        Unlike ``fetch_for_scaffold_tree`` this KEEPS NULL-smiles rows — a
        structureless member must still count (it becomes ``unmatched``), so
        totals stay honest. Merged molecules (``merged_into_id IS NOT NULL``)
        are excluded, matching the molecule reader's visibility and keeping
        membership consistent with the ``/rows`` join.
        """
        if not molecule_ids:
            return []
        stmt = select(
            MoleculeModel.id,
            MoleculeModel.smiles,
            MoleculeModel.version,
        ).where(
            MoleculeModel.workspace_id == workspace_id,
            MoleculeModel.id.in_(molecule_ids),
            MoleculeModel.merged_into_id.is_(None),
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/chemical_registration/test_fetch_for_decomposition.py -v`
Expected: all PASS. (If `molecules` has additional NOT NULL columns without defaults, the INSERT will error — add them to `_seed_molecule` per the molecules schema.)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): fetch_for_decomposition projection (id, smiles, version)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py tests/integration/persistence/chemical_registration/test_fetch_for_decomposition.py
```

---

## Task 4: Batched member stream

`DecompositionMemberStream` pages `(id, smiles, version)` batches for a source. Collection source pages member ids via the (auth-free, workspace-scoped) collection repo and projects each page through `fetch_for_decomposition`; ad-hoc source chunks its bounded id list. Used twice (hash at start; decomposer feed at run). Both backing repos share the use case's UoW (wired in Tasks 5/6/10), so the stream is iterated inside the use case's `async with self._uow:`.

**Files:**
- Create: `src/cellar/application/sar_analysis/decomposition_members.py`
- Test: `tests/unit/application/sar_analysis/test_decomposition_members.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_decomposition_members.py`:

```python
from __future__ import annotations

import uuid

import pytest

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream


class FakeMoleculeFetcher:
    """Returns (id, smiles, version); honors NULL smiles; drops unknown ids."""

    def __init__(self, table: dict[uuid.UUID, tuple[str | None, int]]) -> None:
        self._table = table
        self.calls: list[list[uuid.UUID]] = []

    async def fetch_for_decomposition(self, *, molecule_ids, workspace_id):
        self.calls.append(list(molecule_ids))
        return [
            (mid, self._table[mid][0], self._table[mid][1])
            for mid in molecule_ids
            if mid in self._table
        ]


class FakeCollectionReader:
    """Pages a fixed id list via offset/limit."""

    def __init__(self, ids: list[uuid.UUID]) -> None:
        self._ids = ids

    async def get_molecule_ids(self, workspace_id, collection_id, *, offset, limit):
        return self._ids[offset : offset + limit]


async def _drain(stream, **kwargs):
    out = []
    async for batch in stream.stream(**kwargs):
        out.append(batch)
    return out


@pytest.mark.asyncio
async def test_ad_hoc_ids_are_chunked_by_page_size():
    ids = [uuid.uuid4() for _ in range(5)]
    table = {mid: ("Fc1ccccc1", 1) for mid in ids}
    fetcher = FakeMoleculeFetcher(table)
    stream = DecompositionMemberStream(
        molecule_fetcher=fetcher, collection_reader=FakeCollectionReader([]), page_size=2
    )
    batches = await _drain(stream, workspace_id=uuid.uuid4(), collection_id=None, molecule_ids=ids)
    assert [len(b) for b in batches] == [2, 2, 1]
    flat = [row for b in batches for row in b]
    assert {r[0] for r in flat} == set(ids)


@pytest.mark.asyncio
async def test_collection_source_pages_then_stops_on_short_page():
    ids = [uuid.uuid4() for _ in range(3)]
    table = {ids[0]: ("Fc1ccccc1", 2), ids[1]: (None, 1), ids[2]: ("Clc1ccccc1", 1)}
    fetcher = FakeMoleculeFetcher(table)
    stream = DecompositionMemberStream(
        molecule_fetcher=fetcher,
        collection_reader=FakeCollectionReader(ids),
        page_size=2,
    )
    batches = await _drain(
        stream, workspace_id=uuid.uuid4(), collection_id=uuid.uuid4(), molecule_ids=None
    )
    flat = [row for b in batches for row in b]
    assert len(flat) == 3
    # NULL smiles preserved as a member; version surfaced.
    by_id = {mid: (smi, ver) for (mid, smi, ver) in flat}
    assert by_id[ids[1]] == (None, 1)
    assert by_id[ids[0]] == ("Fc1ccccc1", 2)


@pytest.mark.asyncio
async def test_collection_source_handles_exact_multiple_page_boundary():
    ids = [uuid.uuid4() for _ in range(4)]
    table = {mid: ("CCO", 1) for mid in ids}
    stream = DecompositionMemberStream(
        molecule_fetcher=FakeMoleculeFetcher(table),
        collection_reader=FakeCollectionReader(ids),
        page_size=2,
    )
    batches = await _drain(
        stream, workspace_id=uuid.uuid4(), collection_id=uuid.uuid4(), molecule_ids=None
    )
    flat = [row for b in batches for row in b]
    assert len(flat) == 4  # no infinite loop, no missed/duplicate page


@pytest.mark.asyncio
async def test_empty_ad_hoc_source_yields_nothing():
    stream = DecompositionMemberStream(
        molecule_fetcher=FakeMoleculeFetcher({}),
        collection_reader=FakeCollectionReader([]),
    )
    batches = await _drain(
        stream, workspace_id=uuid.uuid4(), collection_id=None, molecule_ids=None
    )
    assert batches == []
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_decomposition_members.py -v`
Expected: FAIL — `ModuleNotFoundError: ...decomposition_members`.

- [ ] **Step 3: Implement the stream**

Create `src/cellar/application/sar_analysis/decomposition_members.py`:

```python
"""Batched member streaming for decomposition runs.

Streams ``(molecule_id, smiles, version)`` in pages so a >100K collection is
never materialized in one fetch. For a collection, member ids are paged via the
workspace-scoped collection repo (auth already enforced at the start route) and
each page is projected to ``(id, smiles, version)``; for an ad-hoc explicit set,
the bounded id list is chunked. Re-expansion at run time is why the job input
carries ``collection_id``, not ~1M ids through Temporal history.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from cellar.application.shared.pagination import COLLECTION_FETCH_MAX_PAGE_SIZE

MemberRow = tuple[UUID, str | None, int]


class MoleculeDecompositionFetcher(Protocol):
    async def fetch_for_decomposition(
        self, *, molecule_ids: list[UUID], workspace_id: UUID
    ) -> list[MemberRow]: ...


class CollectionMemberIdReader(Protocol):
    async def get_molecule_ids(
        self, workspace_id: UUID, collection_id: UUID, *, offset: int, limit: int
    ) -> list[UUID]: ...


class DecompositionMemberStream:
    def __init__(
        self,
        *,
        molecule_fetcher: MoleculeDecompositionFetcher,
        collection_reader: CollectionMemberIdReader,
        page_size: int = COLLECTION_FETCH_MAX_PAGE_SIZE,
    ) -> None:
        self._fetcher = molecule_fetcher
        self._collections = collection_reader
        self._page_size = page_size

    async def stream(
        self,
        *,
        workspace_id: UUID,
        collection_id: UUID | None,
        molecule_ids: list[UUID] | None,
    ) -> AsyncIterator[list[MemberRow]]:
        if collection_id is not None:
            offset = 0
            while True:
                page_ids = await self._collections.get_molecule_ids(
                    workspace_id, collection_id, offset=offset, limit=self._page_size
                )
                if not page_ids:
                    break
                rows = await self._fetcher.fetch_for_decomposition(
                    molecule_ids=page_ids, workspace_id=workspace_id
                )
                if rows:
                    yield rows
                if len(page_ids) < self._page_size:
                    break
                offset += self._page_size
            return

        ids = molecule_ids or []
        for i in range(0, len(ids), self._page_size):
            chunk = ids[i : i + self._page_size]
            rows = await self._fetcher.fetch_for_decomposition(
                molecule_ids=chunk, workspace_id=workspace_id
            )
            if rows:
                yield rows
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_decomposition_members.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): batched decomposition member stream (collection + ad-hoc)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/decomposition_members.py tests/unit/application/sar_analysis/test_decomposition_members.py
```

---

## Task 5: `RunDecomposition` use case (+ `ready_counts`)

The in-process runner the Temporal activity wraps and the Null orchestrator invokes inline. Mirrors `RunScaffoldTree`: load → `mark_running` (commit) → stream + decompose + `write_assignments` + `mark_ready` (commit); on exception `mark_failed` + reraise (Temporal retries). Streams the source by id at run time, workspace-scoped, no auth context. Defines the pure `ready_counts` bridge reused by `StartDecompositionRun`.

**Files:**
- Create: `src/cellar/application/sar_analysis/run_decomposition.py`
- Test: `tests/unit/application/sar_analysis/test_run_decomposition.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_run_decomposition.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.run_decomposition import RunDecomposition, ready_counts
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.domain.sar_analysis.rgroup_types import (
    RGroupAssignment,
    RGroupDecompositionResult,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRunRepo:
    def __init__(self, run: RGroupDecompositionRun | None) -> None:
        self._runs: dict[uuid.UUID, RGroupDecompositionRun] = {}
        if run is not None:
            self._runs[run.id] = run
        self.written: dict[uuid.UUID, list[RGroupAssignment]] = {}

    async def save(self, run):
        self._runs[run.id] = run

    async def find_by_id(self, run_id, *, workspace_id):
        run = self._runs.get(run_id)
        if run is None or run.workspace_id != workspace_id:
            return None
        return run

    async def write_assignments(self, run_id, assignments):
        self.written[run_id] = list(assignments)


class FakeSession:
    def __init__(self, result: RGroupDecompositionResult, *, raise_on_finish=False):
        self._result = result
        self._raise = raise_on_finish
        self.added: list[tuple] = []

    def add(self, molecule_id, smiles):
        self.added.append((molecule_id, smiles))
        return True

    def finish(self):
        if self._raise:
            raise RuntimeError("rdkit boom")
        return self._result


class FakeDecomposer:
    def __init__(self, session: FakeSession):
        self._session = session

    def canonical_core_smiles(self, core_smiles):
        return core_smiles

    def session(self, *, core_smiles):
        return self._session


class FakeStream:
    def __init__(self, batches):
        self._batches = batches

    async def stream(self, *, workspace_id, collection_id, molecule_ids):
        for batch in self._batches:
            yield batch


def _pending_run(ws: uuid.UUID) -> RGroupDecompositionRun:
    return RGroupDecompositionRun.create(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        membership_hash="m",
        core_smiles="c1ccccc1",
        core_hash="ch",
        now=_NOW,
    )


def test_ready_counts_bridge():
    a, b = uuid.uuid4(), uuid.uuid4()
    result = RGroupDecompositionResult(
        core_smiles="c1ccccc1",
        rgroup_labels=["R1"],
        assignments=[RGroupAssignment(molecule_id=a, rgroups={"R1": "F"})],
        unmatched_ids=[b],
    )
    assert ready_counts(result) == (1, 1, 2)


@pytest.mark.asyncio
async def test_run_marks_ready_with_assignments_and_counts():
    ws = uuid.uuid4()
    run = _pending_run(ws)
    matched, unmatched = uuid.uuid4(), uuid.uuid4()
    result = RGroupDecompositionResult(
        core_smiles="c1ccccc1",
        rgroup_labels=["R1"],
        assignments=[RGroupAssignment(molecule_id=matched, rgroups={"R1": "F"})],
        unmatched_ids=[unmatched],
    )
    repo = FakeRunRepo(run)
    uc = RunDecomposition(
        members=FakeStream([[(matched, "Fc1ccccc1", 1), (unmatched, "CCO", 1)]]),
        decomposer=FakeDecomposer(FakeSession(result)),
        repository=repo,
        uow=FakeUoW(),
    )

    await uc.run(run_id=run.id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=[matched, unmatched])

    saved = repo._runs[run.id]
    assert saved.status == RGroupDecompositionRunStatus.READY
    assert saved.rgroup_labels == ["R1"]
    assert (saved.matched_count, saved.unmatched_count, saved.total_count) == (1, 1, 2)
    assert repo.written[run.id][0].molecule_id == matched


@pytest.mark.asyncio
async def test_run_null_smiles_member_is_added_as_empty_string():
    ws = uuid.uuid4()
    run = _pending_run(ws)
    structureless = uuid.uuid4()
    session = FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1", unmatched_ids=[structureless]))
    uc = RunDecomposition(
        members=FakeStream([[(structureless, None, 1)]]),
        decomposer=FakeDecomposer(session),
        repository=FakeRunRepo(run),
        uow=FakeUoW(),
    )
    await uc.run(run_id=run.id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=[structureless])
    assert session.added == [(structureless, "")]  # None -> "" so the session routes it to unmatched


@pytest.mark.asyncio
async def test_run_marks_failed_and_reraises_on_exception():
    ws = uuid.uuid4()
    run = _pending_run(ws)
    repo = FakeRunRepo(run)
    uc = RunDecomposition(
        members=FakeStream([[(uuid.uuid4(), "Fc1ccccc1", 1)]]),
        decomposer=FakeDecomposer(FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1"), raise_on_finish=True)),
        repository=repo,
        uow=FakeUoW(),
    )
    with pytest.raises(RuntimeError, match="rdkit boom"):
        await uc.run(run_id=run.id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=[uuid.uuid4()])
    assert repo._runs[run.id].status == RGroupDecompositionRunStatus.FAILED
    assert "rdkit boom" in (repo._runs[run.id].error_message or "")


@pytest.mark.asyncio
async def test_run_skips_when_not_pending():
    ws = uuid.uuid4()
    cancelled = _pending_run(ws).mark_cancelled(_NOW)
    repo = FakeRunRepo(cancelled)
    session = FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1"))
    uc = RunDecomposition(
        members=FakeStream([]),
        decomposer=FakeDecomposer(session),
        repository=repo,
        uow=FakeUoW(),
    )
    await uc.run(run_id=cancelled.id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=[])
    assert repo._runs[cancelled.id].status == RGroupDecompositionRunStatus.CANCELLED
    assert session.added == []  # never decomposed a cancelled run
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_run_decomposition.py -v`
Expected: FAIL — `ModuleNotFoundError: ...run_decomposition`.

- [ ] **Step 3: Implement the runner**

Create `src/cellar/application/sar_analysis/run_decomposition.py`:

```python
"""RunDecomposition — in-process runner: load -> stream + decompose -> persist.

The Temporal activity wraps this; the Null orchestrator invokes it inline (dev /
tests). Mirrors RunScaffoldTree's state-machine handling so the activity is a
thin adapter. Members are re-streamed by source at run time, workspace-scoped,
with no auth context (authorization happened at the start route).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.rgroup_decomposition import StreamingDecomposer
from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRunStatus
from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult

logger = structlog.get_logger(__name__)


def ready_counts(result: RGroupDecompositionResult) -> tuple[int, int, int]:
    """The verified count bridge: (matched, unmatched, total)."""
    matched = len(result.assignments)
    unmatched = len(result.unmatched_ids)
    return matched, unmatched, matched + unmatched


@dataclass
class RunDecomposition:
    members: DecompositionMemberStream
    decomposer: StreamingDecomposer
    repository: RGroupDecompositionRunRepository
    uow: UnitOfWork

    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        log = logger.bind(run_id=str(run_id), workspace_id=str(workspace_id))
        try:
            async with self.uow:
                run = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                if run is None:
                    log.error("rgroup_decomposition_run_not_found")
                    return
                if run.status != RGroupDecompositionRunStatus.PENDING:
                    log.info("rgroup_decomposition_run_not_pending", status=str(run.status))
                    return
                running = run.mark_running(datetime.now(UTC))
                await self.repository.save(running)
                await self.uow.commit()

            async with self.uow:
                session = self.decomposer.session(core_smiles=core_smiles)
                async for batch in self.members.stream(
                    workspace_id=workspace_id,
                    collection_id=collection_id,
                    molecule_ids=molecule_ids,
                ):
                    for molecule_id, smiles, _version in batch:
                        session.add(molecule_id, smiles or "")
                result = session.finish()
                await self.repository.write_assignments(run_id, result.assignments)
                matched, unmatched, total = ready_counts(result)
                ready = running.mark_ready(
                    rgroup_labels=result.rgroup_labels,
                    matched_count=matched,
                    unmatched_count=unmatched,
                    total_count=total,
                    now=datetime.now(UTC),
                )
                await self.repository.save(ready)
                await self.uow.commit()
            log.info("rgroup_decomposition_run_ready", matched=matched, unmatched=unmatched)

        except Exception as exc:
            log.exception("rgroup_decomposition_run_failed")
            try:
                async with self.uow:
                    current = await self.repository.find_by_id(run_id, workspace_id=workspace_id)
                    if current is not None and current.status == RGroupDecompositionRunStatus.RUNNING:
                        failed = current.mark_failed(str(exc), datetime.now(UTC))
                        await self.repository.save(failed)
                        await self.uow.commit()
            except Exception:
                log.exception("rgroup_decomposition_fail_mark_failed")
            raise
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_run_decomposition.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): RunDecomposition runner (stream -> decompose -> persist)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/run_decomposition.py tests/unit/application/sar_analysis/test_run_decomposition.py
```

---

## Task 6: `StartDecompositionRun` use case

Single entry point. One pass over the member stream folds `membership_hash` over `(id, version)` + counts + buffers `(id, smiles)` only up to `inline_threshold` (so a 1M collection never materializes smiles). Then: cache hit ⇒ return prior READY header; miss + count ≤ 200 ⇒ decompose inline from the buffer, persist a READY run; miss + count > 200 ⇒ persist PENDING + `orchestrator.schedule(source)`. Returns the `RGroupDecompositionRun` header. Declares the `RGroupDecompositionOrchestrator` Protocol (the canonical app-layer port, mirroring where `ScaffoldTreeOrchestrator` lives).

**Files:**
- Create: `src/cellar/application/sar_analysis/start_decomposition_run.py`
- Test: `tests/unit/application/sar_analysis/test_start_decomposition_run.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_start_decomposition_run.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.application.sar_analysis.start_decomposition_run import (
    StartDecompositionRun,
    StartDecompositionRunInput,
)
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.domain.sar_analysis.rgroup_types import (
    RGroupAssignment,
    RGroupDecompositionResult,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRunRepo:
    def __init__(self, cached: RGroupDecompositionRun | None = None) -> None:
        self._runs: dict[uuid.UUID, RGroupDecompositionRun] = {}
        self._cached = cached
        self.written: dict[uuid.UUID, list[RGroupAssignment]] = {}

    async def save(self, run):
        self._runs[run.id] = run

    async def find_by_id(self, run_id, *, workspace_id):
        return self._runs.get(run_id)

    async def find_cached(self, *, membership_hash, core_hash):
        return self._cached

    async def write_assignments(self, run_id, assignments):
        self.written[run_id] = list(assignments)


class FakeSession:
    def __init__(self, result: RGroupDecompositionResult):
        self._result = result
        self.added: list[tuple] = []

    def add(self, molecule_id, smiles):
        self.added.append((molecule_id, smiles))
        return True

    def finish(self):
        return self._result


class FakeDecomposer:
    def __init__(self, session: FakeSession | None = None):
        self._session = session or FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1"))

    def canonical_core_smiles(self, core_smiles):
        return f"canon::{core_smiles}"

    def session(self, *, core_smiles):
        return self._session


class FakeStream:
    def __init__(self, batches):
        self._batches = batches

    async def stream(self, *, workspace_id, collection_id, molecule_ids):
        for batch in self._batches:
            yield batch


class FakeOrchestrator:
    def __init__(self):
        self.scheduled: list[dict] = []

    async def schedule(self, *, run_id, workspace_id, core_smiles, collection_id=None, molecule_ids=None):
        self.scheduled.append(
            {
                "run_id": run_id,
                "workspace_id": workspace_id,
                "core_smiles": core_smiles,
                "collection_id": collection_id,
                "molecule_ids": molecule_ids,
            }
        )

    async def cancel(self, *, run_id):
        pass


def _input(ws, *, collection_id=None, molecule_ids=None):
    return StartDecompositionRunInput(
        workspace_id=ws,
        requested_by=uuid.uuid4(),
        collection_id=collection_id,
        molecule_ids=molecule_ids,
        core_smiles="c1ccccc1",
        now=_NOW,
    )


@pytest.mark.asyncio
async def test_cache_hit_returns_prior_ready_run_without_compute():
    ws = uuid.uuid4()
    prior = (
        RGroupDecompositionRun.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
        )
        .mark_running(_NOW)
        .mark_ready(rgroup_labels=["R1"], matched_count=3, unmatched_count=0, total_count=3, now=_NOW)
    )
    repo = FakeRunRepo(cached=prior)
    orch = FakeOrchestrator()
    ids = [uuid.uuid4()]
    uc = StartDecompositionRun(
        members=FakeStream([[(ids[0], "Fc1ccccc1", 1)]]),
        decomposer=FakeDecomposer(),
        repository=repo,
        orchestrator=orch,
        uow=FakeUoW(),
    )
    out = await uc.execute(_input(ws, molecule_ids=ids))
    assert out.id == prior.id
    assert out.status == RGroupDecompositionRunStatus.READY
    assert orch.scheduled == []
    assert repo.written == {}  # no new compute


@pytest.mark.asyncio
async def test_inline_path_computes_persists_ready_and_assignments():
    ws = uuid.uuid4()
    matched, unmatched = uuid.uuid4(), uuid.uuid4()
    result = RGroupDecompositionResult(
        core_smiles="c1ccccc1",
        rgroup_labels=["R1"],
        assignments=[RGroupAssignment(molecule_id=matched, rgroups={"R1": "F"})],
        unmatched_ids=[unmatched],
    )
    repo = FakeRunRepo(cached=None)
    orch = FakeOrchestrator()
    uc = StartDecompositionRun(
        members=FakeStream([[(matched, "Fc1ccccc1", 1), (unmatched, "CCO", 1)]]),
        decomposer=FakeDecomposer(FakeSession(result)),
        repository=repo,
        orchestrator=orch,
        uow=FakeUoW(),
        inline_threshold=200,
    )
    out = await uc.execute(_input(ws, molecule_ids=[matched, unmatched]))
    assert out.status == RGroupDecompositionRunStatus.READY
    assert out.rgroup_labels == ["R1"]
    assert (out.matched_count, out.unmatched_count, out.total_count) == (1, 1, 2)
    assert repo.written[out.id][0].molecule_id == matched
    assert orch.scheduled == []  # inline, not scheduled


@pytest.mark.asyncio
async def test_async_path_schedules_pending_run_above_threshold():
    ws = uuid.uuid4()
    cid = uuid.uuid4()
    # 3 members but threshold=2 -> async.
    batch = [(uuid.uuid4(), "Fc1ccccc1", 1) for _ in range(3)]
    repo = FakeRunRepo(cached=None)
    orch = FakeOrchestrator()
    uc = StartDecompositionRun(
        members=FakeStream([batch]),
        decomposer=FakeDecomposer(),
        repository=repo,
        orchestrator=orch,
        uow=FakeUoW(),
        inline_threshold=2,
    )
    out = await uc.execute(_input(ws, collection_id=cid))
    assert out.status == RGroupDecompositionRunStatus.PENDING
    assert repo.written == {}  # nothing computed inline
    assert len(orch.scheduled) == 1
    assert orch.scheduled[0]["run_id"] == out.id
    assert orch.scheduled[0]["collection_id"] == cid  # source passed, not expanded ids


@pytest.mark.asyncio
async def test_empty_input_yields_ready_empty_run():
    ws = uuid.uuid4()
    repo = FakeRunRepo(cached=None)
    uc = StartDecompositionRun(
        members=FakeStream([]),
        decomposer=FakeDecomposer(FakeSession(RGroupDecompositionResult(core_smiles="c1ccccc1"))),
        repository=repo,
        orchestrator=FakeOrchestrator(),
        uow=FakeUoW(),
    )
    out = await uc.execute(_input(ws, molecule_ids=[]))
    assert out.status == RGroupDecompositionRunStatus.READY
    assert out.total_count == 0
    assert out.rgroup_labels == []
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_start_decomposition_run.py -v`
Expected: FAIL — `ModuleNotFoundError: ...start_decomposition_run`.

- [ ] **Step 3: Implement the use case**

Create `src/cellar/application/sar_analysis/start_decomposition_run.py`:

```python
"""StartDecompositionRun — single entry point for the decomposition endpoint.

Dispatches one of three paths (mirrors StartScaffoldTreeJob):
1. Cache hit (any size)        -> return the prior READY run header.
2. Cache miss, <= inline_threshold -> decompose inline, persist a READY run.
3. Cache miss, > inline_threshold  -> persist PENDING + schedule the workflow.

A single pass over the member stream folds ``membership_hash`` over
``(id, version)``, counts members, and buffers ``(id, smiles)`` only up to the
inline threshold — so a huge collection is hashed/counted without materializing
its structures. The job is scheduled with the **source** (``collection_id`` or a
bounded id list), never the expanded membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.hashing import compute_membership_hash, sha256_hex
from cellar.application.sar_analysis.rgroup_decomposition import StreamingDecomposer
from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.sar_analysis.run_decomposition import ready_counts
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun


@dataclass(frozen=True)
class StartDecompositionRunInput:
    workspace_id: UUID
    requested_by: UUID
    collection_id: UUID | None
    molecule_ids: list[UUID] | None
    core_smiles: str
    now: datetime


class RGroupDecompositionOrchestrator(Protocol):
    async def schedule(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None: ...

    async def cancel(self, *, run_id: UUID) -> None: ...


class StartDecompositionRun:
    def __init__(
        self,
        *,
        members: DecompositionMemberStream,
        decomposer: StreamingDecomposer,
        repository: RGroupDecompositionRunRepository,
        orchestrator: RGroupDecompositionOrchestrator,
        uow: UnitOfWork,
        inline_threshold: int = 200,
    ) -> None:
        self._members = members
        self._decomposer = decomposer
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow
        self._inline_threshold = inline_threshold

    async def execute(self, payload: StartDecompositionRunInput) -> RGroupDecompositionRun:
        core_hash = sha256_hex(self._decomposer.canonical_core_smiles(payload.core_smiles))

        async with self._uow:
            pairs, buffer, count = await self._collect(payload)
            membership_hash = compute_membership_hash(pairs)

            cached = await self._repo.find_cached(
                membership_hash=membership_hash, core_hash=core_hash
            )
            if cached is not None:
                return cached

            run = RGroupDecompositionRun.create(
                workspace_id=payload.workspace_id,
                requested_by=payload.requested_by,
                membership_hash=membership_hash,
                core_smiles=payload.core_smiles,
                core_hash=core_hash,
                now=payload.now,
            )

            if count <= self._inline_threshold:
                running = run.mark_running(payload.now)
                await self._repo.save(running)
                await self._uow.commit()  # run row must exist before assignment FKs

                session = self._decomposer.session(core_smiles=payload.core_smiles)
                for molecule_id, smiles in buffer:
                    session.add(molecule_id, smiles or "")
                result = session.finish()
                await self._repo.write_assignments(run.id, result.assignments)
                matched, unmatched, total = ready_counts(result)
                ready = running.mark_ready(
                    rgroup_labels=result.rgroup_labels,
                    matched_count=matched,
                    unmatched_count=unmatched,
                    total_count=total,
                    now=payload.now,
                )
                await self._repo.save(ready)
                await self._uow.commit()
                return ready

            await self._repo.save(run)
            await self._uow.commit()

        await self._orchestrator.schedule(
            run_id=run.id,
            workspace_id=payload.workspace_id,
            core_smiles=payload.core_smiles,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
        )
        return run

    async def _collect(
        self, payload: StartDecompositionRunInput
    ) -> tuple[list[tuple[UUID, int]], list[tuple[UUID, str | None]], int]:
        """One pass: fold (id, version) for the hash, count, buffer (id, smiles)
        only while at/under the inline threshold."""
        pairs: list[tuple[UUID, int]] = []
        buffer: list[tuple[UUID, str | None]] = []
        overflowed = False
        async for batch in self._members.stream(
            workspace_id=payload.workspace_id,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
        ):
            for molecule_id, smiles, version in batch:
                pairs.append((molecule_id, version))
                if not overflowed:
                    buffer.append((molecule_id, smiles))
                    if len(buffer) > self._inline_threshold:
                        overflowed = True
                        buffer = []  # release — this run will be async
        return pairs, buffer, len(pairs)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_start_decomposition_run.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(sar): StartDecompositionRun (cache -> inline <=200 -> 202 job)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/start_decomposition_run.py tests/unit/application/sar_analysis/test_start_decomposition_run.py
```

---

## Task 7: `GetDecompositionRun` + `CancelDecompositionRun`

Poll + cancel. Mirror `GetScaffoldTreeJob` / `CancelScaffoldTreeJob` exactly (Result-returning; cancel is idempotent on terminal runs and forwards to `orchestrator.cancel`).

**Files:**
- Create: `src/cellar/application/sar_analysis/get_decomposition_run.py`
- Create: `src/cellar/application/sar_analysis/cancel_decomposition_run.py`
- Test: `tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from returns.result import Failure, Success

from cellar.application.sar_analysis.cancel_decomposition_run import (
    CancelDecompositionRun,
    CancelDecompositionRunInput,
)
from cellar.application.sar_analysis.get_decomposition_run import (
    GetDecompositionRun,
    GetDecompositionRunInput,
)
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class FakeRunRepo:
    def __init__(self, run: RGroupDecompositionRun | None = None) -> None:
        self._runs: dict[uuid.UUID, RGroupDecompositionRun] = {}
        if run is not None:
            self._runs[run.id] = run

    async def save(self, run):
        self._runs[run.id] = run

    async def find_by_id(self, run_id, *, workspace_id):
        run = self._runs.get(run_id)
        if run is None or run.workspace_id != workspace_id:
            return None
        return run


class FakeOrchestrator:
    def __init__(self):
        self.cancelled: list[uuid.UUID] = []

    async def cancel(self, *, run_id):
        self.cancelled.append(run_id)


def _pending(ws):
    return RGroupDecompositionRun.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
    )


@pytest.mark.asyncio
async def test_get_returns_run():
    ws = uuid.uuid4()
    run = _pending(ws)
    uc = GetDecompositionRun(repository=FakeRunRepo(run), uow=FakeUoW())
    out = await uc.execute(GetDecompositionRunInput(run_id=run.id, workspace_id=ws))
    assert isinstance(out, Success)
    assert out.unwrap().id == run.id


@pytest.mark.asyncio
async def test_get_missing_is_failure():
    uc = GetDecompositionRun(repository=FakeRunRepo(), uow=FakeUoW())
    out = await uc.execute(GetDecompositionRunInput(run_id=uuid.uuid4(), workspace_id=uuid.uuid4()))
    assert isinstance(out, Failure)


@pytest.mark.asyncio
async def test_get_other_workspace_is_failure():
    ws = uuid.uuid4()
    run = _pending(ws)
    uc = GetDecompositionRun(repository=FakeRunRepo(run), uow=FakeUoW())
    out = await uc.execute(GetDecompositionRunInput(run_id=run.id, workspace_id=uuid.uuid4()))
    assert isinstance(out, Failure)


@pytest.mark.asyncio
async def test_cancel_marks_cancelled_and_forwards_to_orchestrator():
    ws = uuid.uuid4()
    run = _pending(ws)
    repo = FakeRunRepo(run)
    orch = FakeOrchestrator()
    uc = CancelDecompositionRun(repository=repo, orchestrator=orch, uow=FakeUoW())
    out = await uc.execute(CancelDecompositionRunInput(run_id=run.id, workspace_id=ws, now=_NOW))
    assert isinstance(out, Success)
    assert out.unwrap().status == RGroupDecompositionRunStatus.CANCELLED
    assert orch.cancelled == [run.id]


@pytest.mark.asyncio
async def test_cancel_terminal_run_is_idempotent_no_op():
    ws = uuid.uuid4()
    ready = _pending(ws).mark_running(_NOW).mark_ready(
        rgroup_labels=[], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
    )
    repo = FakeRunRepo(ready)
    orch = FakeOrchestrator()
    uc = CancelDecompositionRun(repository=repo, orchestrator=orch, uow=FakeUoW())
    out = await uc.execute(CancelDecompositionRunInput(run_id=ready.id, workspace_id=ws, now=_NOW))
    assert isinstance(out, Success)
    assert out.unwrap().status == RGroupDecompositionRunStatus.READY  # unchanged


@pytest.mark.asyncio
async def test_cancel_missing_is_failure():
    uc = CancelDecompositionRun(repository=FakeRunRepo(), orchestrator=FakeOrchestrator(), uow=FakeUoW())
    out = await uc.execute(
        CancelDecompositionRunInput(run_id=uuid.uuid4(), workspace_id=uuid.uuid4(), now=_NOW)
    )
    assert isinstance(out, Failure)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement Get**

Create `src/cellar/application/sar_analysis/get_decomposition_run.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class GetDecompositionRunInput:
    run_id: UUID
    workspace_id: UUID


class GetDecompositionRun:
    def __init__(self, *, repository: RGroupDecompositionRunRepository, uow: UnitOfWork) -> None:
        self._repo = repository
        self._uow = uow

    async def execute(
        self, payload: GetDecompositionRunInput
    ) -> Result[RGroupDecompositionRun, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
        if run is None:
            return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
        return Success(run)
```

- [ ] **Step 4: Implement Cancel**

Create `src/cellar/application/sar_analysis/cancel_decomposition_run.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.sar_analysis.start_decomposition_run import RGroupDecompositionOrchestrator
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    InvalidRGroupRunTransition,
    RGroupDecompositionRun,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class CancelDecompositionRunInput:
    run_id: UUID
    workspace_id: UUID
    now: datetime


class CancelDecompositionRun:
    def __init__(
        self,
        *,
        repository: RGroupDecompositionRunRepository,
        orchestrator: RGroupDecompositionOrchestrator,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._orchestrator = orchestrator
        self._uow = uow

    async def execute(
        self, payload: CancelDecompositionRunInput
    ) -> Result[RGroupDecompositionRun, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            try:
                cancelled = run.mark_cancelled(payload.now)
            except InvalidRGroupRunTransition:
                return Success(run)  # already terminal — idempotent no-op
            await self._repo.save(cancelled)
            await self._uow.commit()
        await self._orchestrator.cancel(run_id=run.id)
        return Success(cancelled)
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): GetDecompositionRun + CancelDecompositionRun use cases" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/get_decomposition_run.py src/cellar/application/sar_analysis/cancel_decomposition_run.py tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py
```

---

## Task 8: `/rows` read-model — reader + `FetchDecompositionRows`

A SQL page over `rgroup_assignments ⋈ rgroup_decomposition_runs ⋈ molecules`, workspace-scoped via the run, with `merged_into_id IS NULL` (matches the molecule reader's visibility). Sort on molecule columns (reg#/name/MW/cLogP/TPSA) or an R-group via `rgroups->>'Rn'`, always with a `molecule_id` tiebreaker for stable pagination. `total` is the count of the *same visible join* (so it stays consistent with what `/rows` returns even if a matched molecule was later merged).

**Files:**
- Create: `src/cellar/application/sar_analysis/decomposition_rows.py`
- Create: `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py`
- Test: `tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py`

- [ ] **Step 1: Write the application DTOs + ports + use case**

Create `src/cellar/application/sar_analysis/decomposition_rows.py`:

```python
"""Read-model contract for the decomposition ``/rows`` endpoint.

A bounded SQL page over assignment rows joined to molecules. Sort is driven by a
list of ``DecompositionRowSort`` (molecule columns or R-group labels); ``filter``
mapping (AG-Grid filterModel) is deferred to Unit B. ``activity`` arrives in
Part 2 (activity projection), so it is not part of this contract yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from returns.result import Failure, Result, Success

from cellar.application.sar_analysis.repositories import RGroupDecompositionRunRepository
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True)
class DecompositionRow:
    molecule_id: UUID
    smiles: str | None
    registration_number: str
    name: str
    rgroups: dict[str, str]
    molecular_weight: float | None
    logp: float | None
    tpsa: float | None


@dataclass(frozen=True)
class DecompositionRowSort:
    col: str
    direction: str  # "asc" | "desc"


class DecompositionRowReader(Protocol):
    async def fetch_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        offset: int,
        limit: int,
        sort: list[DecompositionRowSort],
    ) -> list[DecompositionRow]: ...

    async def count_rows(self, run_id: UUID, *, workspace_id: UUID) -> int: ...


@dataclass(frozen=True)
class FetchDecompositionRowsInput:
    run_id: UUID
    workspace_id: UUID
    offset: int
    limit: int
    sort: list[DecompositionRowSort]


@dataclass(frozen=True)
class FetchDecompositionRowsOutput:
    rows: list[DecompositionRow]
    total: int


class FetchDecompositionRows:
    def __init__(
        self,
        *,
        repository: RGroupDecompositionRunRepository,
        reader: DecompositionRowReader,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repository
        self._reader = reader
        self._uow = uow

    async def execute(
        self, payload: FetchDecompositionRowsInput
    ) -> Result[FetchDecompositionRowsOutput, DomainError]:
        async with self._uow:
            run = await self._repo.find_by_id(payload.run_id, workspace_id=payload.workspace_id)
            if run is None:
                return Failure(NotFoundError("RGroupDecompositionRun", str(payload.run_id)))
            rows = await self._reader.fetch_rows(
                payload.run_id,
                workspace_id=payload.workspace_id,
                offset=payload.offset,
                limit=payload.limit,
                sort=payload.sort,
            )
            total = await self._reader.count_rows(
                payload.run_id, workspace_id=payload.workspace_id
            )
        return Success(FetchDecompositionRowsOutput(rows=rows, total=total))
```

- [ ] **Step 2: Write the failing integration test**

Create `tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py`:

```python
"""Integration tests for SQLAlchemyDecompositionRowReader (assignment ⋈ molecule)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.application.sar_analysis.decomposition_rows import DecompositionRowSort
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.decomposition_row_reader import (
    SQLAlchemyDecompositionRowReader,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


async def _seed_org(uow, ws):
    org_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :n, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws, "n": f"org-{org_id.hex[:6]}"},
    )
    return org_id


async def _seed_molecule(uow, ws, org, *, reg, smiles, mw=None, logp=None, tpsa=None, merged=None):
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, molecular_weight, logp, tpsa, version, originating_org_id, merged_into_id) "
            "VALUES (:id, :ws, :r, :r, 'small_molecule', :smi, :mw, :logp, :tpsa, 1, :org, :merged)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "smi": smiles, "mw": mw, "logp": logp,
         "tpsa": tpsa, "org": org, "merged": merged},
    )
    return mol_id


async def _seed_ready_run(uow, ws):
    run = RGroupDecompositionRun.create(
        workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
        core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
    ).mark_running(_NOW).mark_ready(
        rgroup_labels=["R1"], matched_count=0, unmatched_count=0, total_count=0, now=_NOW
    )
    repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
    await repo.save(run)
    return run


@pytest.mark.asyncio
async def test_fetch_rows_joins_molecule_fields(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        m = await _seed_molecule(uow, ws, org, reg="CV-1", smiles="Fc1ccccc1", mw=96.1, logp=1.8, tpsa=0.0)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.write_assignments(run.id, [RGroupAssignment(molecule_id=m, rgroups={"R1": "F"})])
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[])
        total = await reader.count_rows(run.id, workspace_id=ws)

    assert total == 1
    row = rows[0]
    assert row.molecule_id == m
    assert row.smiles == "Fc1ccccc1"
    assert row.registration_number == "CV-1"
    assert row.rgroups == {"R1": "F"}
    assert row.molecular_weight == pytest.approx(96.1)
    assert row.logp == pytest.approx(1.8)


@pytest.mark.asyncio
async def test_fetch_rows_sorts_by_registration_number(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        asg = []
        for reg in ("CV-C", "CV-A", "CV-B"):
            m = await _seed_molecule(uow, ws, org, reg=reg, smiles="Fc1ccccc1")
            asg.append(RGroupAssignment(molecule_id=m, rgroups={"R1": "F"}))
        await repo.write_assignments(run.id, asg)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        asc = await reader.fetch_rows(
            run.id, workspace_id=ws, offset=0, limit=50,
            sort=[DecompositionRowSort(col="registration_number", direction="asc")],
        )
    assert [r.registration_number for r in asc] == ["CV-A", "CV-B", "CV-C"]


@pytest.mark.asyncio
async def test_fetch_rows_sorts_by_rgroup_label(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        asg = []
        for reg, r1 in (("CV-1", "Cl"), ("CV-2", "Br"), ("CV-3", "F")):
            m = await _seed_molecule(uow, ws, org, reg=reg, smiles="Fc1ccccc1")
            asg.append(RGroupAssignment(molecule_id=m, rgroups={"R1": r1}))
        await repo.write_assignments(run.id, asg)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(
            run.id, workspace_id=ws, offset=0, limit=50,
            sort=[DecompositionRowSort(col="R1", direction="asc")],
        )
    assert [r.rgroups["R1"] for r in rows] == ["Br", "Cl", "F"]


@pytest.mark.asyncio
async def test_fetch_rows_paginates_stably(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        asg = []
        for i in range(5):
            m = await _seed_molecule(uow, ws, org, reg=f"CV-{i}", smiles="Fc1ccccc1")
            asg.append(RGroupAssignment(molecule_id=m, rgroups={"R1": "F"}))
        await repo.write_assignments(run.id, asg)
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        p1 = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=2, sort=[])
        p2 = await reader.fetch_rows(run.id, workspace_id=ws, offset=2, limit=2, sort=[])
        p3 = await reader.fetch_rows(run.id, workspace_id=ws, offset=4, limit=2, sort=[])
    seen = [r.molecule_id for r in (*p1, *p2, *p3)]
    assert len(seen) == 5 and len(set(seen)) == 5


@pytest.mark.asyncio
async def test_fetch_rows_excludes_merged_and_scopes_workspace(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        run = await _seed_ready_run(uow, ws)
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        visible = await _seed_molecule(uow, ws, org, reg="CV-V", smiles="Fc1ccccc1")
        merged = await _seed_molecule(uow, ws, org, reg="CV-M", smiles="CCO", merged=uuid.uuid4())
        await repo.write_assignments(
            run.id,
            [
                RGroupAssignment(molecule_id=visible, rgroups={"R1": "F"}),
                RGroupAssignment(molecule_id=merged, rgroups={"R1": "OH"}),
            ],
        )
        await uow.commit()

    async with uow:
        reader = SQLAlchemyDecompositionRowReader(uow)
        rows = await reader.fetch_rows(run.id, workspace_id=ws, offset=0, limit=50, sort=[])
        total = await reader.count_rows(run.id, workspace_id=ws)
        other = await reader.fetch_rows(run.id, workspace_id=uuid.uuid4(), offset=0, limit=50, sort=[])

    assert {r.molecule_id for r in rows} == {visible}  # merged excluded
    assert total == 1
    assert other == []  # wrong workspace sees nothing
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -v`
Expected: FAIL — `ModuleNotFoundError: ...decomposition_row_reader`. (Requires Docker.)

- [ ] **Step 4: Implement the reader**

Create `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py`:

```python
"""SQLAlchemy read-model for the decomposition ``/rows`` endpoint.

Joins assignment rows to molecules, scoped to the run's workspace and the
molecule reader's visibility (``merged_into_id IS NULL``). Sort accepts molecule
columns or an R-group label (``rgroups->>'Rn'``), always with a ``molecule_id``
tiebreaker for stable pagination.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from cellar.application.sar_analysis.decomposition_rows import (
    DecompositionRow,
    DecompositionRowSort,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_models import (  # noqa: E501
    RGroupAssignmentModel,
    RGroupDecompositionRunModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_MOLECULE_SORT_COLS: dict[str, Any] = {
    "registration_number": MoleculeModel.registration_number,
    "name": MoleculeModel.name,
    "molecular_weight": MoleculeModel.molecular_weight,
    "logp": MoleculeModel.logp,
    "tpsa": MoleculeModel.tpsa,
}
_RGROUP_LABEL = re.compile(r"^R\d+$")


def _sort_column(col: str):
    """Resolve a sort key to a column expression, or None if unrecognized."""
    if col in _MOLECULE_SORT_COLS:
        return _MOLECULE_SORT_COLS[col]
    if _RGROUP_LABEL.match(col):
        return RGroupAssignmentModel.rgroups[col].as_string()
    return None


class SQLAlchemyDecompositionRowReader:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    def _scoped_join(self, stmt, run_id: UUID, workspace_id: UUID):
        return (
            stmt.join(
                RGroupDecompositionRunModel,
                RGroupDecompositionRunModel.id == RGroupAssignmentModel.run_id,
            )
            .join(MoleculeModel, MoleculeModel.id == RGroupAssignmentModel.molecule_id)
            .where(
                RGroupAssignmentModel.run_id == run_id,
                RGroupDecompositionRunModel.workspace_id == workspace_id,
                MoleculeModel.workspace_id == workspace_id,
                MoleculeModel.merged_into_id.is_(None),
            )
        )

    async def fetch_rows(
        self,
        run_id: UUID,
        *,
        workspace_id: UUID,
        offset: int,
        limit: int,
        sort: list[DecompositionRowSort],
    ) -> list[DecompositionRow]:
        stmt = self._scoped_join(
            select(
                RGroupAssignmentModel.molecule_id,
                MoleculeModel.smiles,
                MoleculeModel.registration_number,
                MoleculeModel.name,
                RGroupAssignmentModel.rgroups,
                MoleculeModel.molecular_weight,
                MoleculeModel.logp,
                MoleculeModel.tpsa,
            ),
            run_id,
            workspace_id,
        )

        order_by = []
        for spec in sort:
            col = _sort_column(spec.col)
            if col is None:
                continue  # unknown sort key — ignored (lenient); tiebreaker keeps it stable
            order_by.append(col.desc().nulls_last() if spec.direction == "desc" else col.asc().nulls_last())
        order_by.append(RGroupAssignmentModel.molecule_id)  # stable tiebreaker

        stmt = stmt.order_by(*order_by).offset(offset).limit(limit)
        result = await self._uow.session.execute(stmt)
        return [
            DecompositionRow(
                molecule_id=row[0],
                smiles=row[1],
                registration_number=row[2],
                name=row[3],
                rgroups=dict(row[4]),
                molecular_weight=row[5],
                logp=row[6],
                tpsa=row[7],
            )
            for row in result.all()
        ]

    async def count_rows(self, run_id: UUID, *, workspace_id: UUID) -> int:
        stmt = self._scoped_join(
            select(func.count()).select_from(RGroupAssignmentModel), run_id, workspace_id
        )
        return int((await self._uow.session.execute(stmt)).scalar_one())
```

- [ ] **Step 5: Run the integration test to confirm it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py -v`
Expected: all PASS. (If `molecules` requires more NOT NULL columns, extend `_seed_molecule`.)

- [ ] **Step 6: Run import-linter (the application port must not leak infra)**

Run: `cd backend && uv run lint-imports`
Expected: PASS — `decomposition_rows.py` imports only application/domain; the reader lives in infrastructure.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(sar): /rows read-model — assignment ⋈ molecule page + count" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/sar_analysis/decomposition_rows.py src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py
```

---

## Task 9: Temporal orchestrator + workflow + activity

Mirror `scaffold_tree` exactly, with the source (`collection_id` XOR `molecule_ids`) carried as strings across the workflow/activity boundary. **Generous baked timeout** (1h `start_to_close`, `maximum_attempts=3`) for large streamed computes — these are baked into workflow history at schedule time.

**Files:**
- Create: `src/cellar/infrastructure/temporal/activities/rgroup_decomposition.py`
- Create: `src/cellar/infrastructure/temporal/workflows/rgroup_decomposition.py`
- Create: `src/cellar/infrastructure/temporal/orchestrators/rgroup_decomposition.py`
- Test: `tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py`

- [ ] **Step 1: Write the failing orchestrator test**

Create `tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py`:

```python
"""Null + Temporal orchestrator behavior for R-group decomposition.

The Null path (TEMPORAL_DISABLED=1 / tests) runs the runner inline as a
fire-and-forget task. The Temporal path converts UUIDs to strings and starts the
workflow on the main task queue.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from cellar.infrastructure.temporal.orchestrators.rgroup_decomposition import (
    NullRGroupDecompositionOrchestrator,
    TemporalRGroupDecompositionOrchestrator,
)


class FakeRunner:
    def __init__(self):
        self.calls: list[dict] = []
        self.done = asyncio.Event()

    async def run(self, *, run_id, workspace_id, core_smiles, collection_id=None, molecule_ids=None):
        self.calls.append(
            {
                "run_id": run_id,
                "workspace_id": workspace_id,
                "core_smiles": core_smiles,
                "collection_id": collection_id,
                "molecule_ids": molecule_ids,
            }
        )
        self.done.set()


@pytest.mark.asyncio
async def test_null_orchestrator_runs_runner_inline():
    runner = FakeRunner()
    orch = NullRGroupDecompositionOrchestrator(runner)
    run_id, ws, cid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await orch.schedule(run_id=run_id, workspace_id=ws, core_smiles="c1ccccc1", collection_id=cid)
    await asyncio.wait_for(runner.done.wait(), timeout=1.0)
    assert runner.calls[0]["run_id"] == run_id
    assert runner.calls[0]["collection_id"] == cid


@pytest.mark.asyncio
async def test_null_orchestrator_cancel_is_noop():
    orch = NullRGroupDecompositionOrchestrator(FakeRunner())
    await orch.cancel(run_id=uuid.uuid4())  # must not raise


class FakeClient:
    def __init__(self):
        self.started: list[dict] = []

    async def start_workflow(self, run_fn, arg, *, id, task_queue):
        self.started.append({"arg": arg, "id": id, "task_queue": task_queue})


@pytest.mark.asyncio
async def test_temporal_orchestrator_serializes_source_to_strings():
    client = FakeClient()
    orch = TemporalRGroupDecompositionOrchestrator(client)
    run_id, ws = uuid.uuid4(), uuid.uuid4()
    mids = [uuid.uuid4(), uuid.uuid4()]
    await orch.schedule(run_id=run_id, workspace_id=ws, core_smiles="c1ccccc1", molecule_ids=mids)
    started = client.started[0]
    assert started["id"] == f"rgroup-decomposition-{run_id}"
    assert started["arg"].run_id == str(run_id)
    assert started["arg"].workspace_id == str(ws)
    assert started["arg"].collection_id is None
    assert started["arg"].molecule_ids == [str(m) for m in mids]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the activity**

Create `src/cellar/infrastructure/temporal/activities/rgroup_decomposition.py`:

```python
"""RGroupDecompositionActivities — Temporal activity delegating to RunDecomposition.

RunDecomposition is injected at worker boot so the activity is a thin adapter.
The source (collection_id XOR molecule_ids) crosses the boundary as strings.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from temporalio import activity

from cellar.application.sar_analysis.run_decomposition import RunDecomposition


@dataclass
class RunDecompositionInput:
    run_id: str
    workspace_id: str
    core_smiles: str
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


class RGroupDecompositionActivities:
    def __init__(self, run_decomposition: RunDecomposition) -> None:
        self._run = run_decomposition

    @activity.defn
    async def run_rgroup_decomposition(self, input: RunDecompositionInput) -> None:
        collection_id = uuid.UUID(input.collection_id) if input.collection_id else None
        molecule_ids = [uuid.UUID(m) for m in input.molecule_ids] if input.molecule_ids else None
        await self._run.run(
            run_id=uuid.UUID(input.run_id),
            workspace_id=uuid.UUID(input.workspace_id),
            core_smiles=input.core_smiles,
            collection_id=collection_id,
            molecule_ids=molecule_ids,
        )
```

- [ ] **Step 4: Implement the workflow**

Create `src/cellar/infrastructure/temporal/workflows/rgroup_decomposition.py`:

```python
"""RGroupDecompositionWorkflow — durable single-activity wrapper for RunDecomposition.

One workflow per decomposition run. The 1-hour timeout is generous because the
activity streams the (re-expanded) collection and decomposes it; timeout + retry
are baked into history at schedule time, so changing them later does not affect
in-flight workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from cellar.infrastructure.temporal.activities.rgroup_decomposition import (
        RGroupDecompositionActivities,
        RunDecompositionInput,
    )


@dataclass
class RGroupDecompositionWorkflowInput:
    run_id: str
    workspace_id: str
    core_smiles: str
    collection_id: str | None = None
    molecule_ids: list[str] = field(default_factory=list)


@workflow.defn
class RGroupDecompositionWorkflow:
    @workflow.run
    async def run(self, input: RGroupDecompositionWorkflowInput) -> None:
        await workflow.execute_activity(
            RGroupDecompositionActivities.run_rgroup_decomposition,
            RunDecompositionInput(
                run_id=input.run_id,
                workspace_id=input.workspace_id,
                core_smiles=input.core_smiles,
                collection_id=input.collection_id,
                molecule_ids=input.molecule_ids,
            ),
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
```

- [ ] **Step 5: Implement the orchestrators**

Create `src/cellar/infrastructure/temporal/orchestrators/rgroup_decomposition.py`:

```python
"""Orchestrator implementations for the R-group decomposition workflow.

``TemporalRGroupDecompositionOrchestrator`` submits the workflow and cancels via
handle. ``NullRGroupDecompositionOrchestrator`` runs RunDecomposition inline as a
fire-and-forget asyncio task (dev / tests). Mirrors scaffold_tree exactly.
"""

from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from temporalio.client import Client

from cellar.application.sar_analysis.run_decomposition import RunDecomposition
from cellar.infrastructure.temporal.task_queues import MAIN_TASK_QUEUE
from cellar.infrastructure.temporal.workflows.rgroup_decomposition import (
    RGroupDecompositionWorkflow,
    RGroupDecompositionWorkflowInput,
)


class RGroupDecompositionRunner(Protocol):
    async def run(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None: ...


class TemporalRGroupDecompositionOrchestrator:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def schedule(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        await self._client.start_workflow(
            RGroupDecompositionWorkflow.run,
            RGroupDecompositionWorkflowInput(
                run_id=str(run_id),
                workspace_id=str(workspace_id),
                core_smiles=core_smiles,
                collection_id=str(collection_id) if collection_id is not None else None,
                molecule_ids=[str(m) for m in (molecule_ids or [])],
            ),
            id=f"rgroup-decomposition-{run_id}",
            task_queue=MAIN_TASK_QUEUE,
        )

    async def cancel(self, *, run_id: UUID) -> None:
        handle = self._client.get_workflow_handle(f"rgroup-decomposition-{run_id}")
        await handle.cancel()


class NullRGroupDecompositionOrchestrator:
    """In-process fallback when Temporal is unavailable."""

    def __init__(self, runner: RGroupDecompositionRunner | RunDecomposition) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def schedule(
        self,
        *,
        run_id: UUID,
        workspace_id: UUID,
        core_smiles: str,
        collection_id: UUID | None = None,
        molecule_ids: list[UUID] | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._runner.run(
                run_id=run_id,
                workspace_id=workspace_id,
                core_smiles=core_smiles,
                collection_id=collection_id,
                molecule_ids=molecule_ids,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def cancel(self, *, run_id: UUID) -> None:
        return None  # inline tasks cannot be cancelled by run id
```

- [ ] **Step 6: Run the orchestrator tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(sar): Temporal workflow/activity + Null orchestrator for decomposition" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/temporal/activities/rgroup_decomposition.py src/cellar/infrastructure/temporal/workflows/rgroup_decomposition.py src/cellar/infrastructure/temporal/orchestrators/rgroup_decomposition.py tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py
```

---

## Task 10: DI wiring + remove the old sync path + Dep aliases

Register all new use cases (per-resolve UoW shared with the member stream + repo + reader), the `StreamingRGroupDecomposer` Singleton, and the Null orchestrator fallback. Remove `DecomposeRGroups` + the now-dead functional `RGroupDecomposer`. Add the four route Dep aliases; drop `DecomposeRGroupsDep`.

**Files:**
- Delete: `src/cellar/application/sar_analysis/decompose_rgroups.py`
- Delete (if present): `tests/unit/application/sar_analysis/test_decompose_rgroups.py`
- Modify: `src/cellar/infrastructure/di/_sar_analysis.py`
- Modify: `src/cellar/interface/dependencies/_sar_analysis.py`
- Modify: `tests/unit/infrastructure/di/test_sar_analysis_wiring.py`

- [ ] **Step 1: Delete the old sync use case + its test**

```bash
cd backend && rm -f src/cellar/application/sar_analysis/decompose_rgroups.py tests/unit/application/sar_analysis/test_decompose_rgroups.py
```

- [ ] **Step 2: Edit `_sar_analysis.py` imports**

In `src/cellar/infrastructure/di/_sar_analysis.py`:

Remove this import (line ~37):
```python
from cellar.application.sar_analysis.decompose_rgroups import DecomposeRGroups
```
Remove this import (line ~66):
```python
from cellar.infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer
```
Change the `repositories` import to add the new repo:
```python
from cellar.application.sar_analysis.repositories import (
    RGroupDecompositionRunRepository,
    ScaffoldTreeJobRepository,
    UmapJobRepository,
)
```
Add these imports (group with the other `application.sar_analysis` imports):
```python
from cellar.application.sar_analysis.cancel_decomposition_run import CancelDecompositionRun
from cellar.application.sar_analysis.decomposition_members import DecompositionMemberStream
from cellar.application.sar_analysis.decomposition_rows import FetchDecompositionRows
from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRun
from cellar.application.sar_analysis.run_decomposition import RunDecomposition
from cellar.application.sar_analysis.start_decomposition_run import (
    RGroupDecompositionOrchestrator,
    StartDecompositionRun,
)
```
Add these imports (group with the other infrastructure imports):
```python
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.decomposition_row_reader import (  # noqa: E501
    SQLAlchemyDecompositionRowReader,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)
from cellar.infrastructure.rdkit.streaming_rgroup_decomposer import StreamingRGroupDecomposer
```

- [ ] **Step 3: Replace the old RGroupDecomposer/DecomposeRGroups block with the new registrations**

In `register_sar_analysis`, delete the entire block (the `RGroupDecomposer` Singleton + `_decompose_rgroups` + its `container.define`, currently lines ~99–111):

```python
    # --- Pure RDKit wrapper, no deps → Singleton ---
    container.define(RGroupDecomposer, Singleton(RGroupDecomposer))

    # --- Use case: fresh UoW per resolve, shared by the use case and its repo ---
    def _decompose_rgroups(c: Container) -> DecomposeRGroups:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DecomposeRGroups(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            decomposer=c[RGroupDecomposer],
            uow=uow,
        )

    container.define(DecomposeRGroups, _decompose_rgroups)
```

Replace it with:

```python
    # --- Streaming R-group decomposer (pure RDKit wrapper, no deps) → Singleton ---
    container.define(StreamingRGroupDecomposer, Singleton(StreamingRGroupDecomposer))

    # --- RGroupDecompositionRunRepository — per-resolve fresh UoW ---
    def _rgroup_run_repo(c: Container) -> RGroupDecompositionRunRepository:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SQLAlchemyRGroupDecompositionRunRepository(uow)  # type: ignore[return-value]

    container.define(RGroupDecompositionRunRepository, _rgroup_run_repo)

    # --- RunDecomposition — in-process runner the Temporal activity wraps. The
    # member stream + repo share one UoW so streaming + persistence are one tx. ---
    def _run_decomposition(c: Container) -> RunDecomposition:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        members = DecompositionMemberStream(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            collection_reader=SQLAlchemyCollectionRepository(uow),
        )
        return RunDecomposition(
            members=members,
            decomposer=c[StreamingRGroupDecomposer],
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            uow=uow,
        )

    container.define(RunDecomposition, _run_decomposition)

    # --- RGroupDecompositionOrchestrator — Null when TEMPORAL_DISABLED=1; live
    # TemporalRGroupDecompositionOrchestrator bound by app.py's lifespan. ---
    if os.environ.get("TEMPORAL_DISABLED") == "1":
        from cellar.infrastructure.temporal.orchestrators.rgroup_decomposition import (
            NullRGroupDecompositionOrchestrator,
        )

        def _null_rgroup_orchestrator(c: Container) -> NullRGroupDecompositionOrchestrator:
            return NullRGroupDecompositionOrchestrator(c[RunDecomposition])

        container.define(RGroupDecompositionOrchestrator, _null_rgroup_orchestrator)

    # --- Decomposition use cases (each shares one UoW across its collaborators) ---
    def _start_decomposition(c: Container) -> StartDecompositionRun:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        members = DecompositionMemberStream(
            molecule_fetcher=SQLAlchemyMoleculeRepository(uow),
            collection_reader=SQLAlchemyCollectionRepository(uow),
        )
        return StartDecompositionRun(
            members=members,
            decomposer=c[StreamingRGroupDecomposer],
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            orchestrator=c[RGroupDecompositionOrchestrator],
            uow=uow,
        )

    def _get_decomposition(c: Container) -> GetDecompositionRun:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetDecompositionRun(
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            uow=uow,
        )

    def _cancel_decomposition(c: Container) -> CancelDecompositionRun:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CancelDecompositionRun(
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            orchestrator=c[RGroupDecompositionOrchestrator],
            uow=uow,
        )

    def _fetch_decomposition_rows(c: Container) -> FetchDecompositionRows:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return FetchDecompositionRows(
            repository=SQLAlchemyRGroupDecompositionRunRepository(uow),
            reader=SQLAlchemyDecompositionRowReader(uow),
            uow=uow,
        )

    container.define(StartDecompositionRun, _start_decomposition)
    container.define(GetDecompositionRun, _get_decomposition)
    container.define(CancelDecompositionRun, _cancel_decomposition)
    container.define(FetchDecompositionRows, _fetch_decomposition_rows)
```

> Ordering matters: `RunDecomposition` is defined before the Null-orchestrator fallback (which resolves `c[RunDecomposition]`) and `StartDecompositionRun`/`CancelDecompositionRun` after the orchestrator (which they resolve via `c[RGroupDecompositionOrchestrator]`).

- [ ] **Step 4: Update the route Dep aliases**

In `src/cellar/interface/dependencies/_sar_analysis.py`:

Remove the `DecomposeRGroups` import, the `"DecomposeRGroupsDep",` entry in `__all__`, and the `DecomposeRGroupsDep = Annotated[...]` line.

Add to the imports:
```python
from cellar.application.sar_analysis.cancel_decomposition_run import CancelDecompositionRun
from cellar.application.sar_analysis.decomposition_rows import FetchDecompositionRows
from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRun
from cellar.application.sar_analysis.start_decomposition_run import StartDecompositionRun
```

Add to `__all__`:
```python
    "CancelDecompositionRunDep",
    "FetchDecompositionRowsDep",
    "GetDecompositionRunDep",
    "StartDecompositionRunDep",
```

Add the aliases (next to the scaffold-tree ones):
```python
StartDecompositionRunDep = Annotated[
    StartDecompositionRun, Depends(_get_use_case(StartDecompositionRun))
]
GetDecompositionRunDep = Annotated[
    GetDecompositionRun, Depends(_get_use_case(GetDecompositionRun))
]
CancelDecompositionRunDep = Annotated[
    CancelDecompositionRun, Depends(_get_use_case(CancelDecompositionRun))
]
FetchDecompositionRowsDep = Annotated[
    FetchDecompositionRows, Depends(_get_use_case(FetchDecompositionRows))
]
```

- [ ] **Step 5: Update the DI wiring test**

In `tests/unit/infrastructure/di/test_sar_analysis_wiring.py`, find any assertion that resolves `DecomposeRGroups` and remove it. Add a test that the new use cases resolve when `TEMPORAL_DISABLED=1` (mirror the existing scaffold-tree wiring test). Append:

```python
def test_decomposition_use_cases_resolve_with_temporal_disabled(monkeypatch):
    monkeypatch.setenv("TEMPORAL_DISABLED", "1")
    from lagom import Container

    from cellar.application.sar_analysis.cancel_decomposition_run import CancelDecompositionRun
    from cellar.application.sar_analysis.decomposition_rows import FetchDecompositionRows
    from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRun
    from cellar.application.sar_analysis.run_decomposition import RunDecomposition
    from cellar.application.sar_analysis.start_decomposition_run import StartDecompositionRun
    from cellar.infrastructure.di import build_container  # adjust to the real factory

    container: Container = build_container()
    assert isinstance(container[RunDecomposition], RunDecomposition)
    assert isinstance(container[StartDecompositionRun], StartDecompositionRun)
    assert isinstance(container[GetDecompositionRun], GetDecompositionRun)
    assert isinstance(container[CancelDecompositionRun], CancelDecompositionRun)
    assert isinstance(container[FetchDecompositionRows], FetchDecompositionRows)
```

> Open `tests/unit/infrastructure/di/test_sar_analysis_wiring.py` first and copy its existing container-construction helper (e.g. `register_sar_analysis(Container())` or a `build_container`/`create_container` import) — use the exact same construction the file already uses rather than the placeholder `build_container` above.

- [ ] **Step 6: Verify no dangling references + run the wiring test**

Run: `cd backend && grep -rn "DecomposeRGroups\|decompose_rgroups\|infrastructure.rdkit.rgroup_decomposer import RGroupDecomposer" src/ tests/ ; echo "--- (the only hits should be the functional rgroup_decomposer.py module itself + its oracle test) ---"; uv run pytest tests/unit/infrastructure/di/test_sar_analysis_wiring.py -v`
Expected: no references to the deleted use case in `di/`, `routes/`, `dependencies/`; the wiring test PASSES. (The functional `infrastructure/rdkit/rgroup_decomposer.py` + `tests/unit/infrastructure/rdkit/test_rgroup_decomposer.py` remain — that class is the streaming oracle and is imported directly by the test, not via DI.)

- [ ] **Step 7: Commit**

```bash
git commit -m "wire(sar): DI for decomposition use cases; drop old sync DecomposeRGroups" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/di/_sar_analysis.py src/cellar/interface/dependencies/_sar_analysis.py tests/unit/infrastructure/di/test_sar_analysis_wiring.py
```

---

## Task 11: Temporal worker registration + app.py lifespan binding

Register the new workflow + activity with the worker, and bind the live `TemporalRGroupDecompositionOrchestrator` (or Null fallback) in the app lifespan — mirroring the scaffold-tree wiring exactly. These are infra edits exercised by the worker boot test (Step 4) and the route smoke (Task 12).

**Files:**
- Modify: `src/cellar/infrastructure/temporal/worker.py`
- Modify: `src/cellar/interface/app.py`

- [ ] **Step 1: Register the workflow + activity in the worker**

In `src/cellar/infrastructure/temporal/worker.py`:

Add imports (next to the scaffold-tree workflow/activity imports):
```python
from cellar.application.sar_analysis.run_decomposition import RunDecomposition
from cellar.infrastructure.temporal.activities.rgroup_decomposition import (
    RGroupDecompositionActivities,
)
from cellar.infrastructure.temporal.workflows.rgroup_decomposition import (
    RGroupDecompositionWorkflow,
)
```

After the scaffold-tree activity instance is constructed (recon: `run_scaffold_tree = container[RunScaffoldTree]` / `scaffold_tree_activities = ScaffoldTreeActivities(run_scaffold_tree)`), add:
```python
    # --- R-group decomposition activity ---
    run_rgroup_decomposition = container[RunDecomposition]
    rgroup_decomposition_activities = RGroupDecompositionActivities(run_rgroup_decomposition)
```

In the `Worker(...)` call, add `RGroupDecompositionWorkflow` to the `workflows=[...]` list (after `ScaffoldTreeWorkflow`):
```python
        ScaffoldTreeWorkflow,
        RGroupDecompositionWorkflow,
```
…and add the activity to the `activities=[...]` list (after `scaffold_tree_activities.run_scaffold_tree`):
```python
        scaffold_tree_activities.run_scaffold_tree,
        rgroup_decomposition_activities.run_rgroup_decomposition,
```

- [ ] **Step 2: Bind the orchestrator in the app lifespan**

In `src/cellar/interface/app.py`:

Add imports next to the existing temporal-orchestrator imports:
```python
from cellar.application.sar_analysis.start_decomposition_run import (
    RGroupDecompositionOrchestrator,
)
from cellar.infrastructure.temporal.orchestrators.rgroup_decomposition import (
    NullRGroupDecompositionOrchestrator,
    TemporalRGroupDecompositionOrchestrator,
)
```

In the lifespan, where the other orchestrators are chosen (recon lines ~114–139): in the `if app.state.temporal_client is not None:` branch add:
```python
    rgroup_orch: RGroupDecompositionOrchestrator = TemporalRGroupDecompositionOrchestrator(
        app.state.temporal_client
    )
```
…and in the `else:` branch (which already does inline `from ... import RunScaffoldTree` etc.) add:
```python
    from cellar.application.sar_analysis.run_decomposition import RunDecomposition

    rgroup_orch = NullRGroupDecompositionOrchestrator(container[RunDecomposition])
```
…and in the `container.define(...)` block (with the other `Singleton(lambda: ...)` orchestrator bindings) add:
```python
    container.define(RGroupDecompositionOrchestrator, Singleton(lambda: rgroup_orch))
```

- [ ] **Step 3: Confirm the worker module imports cleanly + app boots**

Run: `cd backend && uv run python -c "import cellar.infrastructure.temporal.worker; import cellar.interface.app; print('boot imports ok')"`
Expected: prints `boot imports ok` (no import-time errors; the workflow sandbox import guard is satisfied via `workflow.unsafe.imports_passed_through()`).

- [ ] **Step 4: Run the existing temporal worker/wiring tests to confirm nothing regressed**

Run: `cd backend && uv run pytest tests/unit/infrastructure/temporal/ -v`
Expected: all PASS (including the new orchestrator test from Task 9 and any existing worker-registration test).

- [ ] **Step 5: Commit**

```bash
git commit -m "wire(sar): register decomposition workflow/activity + lifespan orchestrator" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/infrastructure/temporal/worker.py src/cellar/interface/app.py
```

---

## Task 12: Routes (replace sync endpoint) + API tests

Replace `POST /api/v1/sar/r-group-decomposition` with the four decomposition routes (no shim). Literal `jobs/...` routes are declared before `/{run_id}/rows` so the path param never shadows `jobs`. API tests cover validation + DI wiring + an inline happy-path through HTTP + 404s (matching house convention; the real join/sort coverage lives in Task 8's integration test).

**Files:**
- Modify (full rewrite): `src/cellar/interface/routes/sar_analysis.py`
- Modify (replace contents): `tests/api/test_sar_analysis_routes.py`

- [ ] **Step 1: Write the new API tests first (replace the file contents)**

Overwrite `tests/api/test_sar_analysis_routes.py`:

```python
"""API tests for the decomposition endpoints (POST /api/v1/sar/decomposition + jobs + rows).

Scope: route validation, DI wiring, an inline happy-path through HTTP, and 404s.
The join/sort/pagination internals are covered by the row-reader integration test.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


async def _seed_two_molecules(api_app, ws: uuid.UUID) -> list[uuid.UUID]:
    session_factory = api_app.state.container[async_sessionmaker]
    org_id = uuid.uuid4()
    ids = [uuid.uuid4(), uuid.uuid4()]
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, :n, 'internal', true, 1)"
            ),
            {"id": org_id, "ws": ws, "n": "org-sar"},
        )
        for mid, reg, smi in zip(ids, ("CV-A", "CV-B"), ("Fc1ccccc1", "Clc1ccccc1"), strict=True):
            await session.execute(
                text(
                    "INSERT INTO molecules (id, workspace_id, registration_number, name, "
                    "molecule_type, smiles, version, originating_org_id) VALUES "
                    "(:id, :ws, :r, :r, 'small_molecule', :smi, 1, :org)"
                ),
                {"id": mid, "ws": ws, "r": reg, "smi": smi, "org": org_id},
            )
        await session.commit()
    return ids


@pytest.mark.asyncio
async def test_rejects_both_inputs(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [], "collection_id": str(uuid.uuid4()), "core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 400
    assert "exactly one" in res.json()["detail"]


@pytest.mark.asyncio
async def test_rejects_neither_input(client: AsyncClient) -> None:
    res = await client.post("/api/v1/sar/decomposition", json={"core_smiles": "c1ccccc1"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_rejects_empty_core(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/decomposition", json={"molecule_ids": [], "core_smiles": "   "}
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_empty_molecule_ids_returns_ready_empty_run(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/decomposition", json={"molecule_ids": [], "core_smiles": "c1ccccc1"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["total_count"] == 0
    assert body["rgroup_labels"] == []
    assert uuid.UUID(body["run_id"])  # a real run id


@pytest.mark.asyncio
async def test_inline_decomposition_then_rows(client, api_app, workspace_id) -> None:
    ids = await _seed_two_molecules(api_app, workspace_id)
    res = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [str(i) for i in ids], "core_smiles": "c1ccccc1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["matched_count"] == 2
    assert body["total_count"] == 2
    assert body["rgroup_labels"]  # at least R1
    run_id = body["run_id"]

    rows_res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows", json={"offset": 0, "limit": 50}
    )
    assert rows_res.status_code == 200
    rows_body = rows_res.json()
    assert rows_body["total"] == 2
    assert {r["registration_number"] for r in rows_body["rows"]} == {"CV-A", "CV-B"}
    a_row = next(r for r in rows_body["rows"] if r["registration_number"] == "CV-A")
    assert a_row["smiles"] == "Fc1ccccc1"
    assert a_row["rgroups"]  # R-group assignments present


@pytest.mark.asyncio
async def test_rows_sort_by_registration_number_desc(client, api_app, workspace_id) -> None:
    ids = await _seed_two_molecules(api_app, workspace_id)
    start = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [str(i) for i in ids], "core_smiles": "c1ccccc1"},
    )
    run_id = start.json()["run_id"]
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows",
        json={"sort": [{"col": "registration_number", "dir": "desc"}]},
    )
    assert [r["registration_number"] for r in res.json()["rows"]] == ["CV-B", "CV-A"]


@pytest.mark.asyncio
async def test_poll_inline_run_is_ready(client, api_app, workspace_id) -> None:
    ids = await _seed_two_molecules(api_app, workspace_id)
    start = await client.post(
        "/api/v1/sar/decomposition",
        json={"molecule_ids": [str(i) for i in ids], "core_smiles": "c1ccccc1"},
    )
    run_id = start.json()["run_id"]
    poll = await client.get(f"/api/v1/sar/decomposition/jobs/{run_id}")
    assert poll.status_code == 200
    assert poll.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_get_nonexistent_run_404(client: AsyncClient) -> None:
    res = await client.get(f"/api/v1/sar/decomposition/jobs/{uuid.uuid4()}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_cancel_nonexistent_run_404(client: AsyncClient) -> None:
    res = await client.post(f"/api/v1/sar/decomposition/jobs/{uuid.uuid4()}/cancel")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_rows_nonexistent_run_404(client: AsyncClient) -> None:
    res = await client.post(f"/api/v1/sar/decomposition/{uuid.uuid4()}/rows", json={})
    assert res.status_code == 404
```

> Confirm the `workspace_id` fixture name in `tests/api/conftest.py` (recon shows `fake_auth(workspace_id, user_id)`). If the fixture is named differently, adjust the test signatures.

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd backend && uv run pytest tests/api/test_sar_analysis_routes.py -v`
Expected: FAIL — the new routes 404 (old `/r-group-decomposition` still mounted) / `StartDecompositionRunDep` import error.

- [ ] **Step 3: Rewrite the routes file**

Overwrite `src/cellar/interface/routes/sar_analysis.py`:

```python
"""SAR analysis HTTP routes — server-side R-group decomposition (async runs)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from cellar.application.sar_analysis.cancel_decomposition_run import (
    CancelDecompositionRunInput,
)
from cellar.application.sar_analysis.decomposition_rows import (
    DecompositionRow,
    DecompositionRowSort,
    FetchDecompositionRowsInput,
)
from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRunInput
from cellar.application.sar_analysis.start_decomposition_run import StartDecompositionRunInput
from cellar.application.shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from cellar.domain.sar_analysis.rgroup_decomposition_run import (
    RGroupDecompositionRun,
    RGroupDecompositionRunStatus,
)
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._sar_analysis import (
    CancelDecompositionRunDep,
    FetchDecompositionRowsDep,
    GetDecompositionRunDep,
    StartDecompositionRunDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/sar", tags=["sar-analysis"])


class StartDecompositionRequest(BaseModel):
    molecule_ids: list[UUID] | None = None
    collection_id: UUID | None = None
    core_smiles: str


class DecompositionRunResponse(BaseModel):
    run_id: UUID
    status: str
    rgroup_labels: list[str]
    matched_count: int
    unmatched_count: int
    total_count: int
    error_message: str | None = None


class RowSortSpec(BaseModel):
    col: str
    dir: Literal["asc", "desc"] = "asc"


class DecompositionRowsRequest(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    sort: list[RowSortSpec] | None = None
    # Accepted for forward-compat; the AG-Grid filterModel mapping lands in Unit B.
    filter: dict[str, Any] | None = None


class DecompositionRowView(BaseModel):
    molecule_id: UUID
    smiles: str | None
    registration_number: str
    name: str
    rgroups: dict[str, str]
    mw: float | None
    clogp: float | None
    tpsa: float | None


class DecompositionRowsResponse(BaseModel):
    rows: list[DecompositionRowView]
    total: int


def _run_view(run: RGroupDecompositionRun) -> DecompositionRunResponse:
    return DecompositionRunResponse(
        run_id=run.id,
        status=run.status.value,
        rgroup_labels=list(run.rgroup_labels),
        matched_count=run.matched_count,
        unmatched_count=run.unmatched_count,
        total_count=run.total_count,
        error_message=run.error_message,
    )


def _row_view(row: DecompositionRow) -> DecompositionRowView:
    return DecompositionRowView(
        molecule_id=row.molecule_id,
        smiles=row.smiles,
        registration_number=row.registration_number,
        name=row.name,
        rgroups=row.rgroups,
        mw=row.molecular_weight,
        clogp=row.logp,
        tpsa=row.tpsa,
    )


@router.post("/decomposition", status_code=status.HTTP_200_OK)
async def start_decomposition(
    payload: StartDecompositionRequest,
    response: Response,
    auth: AuthDep,
    uc: StartDecompositionRunDep,
) -> DecompositionRunResponse:
    if (payload.molecule_ids is None) == (payload.collection_id is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of molecule_ids or collection_id must be set",
        )
    if not payload.core_smiles.strip():
        raise HTTPException(status_code=400, detail="core_smiles must not be empty")

    run = await uc.execute(
        StartDecompositionRunInput(
            workspace_id=auth.workspace_id,
            requested_by=auth.user_id,
            collection_id=payload.collection_id,
            molecule_ids=payload.molecule_ids,
            core_smiles=payload.core_smiles,
            now=datetime.now(UTC),
        )
    )
    if run.status != RGroupDecompositionRunStatus.READY:
        response.status_code = status.HTTP_202_ACCEPTED
    return _run_view(run)


@router.get("/decomposition/jobs/{run_id}")
async def get_decomposition_run(
    run_id: UUID,
    auth: AuthDep,
    uc: GetDecompositionRunDep,
) -> DecompositionRunResponse:
    run = result_to_response(
        await uc.execute(GetDecompositionRunInput(run_id=run_id, workspace_id=auth.workspace_id))
    )
    return _run_view(run)


@router.post("/decomposition/jobs/{run_id}/cancel")
async def cancel_decomposition_run(
    run_id: UUID,
    auth: AuthDep,
    uc: CancelDecompositionRunDep,
) -> DecompositionRunResponse:
    run = result_to_response(
        await uc.execute(
            CancelDecompositionRunInput(
                run_id=run_id, workspace_id=auth.workspace_id, now=datetime.now(UTC)
            )
        )
    )
    return _run_view(run)


@router.post("/decomposition/{run_id}/rows")
async def decomposition_rows(
    run_id: UUID,
    payload: DecompositionRowsRequest,
    auth: AuthDep,
    uc: FetchDecompositionRowsDep,
) -> DecompositionRowsResponse:
    sort = [DecompositionRowSort(col=s.col, direction=s.dir) for s in (payload.sort or [])]
    out = result_to_response(
        await uc.execute(
            FetchDecompositionRowsInput(
                run_id=run_id,
                workspace_id=auth.workspace_id,
                offset=payload.offset,
                limit=payload.limit,
                sort=sort,
            )
        )
    )
    return DecompositionRowsResponse(rows=[_row_view(r) for r in out.rows], total=out.total)
```

- [ ] **Step 4: Run the API tests to confirm they pass**

Run: `cd backend && uv run pytest tests/api/test_sar_analysis_routes.py -v`
Expected: all PASS. (Requires Docker for the seeded happy-path tests.)

- [ ] **Step 5: Confirm the old endpoint is gone**

Run: `cd backend && grep -rn "r-group-decomposition" src/ ; echo "--- expect: no hits ---"`
Expected: no hits — the old path is fully replaced.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(sar): replace sync r-group endpoint with async decomposition routes + /rows" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/interface/routes/sar_analysis.py tests/api/test_sar_analysis_routes.py
```

---

## Final verification

- [ ] **Step 1: Run the whole decomposition test surface**

Run:
```bash
cd backend && uv run pytest \
  tests/unit/application/sar_analysis/test_hashing.py \
  tests/unit/application/sar_analysis/test_decomposition_members.py \
  tests/unit/application/sar_analysis/test_run_decomposition.py \
  tests/unit/application/sar_analysis/test_start_decomposition_run.py \
  tests/unit/application/sar_analysis/test_get_cancel_decomposition_run.py \
  tests/unit/infrastructure/rdkit/test_streaming_rgroup_decomposer.py \
  tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py \
  tests/unit/infrastructure/di/test_sar_analysis_wiring.py \
  tests/integration/persistence/chemical_registration/test_fetch_for_decomposition.py \
  tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py \
  tests/api/test_sar_analysis_routes.py -v
```
Expected: all PASS.

- [ ] **Step 2: Import-linter (Clean Architecture boundaries)**

Run: `cd backend && uv run lint-imports`
Expected: PASS — application ports import only domain; RDKit/SQLAlchemy/Temporal stay in infrastructure; the workflow's activity import is guarded by `workflow.unsafe.imports_passed_through()`.

- [ ] **Step 3: Full SAR + regression sweep**

Run: `cd backend && uv run pytest tests/unit/application/sar_analysis tests/unit/infrastructure tests/integration/persistence/sar_analysis tests/api -q`
Expected: all PASS — confirms nothing else (scaffold-tree, UMAP, the functional `rgroup_decomposer` oracle test) regressed when the sync path was removed.

- [ ] **Step 4: Lint/format gate (error-severity)**

Run: `cd backend && uv run ruff check src/cellar/application/sar_analysis src/cellar/infrastructure/temporal src/cellar/interface/routes/sar_analysis.py`
Expected: clean (no unused imports left from the removed sync path).

- [ ] **Step 5: Commit the plan itself (force-add — `docs/` is gitignored except force-added files)**

```bash
git add -f docs/superpowers/plans/2026-06-15-sar-decomposition-async-endpoints.md && git commit -m "docs(sar): Part 1b implementation plan — async job + endpoints" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- docs/superpowers/plans/2026-06-15-sar-decomposition-async-endpoints.md
```

---

## What this plan deliberately leaves for later

- **Part 2 — Activity projection** (`sar_activity_projection` + `sar_activity_value` tables; membership+channel keyed) + the **heatmap-aggregation endpoint** + the `activity` column / sort-by-activity on `/rows`.
- **Unit B — Frontend** swap to these endpoints (AG-Grid Infinite Row Model datasource that emits `getRows({startRow, endRow, sortModel, filterModel})`), the server-cell heatmap, deletion of `buildRGroupRows`/`buildHeatmapGrid`/`useSarActivity`. The `/rows` `filter` param's AG-Grid `filterModel`→param mapping (spec §8.3) is decided and built here.
- **Unit C** — server-side "save all matched → collection", `rgroups->>'Rn'` expression indexes + join indexes, the domain-model deviation note in `docs/domain-model/04-sar-analysis.md` (new aggregate `RGroupDecompositionRun`), and the honest-label copy pass.

---

## Self-Review

**Spec coverage (§4 decomposition half of Unit A):**
- Two job lifecycles copy scaffold-tree (start cache→inline≤N→202; run; get; cancel) — Tasks 5/6/7. ✓
- Job input carries `collection_id` (re-expanded at run time), ad-hoc sets carry the bounded id list — Tasks 4/6/9. ✓
- Stream members in batches; fold version-aware `membership_hash`; `core_hash` via RDKit canonicalization — Tasks 1/2/4/6. ✓
- Labeled-core stability — provided by the Part 1a streaming session (one shared RDKit object); Run/Start consume it unchanged. ✓
- `POST /sar/decomposition` (200/202), `GET …/jobs/{run_id}`, `POST …/jobs/{run_id}/cancel`, `POST …/{run_id}/rows` — Task 12. ✓
- `/rows` = pure SQL `assignment ⋈ molecules`, server sort/page, `total` — Task 8. Activity column explicitly deferred to Part 2. ✓
- Old sync endpoint replaced, no shim — Tasks 10/12. ✓
- Temporal workflow/activity + Null fallback + DI; generous baked timeout — Tasks 9/10/11. ✓

**Locked-decision coverage:** inline threshold 200 (Task 6 default + test) ✓ · sibling fetcher (Task 3) ✓ · sort-all-cols/filter-deferred (Tasks 8/12) ✓ · NULL-smiles surfaced + merged excluded (Tasks 3/5/8 tests) ✓ · Start returns header, route maps status (Tasks 6/12) ✓.

**Placeholder scan:** none. The only soft references are "open the sibling file and copy the exact construction/fixture name" notes in Task 10 Step 5 (wiring-test helper) and Task 12 Step 1 (`workspace_id` fixture name) and worker/app anchors in Task 11 — each names the exact file + the exact lines to copy, because those host files' full bodies weren't quoted verbatim during recon. No `TODO`/`TBD`/"add error handling"/"write tests for the above".

**Type/name consistency:** `RGroupDecompositionRun` header is the Start return type and the `_run_view` input ✓. `ready_counts` defined in `run_decomposition.py`, imported by `start_decomposition_run.py` ✓. `DecompositionRowSort(col, direction)` consistent between the port (Task 8), the reader (`spec.direction`), and the route mapping (`direction=s.dir`) ✓. `RGroupDecompositionOrchestrator.schedule(run_id, workspace_id, core_smiles, collection_id?, molecule_ids?)` identical across the Protocol (Task 6), both orchestrators (Task 9), DI/lifespan (Tasks 10/11), and the cancel use case's `cancel(run_id=...)` (Task 7) ✓. `fetch_for_decomposition(*, molecule_ids, workspace_id) -> (id, smiles, version)` identical between the repo (Task 3), the stream Protocol (Task 4), and its fakes ✓. Repo methods (`save`, `find_by_id`, `find_cached`, `write_assignments`) match the Part 1a Protocol used here.

