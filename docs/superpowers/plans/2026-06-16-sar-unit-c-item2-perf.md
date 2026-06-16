# SAR Unit C · Item 2 — Perf (evidence-first) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the `MoleculeResolver` UUID N+1 (one bulk fetch instead of one query per ref) so SAR save-all scales to the full collection, and produce EXPLAIN evidence that the `/rows` hot path already rides its composite PKs (so no new index is added speculatively).

**Architecture:** Part A reworks `MoleculeResolver.resolve` to batch all UUID refs into a single `find_by_ids`, preserving order + every reason code, leaving the non-UUID per-ref path untouched. Part B adds a committed EXPLAIN probe (with `enable_seqscan=off`, which forces index use if an index is *usable* — so a tiny seed suffices) that asserts the joins ride the PKs, captured as durable evidence; a migration is added only if the probe shows a real gap.

**Tech Stack:** Python 3.13 / SQLAlchemy 2.0 async / dry-python returns / pytest. Spec: `docs/superpowers/specs/2026-06-16-sar-unit-c-item2-perf-design.md`. Backlog: `docs/backlog/molecule-resolver-uuid-batch.md`.

**Conventions (every task):**
- Commit with explicit pathspec: `git commit -m "…" -- <paths>`; trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- BE gate (scope ruff to `src/` files only — `tests/` is not ruff-gated and carries pre-existing debt): `cd backend && uv run pytest <paths> -q && uv run lint-imports && uv run ruff check <src paths> && uv run ruff format --check <src paths>`.

---

## Task 1: `MoleculeResolver` UUID batch resolution

**Files:**
- Modify: `backend/src/cellar/application/shared/molecule_resolver.py`
- Test: `backend/tests/unit/application/shared/test_molecule_resolver.py` (new; create `tests/unit/application/shared/` + an empty `__init__.py` if the dir is absent — match sibling dirs which use `__init__.py`)

Reference — current shapes (do not change): `RefType` (StrEnum incl. `UUID="uuid"`, `REGISTRATION_NUMBER="registration_number"`), `MoleculeReference(value, ref_type)`, `ResolvedMolecule(ref, molecule_id)`, `UnresolvedMolecule(ref, reason)`. The success branch of the (current) `_resolve_uuid` is `ResolvedMolecule(ref=ref, molecule_id=mol.id)`; reasons used are `"invalid"` (bad uuid string), `"not_found"`, `"tombstone"` (`mol.is_tombstone`). `find_by_ids(workspace_id, ids) -> list[Molecule]` is workspace-scoped and **returns tombstoned rows** (does not filter `merged_into_id`).

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import uuid

import pytest

from cellar.application.shared.molecule_resolver import (
    MoleculeReference,
    MoleculeResolver,
    RefType,
    ResolvedMolecule,
    UnresolvedMolecule,
)


class _Mol:
    def __init__(self, mid, *, tombstone=False):
        self.id = mid
        self.is_tombstone = tombstone


class _FakeRepo:
    """Counts calls so the test can prove batching (one find_by_ids, zero per-id)."""

    def __init__(self, mols, *, by_reg=None):
        self._by_id = {m.id: m for m in mols}
        self._by_reg = by_reg or {}
        self.find_by_ids_calls = 0
        self.find_by_id_calls = 0

    async def find_by_ids(self, workspace_id, ids):
        self.find_by_ids_calls += 1
        return [self._by_id[i] for i in ids if i in self._by_id]

    async def find_by_id_in_workspace(self, workspace_id, mid):
        self.find_by_id_calls += 1
        return self._by_id.get(mid)

    async def find_by_registration_number(self, workspace_id, value):
        return self._by_reg.get(value)


class _StubProcessor:
    def process(self, value):  # only used by SMILES refs, not exercised here
        raise AssertionError("structure processor should not be called")


def _resolver(repo):
    return MoleculeResolver(molecule_repo=repo, structure_processor=_StubProcessor())


def _uuid_ref(mid):
    return MoleculeReference(value=str(mid), ref_type=RefType.UUID)


@pytest.mark.asyncio
async def test_uuid_refs_resolve_in_a_single_batch_query_preserving_order():
    a, b, missing = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    repo = _FakeRepo([_Mol(a), _Mol(b)])
    refs = [_uuid_ref(a), _uuid_ref(missing), _uuid_ref(b)]
    resolved, unresolved = await _resolver(repo).resolve(uuid.uuid4(), refs)
    assert repo.find_by_ids_calls == 1           # batched
    assert repo.find_by_id_calls == 0            # never per-id
    assert [r.molecule_id for r in resolved] == [a, b]   # order preserved
    assert [u.ref.value for u in unresolved] == [str(missing)]
    assert unresolved[0].reason == "not_found"


@pytest.mark.asyncio
async def test_tombstone_and_invalid_uuid_reasons_preserved():
    live, dead = uuid.uuid4(), uuid.uuid4()
    repo = _FakeRepo([_Mol(live), _Mol(dead, tombstone=True)])
    refs = [
        _uuid_ref(live),
        _uuid_ref(dead),
        MoleculeReference(value="not-a-uuid", ref_type=RefType.UUID),
    ]
    resolved, unresolved = await _resolver(repo).resolve(uuid.uuid4(), refs)
    assert repo.find_by_ids_calls == 1
    assert [r.molecule_id for r in resolved] == [live]
    reasons = {u.ref.value: u.reason for u in unresolved}
    assert reasons[str(dead)] == "tombstone"
    assert reasons["not-a-uuid"] == "invalid"


@pytest.mark.asyncio
async def test_mixed_uuid_and_registration_number():
    a = uuid.uuid4()
    reg_mol = _Mol(uuid.uuid4())
    repo = _FakeRepo([_Mol(a), reg_mol], by_reg={"CV-9": reg_mol})
    refs = [_uuid_ref(a), MoleculeReference(value="CV-9", ref_type=RefType.REGISTRATION_NUMBER)]
    resolved, unresolved = await _resolver(repo).resolve(uuid.uuid4(), refs)
    assert unresolved == []
    assert [r.molecule_id for r in resolved] == [a, reg_mol.id]   # order preserved across kinds
    assert repo.find_by_ids_calls == 1


@pytest.mark.asyncio
async def test_duplicate_uuid_yields_two_resolved_outputs():
    a = uuid.uuid4()
    repo = _FakeRepo([_Mol(a)])
    resolved, unresolved = await _resolver(repo).resolve(uuid.uuid4(), [_uuid_ref(a), _uuid_ref(a)])
    assert [r.molecule_id for r in resolved] == [a, a]   # no dedup, as before
    assert repo.find_by_ids_calls == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/sidx/workspace/chem-vault2/backend && uv run pytest tests/unit/application/shared/test_molecule_resolver.py -q`
Expected: FAIL — the current `resolve` calls `find_by_id_in_workspace` per ref (so `find_by_ids_calls == 0`, `find_by_id_calls == 3`), failing the batching assertions.

- [ ] **Step 3: Confirm `_resolve_uuid` / `_resolve_one`'s UUID branch have no other callers**

Run: `cd /Users/sidx/workspace/chem-vault2/backend && grep -rn "_resolve_uuid\|_resolve_one" src/cellar/`
Expected: both are referenced only inside `molecule_resolver.py` (private). This confirms removing the UUID dispatch branch + `_resolve_uuid` is safe.

- [ ] **Step 4: Rework `resolve` + drop the now-dead UUID per-ref path**

In `molecule_resolver.py`, replace the body of `resolve` with the batched version:

```python
    async def resolve(
        self,
        workspace_id: uuid.UUID,
        refs: list[MoleculeReference],
    ) -> tuple[list[ResolvedMolecule], list[UnresolvedMolecule]]:
        """Resolve each reference and return (resolved, unresolved) lists.

        UUID refs are resolved in a single bulk ``find_by_ids`` (avoids an N+1 of
        per-ref ``find_by_id_in_workspace`` aggregate loads); non-UUID refs keep the
        per-ref path. Output order matches input ``refs``; duplicates are preserved.
        """
        resolved: list[ResolvedMolecule] = []
        unresolved: list[UnresolvedMolecule] = []

        # Pass 1: parse UUID-type refs; collect valid ids for one bulk fetch.
        # parsed_ids[i] is the parsed UUID, or None if ref i is an unparseable
        # UUID string (recorded as "invalid" in pass 2 without a DB hit).
        parsed_ids: dict[int, uuid.UUID | None] = {}
        valid_ids: list[uuid.UUID] = []
        for i, ref in enumerate(refs):
            if ref.ref_type == RefType.UUID:
                try:
                    pid = uuid.UUID(ref.value)
                except ValueError:
                    parsed_ids[i] = None
                else:
                    parsed_ids[i] = pid
                    valid_ids.append(pid)

        by_id: dict[uuid.UUID, object] = {}
        if valid_ids:
            mols = await self._molecule_repo.find_by_ids(workspace_id, valid_ids)
            by_id = {m.id: m for m in mols}

        # Pass 2: emit outcomes in input order.
        for i, ref in enumerate(refs):
            if ref.ref_type == RefType.UUID:
                pid = parsed_ids[i]
                if pid is None:
                    unresolved.append(UnresolvedMolecule(ref=ref, reason="invalid"))
                    continue
                mol = by_id.get(pid)
                if mol is None:
                    unresolved.append(UnresolvedMolecule(ref=ref, reason="not_found"))
                elif mol.is_tombstone:
                    unresolved.append(UnresolvedMolecule(ref=ref, reason="tombstone"))
                else:
                    resolved.append(ResolvedMolecule(ref=ref, molecule_id=mol.id))
            else:
                result = await self._resolve_one(workspace_id, ref)
                if isinstance(result, ResolvedMolecule):
                    resolved.append(result)
                else:
                    unresolved.append(result)

        return resolved, unresolved
```

Then delete the now-dead `_resolve_uuid` method entirely, and remove its dispatch branch from `_resolve_one` so the first branch is `REGISTRATION_NUMBER`:

```python
    async def _resolve_one(
        self, workspace_id: uuid.UUID, ref: MoleculeReference
    ) -> ResolvedMolecule | UnresolvedMolecule:
        """Dispatch to the appropriate resolver based on ref_type (non-UUID only;
        UUID refs are batched in ``resolve``)."""
        if ref.ref_type == RefType.REGISTRATION_NUMBER:
            return await self._resolve_registration_number(workspace_id, ref)
        elif ref.ref_type == RefType.EXTERNAL_ID:
            return await self._resolve_external_id(workspace_id, ref)
        elif ref.ref_type == RefType.SMILES:
            return await self._resolve_smiles(workspace_id, ref)
        elif ref.ref_type == RefType.INCHI_KEY:
            return await self._resolve_inchi_key(workspace_id, ref)
        elif ref.ref_type == RefType.NAME:
            return await self._resolve_name(workspace_id, ref)
        else:
            return UnresolvedMolecule(ref=ref, reason="invalid")
```

- [ ] **Step 5: Run to verify pass**

Run: `cd /Users/sidx/workspace/chem-vault2/backend && uv run pytest tests/unit/application/shared/test_molecule_resolver.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Regression — run every resolver-caller suite**

Run:
```bash
cd /Users/sidx/workspace/chem-vault2/backend && uv run pytest \
  tests/unit/application/research_organization/test_bulk_add_to_collection.py \
  tests/api/test_sar_analysis_routes.py \
  -q
```
Also sweep any other collection-membership / resolver tests:
```bash
cd /Users/sidx/workspace/chem-vault2/backend && uv run pytest "$(grep -rln 'AddMoleculesToCollection\|BulkAddToCollection\|MoleculeResolver' tests/ | tr '\n' ' ')" -q
```
Expected: all PASS (the uuid-ref path through `AddMoleculesToCollection` is exercised end-to-end by the SAR save-collection API tests; behavior is unchanged).

- [ ] **Step 7: Gate + commit**

```bash
cd /Users/sidx/workspace/chem-vault2/backend && uv run pytest tests/unit/application/shared/test_molecule_resolver.py tests/unit/application/research_organization/test_bulk_add_to_collection.py tests/api/test_sar_analysis_routes.py -q \
 && uv run lint-imports \
 && uv run ruff check src/cellar/application/shared/molecule_resolver.py \
 && uv run ruff format --check src/cellar/application/shared/molecule_resolver.py
git commit -m "perf(resolver): batch UUID refs in MoleculeResolver.resolve (one find_by_ids, not N)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- src/cellar/application/shared/molecule_resolver.py tests/unit/application/shared/test_molecule_resolver.py
```
(If the new test dir needed an `__init__.py`, include it in the pathspec.)

---

## Task 2: EXPLAIN evidence for the `/rows` hot path

**Files:**
- Test: `backend/tests/integration/persistence/sar_analysis/test_decomposition_rows_explain.py` (new)
- Create: `docs/backlog/sar-rows-explain-evidence.md` (captured plan + conclusion)
- Conditional: `backend/alembic/versions/059_*.py` + `_apply_filter` rewrite — only if the probe shows a real gap (expected: not needed)

The probe seeds a minimal run + assignments + projection + activity (reusing the seed helpers already in `test_decomposition_row_reader.py` — copy the small ones you need: `_seed_org`, `_seed_molecule`, `_seed_ready_run`, the projection/activity seed). With `SET LOCAL enable_seqscan = off`, Postgres uses any *usable* index regardless of table size, so a tiny seed proves the composite PKs cover the joins. The SQL mirrors `SQLAlchemyDecompositionRowReader.fetch_rows` (kept in sync by the cross-reference comment).

- [ ] **Step 1: Write the probe test**

```python
"""EXPLAIN evidence: the /rows query rides the composite PKs (no new index needed).

With enable_seqscan disabled, Postgres falls back to an index scan iff one is
*usable* for the query shape — so this proves index usability on a tiny seed. The
SQL mirrors SQLAlchemyDecompositionRowReader.fetch_rows; keep them in sync.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)

_NOW = datetime(2026, 6, 16, tzinfo=UTC)

_ROWS_SQL = """
SELECT rga.molecule_id, m.smiles, m.registration_number, m.name, rga.rgroups,
       m.molecular_weight, m.logp, m.tpsa,
       sav.scalar AS activity, sav.snapshot AS activity_snapshot
FROM rgroup_assignments rga
JOIN rgroup_decomposition_runs r ON r.id = rga.run_id
JOIN molecules m ON m.id = rga.molecule_id
LEFT JOIN sar_activity_values sav
       ON sav.projection_id = :pid AND sav.molecule_id = rga.molecule_id
WHERE rga.run_id = :rid AND r.workspace_id = :ws AND m.workspace_id = :ws
      AND m.merged_into_id IS NULL AND m.molecular_weight > :mw
ORDER BY m.registration_number ASC NULLS LAST, rga.molecule_id
LIMIT 100
"""


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


async def _seed_molecule(uow, ws, org, *, reg, smiles, mw):
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, molecular_weight, version, originating_org_id) "
            "VALUES (:id, :ws, :r, :r, 'small_molecule', :smi, :mw, 1, :org)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "smi": smiles, "mw": mw, "org": org},
    )
    return mol_id


@pytest.mark.asyncio
async def test_rows_query_uses_pk_indexes(uow, capsys):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        a = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1", mw=120.0)
        b = await _seed_molecule(uow, ws, org, reg="CV-B", smiles="Clc1ccccc1", mw=130.0)
        run = (
            RGroupDecompositionRun.create(
                workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
                core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
            )
            .mark_running(_NOW)
            .mark_ready(rgroup_labels=["R1"], matched_count=2, unmatched_count=0, total_count=2, now=_NOW)
        )
        repo = SQLAlchemyRGroupDecompositionRunRepository(uow)
        await repo.save(run)
        await repo.write_assignments(run.id, [
            RGroupAssignment(molecule_id=a, rgroups={"R1": "F"}),
            RGroupAssignment(molecule_id=b, rgroups={"R1": "Cl"}),
        ])
        # A projection row so the activity LEFT JOIN is exercised.
        pid = uuid.uuid4()
        await uow.session.execute(
            text(
                "INSERT INTO sar_activity_projections (id, workspace_id, requested_by, status, "
                "membership_hash, channel_hash, channel_spec, value_count, version, created_at) "
                "VALUES (:id, :ws, :rb, 'ready', 'm', 'ch', '{}', 1, 1, :now)"
            ),
            {"id": pid, "ws": ws, "rb": uuid.uuid4(), "now": _NOW},
        )
        await uow.session.execute(
            text(
                "INSERT INTO sar_activity_values (projection_id, molecule_id, scalar, unit, "
                "qualifier, source, snapshot) VALUES (:p, :m, 0.5, 'uM', NULL, 'dose_response', '{}')"
            ),
            {"p": pid, "m": a},
        )

        await uow.session.execute(text("SET LOCAL enable_seqscan = off"))
        plan_rows = (
            await uow.session.execute(
                text("EXPLAIN (FORMAT TEXT) " + _ROWS_SQL),
                {"pid": pid, "rid": run.id, "ws": ws, "mw": 0.0},
            )
        ).scalars().all()
    plan = "\n".join(plan_rows)
    print("\n=== EXPLAIN /rows (enable_seqscan=off) ===\n" + plan)  # captured with -s

    # With seqscan disabled, the joins must ride their PK indexes — no seq scan on
    # the two big SAR tables, and at least one index scan present.
    assert "Seq Scan on rgroup_assignments" not in plan
    assert "Seq Scan on sar_activity_values" not in plan
    assert "Index" in plan
```

> If a column/constraint name differs (e.g. `sar_activity_projections` requires a column the insert omits), fix the INSERT to satisfy the schema — confirm columns with `\d sar_activity_projections` / by reading `sar_activity_projection_models.py`. The probe's value is the EXPLAIN, not the seed shape.

- [ ] **Step 2: Run the probe (capture the plan)**

Run: `cd /Users/sidx/workspace/chem-vault2/backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_rows_explain.py -q -s`
Expected: PASS, and the printed `EXPLAIN` shows Index Scans on `rgroup_assignments_pkey` / `sar_activity_values_pkey` / `molecules_pkey` (exact names may vary) and no Seq Scan on the two SAR tables. **Copy the printed plan.**

- [ ] **Step 3: Record the evidence + decision**

Create `docs/backlog/sar-rows-explain-evidence.md`:

```markdown
# SAR /rows EXPLAIN evidence (Unit C item 2)

**Date:** 2026-06-16 · **Probe:** `tests/integration/persistence/sar_analysis/test_decomposition_rows_explain.py`

## Finding
The `/rows` query's three joins ride composite PKs — `rgroup_assignments (run_id,
molecule_id)`, `sar_activity_values (projection_id, molecule_id)`, `molecules (id)`.
With `enable_seqscan=off`, the planner uses index scans on all three (no seq scan on
the SAR tables), confirming the indexes are usable for the join/filter/sort shape.

## Decision
**No new index added.** The handoff's proposed scoped-join / activity-join indexes are
already the composite PKs. The run-scoped `rgroups` filter operates on one run's rows
(PK-prefixed), so a speculative GIN on `rgroups` is not justified by evidence; revisit
only if a real workload shows the in-run jsonb filter dominating.

## Captured plan (enable_seqscan=off)
```
<paste the printed EXPLAIN output here>
```
```

Fill the fenced block with the actual captured plan.

- [ ] **Step 4: Migration decision gate**

If Step 2 showed **no** Seq Scan on the SAR tables (expected): **no migration** — skip to Step 5.

If the probe instead showed a Seq Scan that an index would fix (a usable index was genuinely absent), STOP and report DONE_WITH_CONCERNS describing the exact plan node, so the controller can scope a focused `059` index migration (GIN on `rgroups` + rewrite `_apply_filter`'s `RGroupAssignmentModel.rgroups[col].as_string() == v` to a `rgroups @> {…}` containment clause) as a follow-up. Do NOT add a speculative index.

- [ ] **Step 5: Gate + commit**

```bash
cd /Users/sidx/workspace/chem-vault2/backend && uv run pytest tests/integration/persistence/sar_analysis/test_decomposition_rows_explain.py -q
```
Then (from repo root) commit the probe + evidence (evidence doc is under gitignored `docs/`, force-add):
```bash
cd /Users/sidx/workspace/chem-vault2
git add -f docs/backlog/sar-rows-explain-evidence.md
git commit -m "test(sar): EXPLAIN probe + evidence — /rows rides composite PKs (no new index)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" -- backend/tests/integration/persistence/sar_analysis/test_decomposition_rows_explain.py docs/backlog/sar-rows-explain-evidence.md
```

---

## Self-review (coverage)
- **Spec → tasks:** Part A (resolver UUID batch) → Task 1 (rework + dead-path removal + unit test + regression sweep). Part B (EXPLAIN verification → likely no migration) → Task 2 (probe test + evidence doc + conditional-migration gate). Conditional migration explicitly gated on evidence (Task 2 Step 4), not added speculatively.
- **Invariants:** order preservation, duplicate handling, and the `invalid`/`not_found`/`tombstone` reason codes are each asserted by a Task 1 test; regression sweep covers the real resolver callers.
- **No placeholders:** all code is concrete; the only intentional fill-in is pasting the captured EXPLAIN plan into the evidence doc (Task 2 Step 3), which is the deliverable.
- **Type consistency:** `resolve` return shape `(list[ResolvedMolecule], list[UnresolvedMolecule])` unchanged; `_resolve_one` keeps its signature, only loses the UUID branch; `find_by_ids(workspace_id, ids)` matches the repo.
