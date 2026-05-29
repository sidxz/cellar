"""Tests for BulkAddToCollection use case — find-and-add CSV row pipeline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from cellar.application.research_organization.bulk_add_to_collection import (
    BulkAddToCollection,
    BulkAddToCollectionCommand,
    StashedUnregisteredRows,
)
from cellar.application.shared.molecule_resolver import (
    ResolvedMolecule,
    UnresolvedMolecule,
)
from cellar.domain.research_organization.bulk_add_types import (
    BulkAddRow,
    RowStatus,
)


@dataclass
class FakeResolver:
    """Stub: returns canned (resolved, unresolved) by reference value."""

    resolved_map: dict[str, uuid.UUID]
    ambiguous_values: set[str]

    async def resolve(self, workspace_id, refs):
        resolved, unresolved = [], []
        for r in refs:
            if r.value in self.resolved_map:
                resolved.append(
                    ResolvedMolecule(ref=r, molecule_id=self.resolved_map[r.value])
                )
            elif r.value in self.ambiguous_values:
                unresolved.append(UnresolvedMolecule(ref=r, reason="ambiguous"))
            else:
                unresolved.append(UnresolvedMolecule(ref=r, reason="not_found"))
        return resolved, unresolved


@dataclass
class FakeCollectionRepo:
    members: set[uuid.UUID]
    collection_exists: bool = True

    async def find_by_id_in_workspace(self, ws, cid):
        return object() if self.collection_exists else None

    async def add_molecules(self, ws, cid, ids):
        new = [i for i in ids if i not in self.members]
        self.members.update(new)
        return len(new)

    async def get_molecule_ids(self, ws, cid, *, offset=0, limit=100):
        return list(self.members)[offset : offset + limit]


@dataclass
class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def commit(self):
        return []


@pytest.mark.asyncio
async def test_dry_run_classifies_all_five_statuses():
    existing = uuid.uuid4()
    already = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-000001": existing, "CC-000002": already},
        ambiguous_values={"aspirin"},
    )
    repo = FakeCollectionRepo(members={already})
    use_case = BulkAddToCollection(uow=FakeUoW(), resolver=resolver, repo=repo)

    rows = [
        BulkAddRow(row_index=0, registration_number="CC-000001"),
        BulkAddRow(row_index=1, registration_number="CC-000002"),
        BulkAddRow(row_index=2, smiles="c1ccccc1O"),
        BulkAddRow(row_index=3, name="aspirin"),
        BulkAddRow(row_index=4, notes="just a note"),
    ]
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=rows,
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    statuses = {o.row_index: o.status for o in result.outcomes}
    assert statuses == {
        0: RowStatus.RESOLVED,
        1: RowStatus.ALREADY_PRESENT,
        2: RowStatus.UNREGISTERED,
        3: RowStatus.AMBIGUOUS,
        4: RowStatus.ERROR,
    }
    assert result.preview_id is not None


@pytest.mark.asyncio
async def test_commit_adds_only_resolved_rows():
    resolver = FakeResolver(
        resolved_map={"CC-1": uuid.uuid4(), "CC-2": uuid.uuid4()},
        ambiguous_values=set(),
    )
    repo = FakeCollectionRepo(members=set())
    use_case = BulkAddToCollection(uow=FakeUoW(), resolver=resolver, repo=repo)

    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[
            BulkAddRow(row_index=0, registration_number="CC-1"),
            BulkAddRow(row_index=1, registration_number="CC-2"),
            BulkAddRow(row_index=2, smiles="c1ccccc1O"),
        ],
        dry_run=False,
    )
    result = (await use_case(cmd)).unwrap()
    assert result.resolved_count == 2
    assert result.unregistered_count == 1
    assert len(repo.members) == 2


@pytest.mark.asyncio
async def test_stash_persists_unregistered_rows_for_handoff():
    resolver = FakeResolver(resolved_map={}, ambiguous_values=set())
    repo = FakeCollectionRepo(members=set())
    use_case = BulkAddToCollection(uow=FakeUoW(), resolver=resolver, repo=repo)
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, smiles="c1ccccc1O", name="phenol")],
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    stashed = use_case.fetch_stash(result.preview_id)
    assert isinstance(stashed, StashedUnregisteredRows)
    assert stashed.rows[0].smiles == "c1ccccc1O"
    assert stashed.rows[0].name == "phenol"


@pytest.mark.asyncio
async def test_collection_not_found_returns_failure():
    resolver = FakeResolver(resolved_map={}, ambiguous_values=set())
    repo = FakeCollectionRepo(members=set(), collection_exists=False)
    use_case = BulkAddToCollection(uow=FakeUoW(), resolver=resolver, repo=repo)
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=True,
    )
    result = await use_case(cmd)
    assert result.failure() is not None  # NotFoundError


@pytest.mark.asyncio
async def test_fetch_stash_returns_none_after_ttl_expiry():
    resolver = FakeResolver(resolved_map={}, ambiguous_values=set())
    repo = FakeCollectionRepo(members=set())
    use_case = BulkAddToCollection(uow=FakeUoW(), resolver=resolver, repo=repo)
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, smiles="c1ccccc1O")],
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    preview_id = result.preview_id
    assert use_case.fetch_stash(preview_id) is not None

    # Manually expire the stash entry by overwriting its expires_at to the past.
    use_case._stash[preview_id] = type(use_case._stash[preview_id])(
        workspace_id=use_case._stash[preview_id].workspace_id,
        collection_id=use_case._stash[preview_id].collection_id,
        rows=use_case._stash[preview_id].rows,
        expires_at=0.0,
    )
    assert use_case.fetch_stash(preview_id) is None
