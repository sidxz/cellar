from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.collection_membership import MembershipResult
from cellar.application.sar_analysis.save_decomposition_collection import (
    SaveDecompositionCollection,
    SaveDecompositionCollectionInput,
)
from cellar.application.shared.molecule_resolver import RefType
from cellar.domain.shared.errors import NotFoundError, ValidationError


class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRunRepo:
    def __init__(self, exists=True):
        self._exists = exists

    async def find_by_id_in_workspace(self, workspace_id, run_id):
        return object() if self._exists else None


class FakeProjRepo:
    def __init__(self, exists=True):
        self._exists = exists

    async def find_by_id(self, projection_id, *, workspace_id):
        return object() if self._exists else None


class FakeReader:
    def __init__(self, ids):
        self.ids = ids
        self.calls = []

    async def fetch_matched_ids(self, run_id, *, workspace_id, projection_id=None, filter=None):
        self.calls.append((run_id, workspace_id, projection_id, filter))
        return self.ids


class FakeCreate:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def __call__(self, cmd, auth=None):
        self.calls.append(cmd)
        return self.result


class FakeCollection:
    def __init__(self, cid):
        self.id = cid


class FakeAdd:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def __call__(self, cmd, auth=None):
        self.calls.append(cmd)
        return self.result


def _input(**over):
    base = dict(
        run_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        name="Series A",
        project_id=None,
        filter=None,
        projection_id=None,
    )
    base.update(over)
    return SaveDecompositionCollectionInput(**base)


def _uc(*, ids, run=True, proj=True, create=None, add=None):
    cid = uuid.uuid4()
    create = create if create is not None else Success(FakeCollection(cid))
    add = add if add is not None else Success(MembershipResult(added=list(ids), already_present=0, unresolved=[]))
    fc, fa = FakeCreate(create), FakeAdd(add)
    uc = SaveDecompositionCollection(
        run_repository=FakeRunRepo(run),
        projection_repository=FakeProjRepo(proj),
        reader=FakeReader(ids),
        create_collection=fc,
        add_molecules=fa,
        uow=FakeUoW(),
    )
    return uc, fc, fa, cid


@pytest.mark.asyncio
async def test_creates_collection_and_adds_matched_ids_as_uuid_refs():
    a, b = uuid.uuid4(), uuid.uuid4()
    uc, fc, fa, cid = _uc(ids=[a, b])
    out = await uc.execute(_input(), auth=None)
    assert isinstance(out, Success)
    assert out.unwrap() == cid
    assert len(fc.calls) == 1
    assert {r.ref_type for r in fa.calls[0].refs} == {RefType.UUID}
    assert {r.value for r in fa.calls[0].refs} == {str(a), str(b)}


@pytest.mark.asyncio
async def test_passes_filter_and_projection_to_reader():
    uc, fc, fa, cid = _uc(ids=[uuid.uuid4()])
    pid = uuid.uuid4()
    flt = {"R1": {"kind": "text", "op": "eq", "value": "Cl"}}
    await uc.execute(_input(filter=flt, projection_id=pid), auth=None)
    assert uc._reader.calls[0][2] == pid   # projection_id forwarded
    assert uc._reader.calls[0][3] == flt   # filter forwarded


@pytest.mark.asyncio
async def test_unknown_run_returns_not_found():
    uc, *_ = _uc(ids=[], run=False)
    out = await uc.execute(_input(), auth=None)
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_unknown_projection_returns_not_found():
    uc, *_ = _uc(ids=[], proj=False)
    out = await uc.execute(_input(projection_id=uuid.uuid4()), auth=None)
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_empty_match_set_creates_collection_skips_add():
    uc, fc, fa, cid = _uc(ids=[])
    out = await uc.execute(_input(), auth=None)
    assert isinstance(out, Success)
    assert out.unwrap() == cid
    assert fa.calls == []   # no add call when nothing matched


@pytest.mark.asyncio
async def test_propagates_create_failure():
    uc, fc, fa, _ = _uc(ids=[uuid.uuid4()], create=Failure(ValidationError("bad name")))
    out = await uc.execute(_input(), auth=None)
    assert isinstance(out, Failure)
    assert fa.calls == []
