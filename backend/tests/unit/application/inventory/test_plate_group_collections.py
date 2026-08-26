"""Unit tests for the PlateGroup → Collection link (S16 §5).

Covers: write validation on create/update, collection-name enrichment on the
tree/detail reads (one ``find_by_ids`` per response), and the reverse read
``ListPlateGroupsForCollection``.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from returns.result import Failure, Success

from cellar.application.inventory.collection_plate_groups import (
    CollectionPlateGroupRow,
    ListPlateGroupsForCollection,
    ListPlateGroupsForCollectionQuery,
)
from cellar.application.inventory.plate_groups import (
    CreatePlateGroup,
    CreatePlateGroupCommand,
    GetGroupTree,
    GetGroupTreeQuery,
    GetPlateGroup,
    GetPlateGroupQuery,
    UpdatePlateGroup,
    UpdatePlateGroupCommand,
)
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.research_organization.collection import Collection
from cellar.domain.shared.errors import NotFoundError
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()
ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
USER = uuid.uuid4()


class _FakeUow:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return []


class _FakeDispatcher:
    async def dispatch_all(self, events):
        return None


class _FakeOrgDirectory:
    def __init__(self, *org_ids: uuid.UUID) -> None:
        self._orgs = [SimpleNamespace(id=i) for i in org_ids]

    async def list_orgs(self):
        return self._orgs


class _FakeGroupRepo:
    def __init__(self, groups: list[PlateGroup] | None = None) -> None:
        self.groups: dict[uuid.UUID, PlateGroup] = {g.id: g for g in groups or []}

    async def find_by_id_in_workspace(self, workspace_id, id):
        g = self.groups.get(id)
        return g if g is not None and g.workspace_id == workspace_id else None

    async def find_by_name(self, workspace_id, owner_org_id, parent_group_id, name):
        return None

    async def save(self, group):
        self.groups[group.id] = group

    async def find_by_workspace(self, workspace_id, *, owner_org_id=None):
        return [
            g
            for g in self.groups.values()
            if g.workspace_id == workspace_id
            and (owner_org_id is None or g.owner_org_id == owner_org_id)
        ]

    async def find_children(self, workspace_id, parent_group_id):
        return [g for g in self.groups.values() if g.parent_group_id == parent_group_id]

    async def count_plates_by_group(self, workspace_id, owner_org_id=None):
        return {}

    async def plate_formats_by_group(self, workspace_id, owner_org_id=None):
        return {}


class _FakeCollectionRepo:
    def __init__(self, *collections: Collection) -> None:
        self._by_id = {c.id: c for c in collections}
        self.find_by_ids_calls: list[list[uuid.UUID]] = []

    async def find_by_id_in_workspace(self, workspace_id, id):
        c = self._by_id.get(id)
        return c if c is not None and c.workspace_id == workspace_id else None

    async def find_by_ids(self, workspace_id, ids):
        self.find_by_ids_calls.append(list(ids))
        return [c for cid in ids if (c := self._by_id.get(cid)) and c.workspace_id == workspace_id]


class _StubReader:
    def __init__(self, rows: list[CollectionPlateGroupRow]) -> None:
        self.rows = rows
        self.calls: list[uuid.UUID] = []

    async def groups_for_collection(self, workspace_id, collection_id):
        self.calls.append(collection_id)
        return self.rows


def _collection(name: str = "SACCZ", workspace_id: uuid.UUID = WS) -> Collection:
    return Collection.create(workspace_id=workspace_id, name=name, created_by=USER)


def _group(
    name: str,
    *,
    owner_org_id: uuid.UUID = ORG_A,
    parent_group_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
) -> PlateGroup:
    return PlateGroup.create(
        workspace_id=WS,
        owner_org_id=owner_org_id,
        name=name,
        created_by=USER,
        parent_group_id=parent_group_id,
        collection_id=collection_id,
    )


def _visibility() -> PlateVisibilityService:
    return PlateVisibilityService(_FakeOrgDirectory(ORG_A, ORG_B))


def _auth(role: str = "editor", *, workspace_id: uuid.UUID = WS, org_id=ORG_A) -> FakeAuth:
    return FakeAuth(role=role, workspace_id=workspace_id, org_id=org_id)


def _row(owner_org_id: uuid.UUID, name: str = "Lib") -> CollectionPlateGroupRow:
    return CollectionPlateGroupRow(
        group_id=uuid.uuid4(),
        name=name,
        group_type="library",
        owner_org_id=owner_org_id,
        path=name,
        plate_count=1,
        subtree_plate_count=2,
        on_loan_count=1,
        overdue_count=0,
    )


# ---------------------------------------------------------------------------
# Create / update
# ---------------------------------------------------------------------------


class TestCreateWithCollection:
    def _uc(self, groups: _FakeGroupRepo, collections: _FakeCollectionRepo) -> CreatePlateGroup:
        return CreatePlateGroup(
            _FakeUow(), groups, _FakeDispatcher(), _visibility(), object(), collections
        )

    async def test_known_collection_links_and_names(self) -> None:
        coll = _collection()
        groups = _FakeGroupRepo()

        result = await self._uc(groups, _FakeCollectionRepo(coll))(
            CreatePlateGroupCommand(
                workspace_id=WS, name="Lib", created_by=USER, collection_id=coll.id
            ),
            auth=_auth(),
        )

        assert isinstance(result, Success)
        saved = result.unwrap()
        assert saved.group.collection_id == coll.id
        assert saved.collection_name == "SACCZ"
        assert saved.group.id in groups.groups

    async def test_without_collection_has_no_name(self) -> None:
        result = await self._uc(_FakeGroupRepo(), _FakeCollectionRepo())(
            CreatePlateGroupCommand(workspace_id=WS, name="Lib", created_by=USER),
            auth=_auth(),
        )

        assert isinstance(result, Success)
        assert result.unwrap().group.collection_id is None
        assert result.unwrap().collection_name is None

    async def test_unknown_collection_is_not_found(self) -> None:
        groups = _FakeGroupRepo()

        result = await self._uc(groups, _FakeCollectionRepo())(
            CreatePlateGroupCommand(
                workspace_id=WS, name="Lib", created_by=USER, collection_id=uuid.uuid4()
            ),
            auth=_auth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert result.failure().entity_type == "Collection"
        assert groups.groups == {}

    async def test_cross_workspace_collection_is_not_found(self) -> None:
        foreign = _collection(workspace_id=uuid.uuid4())

        result = await self._uc(_FakeGroupRepo(), _FakeCollectionRepo(foreign))(
            CreatePlateGroupCommand(
                workspace_id=WS, name="Lib", created_by=USER, collection_id=foreign.id
            ),
            auth=_auth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


class TestUpdateWithCollection:
    def _uc(self, groups: _FakeGroupRepo, collections: _FakeCollectionRepo) -> UpdatePlateGroup:
        return UpdatePlateGroup(
            _FakeUow(), groups, _FakeDispatcher(), _visibility(), object(), collections
        )

    async def test_sets_link(self) -> None:
        coll = _collection()
        group = _group("Lib")

        result = await self._uc(_FakeGroupRepo([group]), _FakeCollectionRepo(coll))(
            UpdatePlateGroupCommand(workspace_id=WS, group_id=group.id, collection_id=coll.id),
            auth=_auth(),
        )

        assert isinstance(result, Success)
        assert result.unwrap().group.collection_id == coll.id
        assert result.unwrap().collection_name == "SACCZ"

    async def test_unknown_collection_is_not_found(self) -> None:
        group = _group("Lib")

        result = await self._uc(_FakeGroupRepo([group]), _FakeCollectionRepo())(
            UpdatePlateGroupCommand(
                workspace_id=WS, group_id=group.id, collection_id=uuid.uuid4()
            ),
            auth=_auth(),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert group.collection_id is None

    async def test_null_clears_without_lookup(self) -> None:
        coll = _collection()
        group = _group("Lib", collection_id=coll.id)
        collections = _FakeCollectionRepo()  # empty on purpose: clearing must not look up

        result = await self._uc(_FakeGroupRepo([group]), collections)(
            UpdatePlateGroupCommand(workspace_id=WS, group_id=group.id, collection_id=None),
            auth=_auth(),
        )

        assert isinstance(result, Success)
        assert result.unwrap().group.collection_id is None
        assert result.unwrap().collection_name is None

    async def test_unset_keeps_link_and_resolves_name(self) -> None:
        coll = _collection()
        group = _group("Lib", collection_id=coll.id)

        result = await self._uc(_FakeGroupRepo([group]), _FakeCollectionRepo(coll))(
            UpdatePlateGroupCommand(workspace_id=WS, group_id=group.id, name="Renamed"),
            auth=_auth(),
        )

        assert isinstance(result, Success)
        assert result.unwrap().group.collection_id == coll.id
        assert result.unwrap().collection_name == "SACCZ"


# ---------------------------------------------------------------------------
# Read enrichment
# ---------------------------------------------------------------------------


class TestReadEnrichment:
    async def test_tree_nodes_carry_names_with_one_batched_fetch(self) -> None:
        coll = _collection()
        other = _collection("NadD hits")
        root = _group("Lib", collection_id=coll.id)
        child = _group("Set", parent_group_id=root.id, collection_id=other.id)
        twin = _group("Lib2", collection_id=coll.id)
        unlinked = _group("Loose")
        collections = _FakeCollectionRepo(coll, other)

        result = await GetGroupTree(
            _FakeUow(), _FakeGroupRepo([root, child, twin, unlinked]), _visibility(), collections
        )(GetGroupTreeQuery(workspace_id=WS), auth=_auth("viewer"))

        assert isinstance(result, Success)
        by_name = {n.group.name: n for n in result.unwrap().roots}
        assert by_name["Lib"].collection_name == "SACCZ"
        assert by_name["Lib"].children[0].collection_name == "NadD hits"
        assert by_name["Lib2"].collection_name == "SACCZ"
        assert by_name["Loose"].collection_name is None
        assert len(collections.find_by_ids_calls) == 1
        assert sorted(collections.find_by_ids_calls[0]) == sorted([coll.id, other.id])

    async def test_detail_group_ancestors_children_carry_names(self) -> None:
        coll = _collection()
        other = _collection("NadD hits")
        root = _group("Lib", collection_id=coll.id)
        mid = _group("Mid", parent_group_id=root.id)
        leaf = _group("Leaf", parent_group_id=mid.id, collection_id=other.id)
        collections = _FakeCollectionRepo(coll, other)

        result = await GetPlateGroup(
            _FakeUow(), _FakeGroupRepo([root, mid, leaf]), _visibility(), collections
        )(GetPlateGroupQuery(workspace_id=WS, group_id=mid.id), auth=_auth("viewer"))

        assert isinstance(result, Success)
        detail = result.unwrap()
        assert detail.collection_name is None
        assert [a.group.name for a in detail.ancestors] == ["Lib"]
        assert detail.ancestors[0].collection_name == "SACCZ"
        assert detail.children[0].collection_name == "NadD hits"
        assert len(collections.find_by_ids_calls) == 1


# ---------------------------------------------------------------------------
# Reverse read
# ---------------------------------------------------------------------------


class TestListPlateGroupsForCollection:
    def _uc(
        self, collections: _FakeCollectionRepo, reader: _StubReader
    ) -> ListPlateGroupsForCollection:
        return ListPlateGroupsForCollection(_FakeUow(), collections, _visibility(), reader)

    async def test_viewer_sees_own_org_rows_only(self) -> None:
        coll = _collection()
        mine, theirs = _row(ORG_A, "Mine"), _row(ORG_B, "Theirs")
        reader = _StubReader([mine, theirs])

        result = await self._uc(_FakeCollectionRepo(coll), reader)(
            ListPlateGroupsForCollectionQuery(workspace_id=WS, collection_id=coll.id),
            auth=_auth("viewer"),
        )

        assert isinstance(result, Success)
        assert result.unwrap() == [mine]
        assert reader.calls == [coll.id]

    async def test_admin_sees_every_row(self) -> None:
        coll = _collection()
        rows = [_row(ORG_A, "Mine"), _row(ORG_B, "Theirs")]

        result = await self._uc(_FakeCollectionRepo(coll), _StubReader(rows))(
            ListPlateGroupsForCollectionQuery(workspace_id=WS, collection_id=coll.id),
            auth=_auth("admin"),
        )

        assert isinstance(result, Success)
        assert result.unwrap() == rows

    async def test_unknown_collection_is_not_found(self) -> None:
        reader = _StubReader([_row(ORG_A)])

        result = await self._uc(_FakeCollectionRepo(), reader)(
            ListPlateGroupsForCollectionQuery(workspace_id=WS, collection_id=uuid.uuid4()),
            auth=_auth("viewer"),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert reader.calls == []

    async def test_other_workspace_raises_not_found(self) -> None:
        coll = _collection()

        with pytest.raises(NotFoundError):
            await self._uc(_FakeCollectionRepo(coll), _StubReader([]))(
                ListPlateGroupsForCollectionQuery(workspace_id=WS, collection_id=coll.id),
                auth=_auth("viewer", workspace_id=uuid.uuid4()),
            )
