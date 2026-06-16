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
