"""Integration tests for tag filtering (composer criterion + list endpoints)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text

from cellar.domain.workspace_config.tagging.tag import TagName
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    MoleculeTagLinkRepository,
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
