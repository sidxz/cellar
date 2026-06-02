"""Integration tests for tag filtering (composer criterion + list endpoints)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text

from cellar.domain.workspace_config.tagging.tag import TagName, TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    MoleculeTagLinkRepository,
    get_tag_link_repository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _org_and_molecule(uow: AsyncUnitOfWork, ws: uuid.UUID, reg: str) -> uuid.UUID:
    org_id, mol_id = uuid.uuid4(), uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, "
            "version) VALUES (:id, :ws, :n, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws, "n": f"org-{reg}"},
    )
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, version, originating_org_id) VALUES "
            "(:id, :ws, :r, :r, 'small_molecule', 1, :org)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "org": org_id},
    )
    return mol_id


class TestComposerTagCriterion:
    async def test_filter_any_and_all(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            t1 = await tag_repo.get_or_create(ws, TagName(key="a"), user)
            t2 = await tag_repo.get_or_create(ws, TagName(key="b"), user)
            m1 = await _org_and_molecule(uow, ws, "F-1")
            m2 = await _org_and_molecule(uow, ws, "F-2")
            links = MoleculeTagLinkRepository(uow)
            await links.add(ws, m1, t1.id, user)
            await links.add(ws, m1, t2.id, user)
            await links.add(ws, m2, t1.id, user)
            await uow.commit()

        async with uow:
            any_clause = compose_criteria(
                {"criteria": [{"type": "tag", "tag_ids": [str(t1.id), str(t2.id)], "tag_logic": "any"}]},
                workspace_id=ws,
            )
            all_clause = compose_criteria(
                {"criteria": [{"type": "tag", "tag_ids": [str(t1.id), str(t2.id)], "tag_logic": "all"}]},
                workspace_id=ws,
            )
            neg_clause = compose_criteria(
                {"criteria": [{"type": "tag", "tag_ids": [str(t2.id)], "negate": True}]},
                workspace_id=ws,
            )
            base = select(MoleculeModel.id).where(MoleculeModel.workspace_id == ws)
            any_ids = {r for r in (await uow.session.execute(base.where(any_clause))).scalars()}
            all_ids = {r for r in (await uow.session.execute(base.where(all_clause))).scalars()}
            neg_ids = {r for r in (await uow.session.execute(base.where(neg_clause))).scalars()}
        assert any_ids == {m1, m2}
        assert all_ids == {m1}
        assert neg_ids == {m2}  # m2 does NOT have t2


# ---------------------------------------------------------------------------
# Project tag-filter tests (F2)
# ---------------------------------------------------------------------------


async def _insert_project(uow: AsyncUnitOfWork, ws: uuid.UUID, name: str) -> uuid.UUID:
    """Insert a minimal project row. Columns with server defaults are omitted."""
    pid = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, name, status, created_by, version) "
            "VALUES (:id, :ws, :n, 'active', :user, 1)"
        ),
        {"id": pid, "ws": ws, "n": name, "user": uuid.uuid4()},
    )
    return pid


class TestProjectListTagFilter:
    async def test_filters_projects_by_tag_any(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws, TagName(key="flagged"), user)
            p1 = await _insert_project(uow, ws, "P-tagged")
            await _insert_project(uow, ws, "P-untagged")
            links = get_tag_link_repository(TaggableEntityType.PROJECT, uow)
            await links.add(ws, p1, tag.id, user)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            rows = await repo.find_by_workspace(ws, tags=[tag.id], tag_logic="any")
        assert {p.id for p in rows} == {p1}

    async def test_filters_projects_by_tag_all(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            t1 = await tag_repo.get_or_create(ws, TagName(key="p-a"), user)
            t2 = await tag_repo.get_or_create(ws, TagName(key="p-b"), user)
            p_both = await _insert_project(uow, ws, "P-both")
            p_one = await _insert_project(uow, ws, "P-one")
            links = get_tag_link_repository(TaggableEntityType.PROJECT, uow)
            await links.add(ws, p_both, t1.id, user)
            await links.add(ws, p_both, t2.id, user)
            await links.add(ws, p_one, t1.id, user)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            rows_all = await repo.find_by_workspace(ws, tags=[t1.id, t2.id], tag_logic="all")
            rows_any = await repo.find_by_workspace(ws, tags=[t1.id, t2.id], tag_logic="any")
        assert {p.id for p in rows_all} == {p_both}
        assert {p.id for p in rows_any} == {p_both, p_one}

    async def test_no_tags_returns_all(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            p1 = await _insert_project(uow, ws, "PA-1")
            p2 = await _insert_project(uow, ws, "PA-2")
            await uow.commit()

        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            rows = await repo.find_by_workspace(ws)
        assert {p.id for p in rows} == {p1, p2}


# ---------------------------------------------------------------------------
# Collection tag-filter tests (F2)
# ---------------------------------------------------------------------------


async def _insert_collection(uow: AsyncUnitOfWork, ws: uuid.UUID, name: str) -> uuid.UUID:
    """Insert a minimal collection row. visibility/is_frozen have server defaults."""
    cid = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO collections (id, workspace_id, name, created_by, version) "
            "VALUES (:id, :ws, :n, :user, 1)"
        ),
        {"id": cid, "ws": ws, "n": name, "user": uuid.uuid4()},
    )
    return cid


class TestCollectionListTagFilter:
    async def test_filters_collections_by_tag_any(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws, TagName(key="c-flagged"), user)
            c1 = await _insert_collection(uow, ws, "C-tagged")
            await _insert_collection(uow, ws, "C-untagged")
            links = get_tag_link_repository(TaggableEntityType.COLLECTION, uow)
            await links.add(ws, c1, tag.id, user)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            rows = await repo.find_by_workspace(ws, tags=[tag.id], tag_logic="any")
        assert {c.id for c in rows} == {c1}

    async def test_filters_collections_by_tag_all(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            t1 = await tag_repo.get_or_create(ws, TagName(key="c-a"), user)
            t2 = await tag_repo.get_or_create(ws, TagName(key="c-b"), user)
            c_both = await _insert_collection(uow, ws, "C-both")
            c_one = await _insert_collection(uow, ws, "C-one")
            links = get_tag_link_repository(TaggableEntityType.COLLECTION, uow)
            await links.add(ws, c_both, t1.id, user)
            await links.add(ws, c_both, t2.id, user)
            await links.add(ws, c_one, t1.id, user)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            rows_all = await repo.find_by_workspace(ws, tags=[t1.id, t2.id], tag_logic="all")
            rows_any = await repo.find_by_workspace(ws, tags=[t1.id, t2.id], tag_logic="any")
        assert {c.id for c in rows_all} == {c_both}
        assert {c.id for c in rows_any} == {c_both, c_one}

    async def test_no_tags_returns_all(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            c1 = await _insert_collection(uow, ws, "CA-1")
            c2 = await _insert_collection(uow, ws, "CA-2")
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            rows = await repo.find_by_workspace(ws)
        assert {c.id for c in rows} == {c1, c2}


# ---------------------------------------------------------------------------
# Protocol tag-filter tests (F2)
# ---------------------------------------------------------------------------


async def _insert_protocol(uow: AsyncUnitOfWork, ws: uuid.UUID, name: str) -> uuid.UUID:
    """Insert a minimal protocol row. Columns with server defaults are omitted."""
    pid = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, protocol_version, created_by, version) "
            "VALUES (:id, :ws, :n, 'biochemical', 1, :user, 1)"
        ),
        {"id": pid, "ws": ws, "n": name, "user": uuid.uuid4()},
    )
    return pid


class TestProtocolListTagFilter:
    async def test_filters_protocols_by_tag_any(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws, TagName(key="pr-flagged"), user)
            pr1 = await _insert_protocol(uow, ws, "Pr-tagged")
            await _insert_protocol(uow, ws, "Pr-untagged")
            links = get_tag_link_repository(TaggableEntityType.PROTOCOL, uow)
            await links.add(ws, pr1, tag.id, user)
            await uow.commit()

        async with uow:
            from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
                SQLAlchemyProtocolRepository,
            )
            repo = SQLAlchemyProtocolRepository(uow)
            rows = await repo.find_by_workspace(ws, tags=[tag.id], tag_logic="any")
        assert {p.id for p in rows} == {pr1}
