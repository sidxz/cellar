"""Integration tests for tag admin ops (repoint / merge / delete cascade)."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from cellar.domain.workspace_config.tagging.tag import TaggableEntityType, TagName
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
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


class TestRepoint:
    async def test_repoint_moves_links_and_dedups(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            a = await tag_repo.get_or_create(ws, TagName(key="a"), user)
            b = await tag_repo.get_or_create(ws, TagName(key="b"), user)
            m1 = await _org_and_molecule(uow, ws, "RP-1")  # has a
            m2 = await _org_and_molecule(uow, ws, "RP-2")  # has a + b
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await links.add(ws, m1, a.id, user)
            await links.add(ws, m2, a.id, user)
            await links.add(ws, m2, b.id, user)
            await uow.commit()
        async with uow:
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await links.repoint(a.id, b.id)
            await uow.commit()
        async with uow:
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            m1_tags = {t.key for t in await links.find_tags_for_entity(ws, m1)}
            m2_tags = {t.key for t in await links.find_tags_for_entity(ws, m2)}
            assert m1_tags == {"b"}
            assert m2_tags == {"b"}
            res = await uow.session.execute(
                text("SELECT count(*) FROM molecule_tags WHERE tag_id = :id"),
                {"id": a.id},
            )
            assert res.scalar_one() == 0


from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    SQLAlchemyTagLinkRepositoryProvider,
)


class TestMergeIntegration:
    async def test_merge_moves_links_and_drops_source_tag(
        self, uow: AsyncUnitOfWork
    ) -> None:
        from unittest.mock import AsyncMock

        from cellar.application.workspace_config.tagging.merge_tags import (
            MergeTags,
            MergeTagsCommand,
        )

        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            src = await tag_repo.get_or_create(ws, TagName(key="src"), user)
            tgt = await tag_repo.get_or_create(ws, TagName(key="tgt"), user)
            m1 = await _org_and_molecule(uow, ws, "MG-1")
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await links.add(ws, m1, src.id, user)
            await uow.commit()

        class _Auth:
            user_id = user
            workspace_id = ws
            workspace_role = "admin"
            is_admin = True

            def has_role(self, m: str) -> bool:
                return True

        uc = MergeTags(
            uow,
            SQLAlchemyTagRepository(uow),
            SQLAlchemyTagLinkRepositoryProvider(uow),
            AsyncMock(),
        )
        result = await uc(
            MergeTagsCommand(workspace_id=ws, source_tag_id=src.id, target_tag_id=tgt.id),
            auth=_Auth(),
        )
        assert result.unwrap().id == tgt.id

        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            assert await tag_repo.find_by_id_in_workspace(ws, src.id) is None
            links = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert {t.key for t in await links.find_tags_for_entity(ws, m1)} == {"tgt"}
