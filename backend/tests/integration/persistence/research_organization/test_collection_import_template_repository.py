"""Integration tests for SQLAlchemyCollectionImportTemplateRepository."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_import_template_repository import (
    SQLAlchemyCollectionImportTemplateRepository,
)


@pytest.mark.asyncio
async def test_save_and_find_by_workspace(uow):
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    tpl = CollectionImportTemplate.create(
        workspace_id=ws_id,
        name="Partner ACME",
        column_mapping={"registration_number": "Reg No.", "name": "Compound"},
        created_by=user_id,
    )
    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        await repo.save(tpl)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        found = await repo.find_by_workspace(ws_id)

    assert len(found) == 1
    assert found[0].name == "Partner ACME"
    assert found[0].column_mapping == {
        "registration_number": "Reg No.",
        "name": "Compound",
    }
    assert found[0].created_by == user_id


@pytest.mark.asyncio
async def test_update_persists_new_mapping(uow):
    ws_id = uuid.uuid4()
    tpl = CollectionImportTemplate.create(
        workspace_id=ws_id,
        name="t1",
        column_mapping={"name": "X"},
        created_by=uuid.uuid4(),
    )
    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        await repo.save(tpl)
        await uow.commit()

    tpl.update(column_mapping={"name": "X", "smiles": "Structure"})

    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        await repo.save(tpl)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        reloaded = await repo.find_by_id_in_workspace(ws_id, tpl.id)

    assert reloaded is not None
    assert reloaded.column_mapping["smiles"] == "Structure"
    assert reloaded.column_mapping["name"] == "X"


@pytest.mark.asyncio
async def test_find_by_workspace_scopes_to_workspace(uow):
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    tpl_a = CollectionImportTemplate.create(
        workspace_id=ws_a,
        name="A-template",
        column_mapping={"name": "Compound"},
        created_by=uuid.uuid4(),
    )
    tpl_b = CollectionImportTemplate.create(
        workspace_id=ws_b,
        name="B-template",
        column_mapping={"name": "Compound"},
        created_by=uuid.uuid4(),
    )
    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        await repo.save(tpl_a)
        await repo.save(tpl_b)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        found_a = await repo.find_by_workspace(ws_a)

    assert [t.id for t in found_a] == [tpl_a.id]


@pytest.mark.asyncio
async def test_delete_removes_template(uow):
    ws_id = uuid.uuid4()
    tpl = CollectionImportTemplate.create(
        workspace_id=ws_id,
        name="to-delete",
        column_mapping={"name": "X"},
        created_by=uuid.uuid4(),
    )
    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        await repo.save(tpl)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        await repo.delete(ws_id, tpl.id)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyCollectionImportTemplateRepository(uow)
        reloaded = await repo.find_by_id_in_workspace(ws_id, tpl.id)

    assert reloaded is None
