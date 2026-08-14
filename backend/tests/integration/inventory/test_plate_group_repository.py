"""Integration tests for SQLAlchemyPlateGroupRepository."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.value_objects import Barcode
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_group_repository import (
    SQLAlchemyPlateGroupRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

WS = uuid.uuid4()
ORG = uuid.uuid4()
USER = uuid.uuid4()


def _group(name: str, parent: uuid.UUID | None = None) -> PlateGroup:
    return PlateGroup.create(
        workspace_id=WS,
        owner_org_id=ORG,
        name=name,
        created_by=USER,
        parent_group_id=parent,
    )


@pytest.mark.integration
async def test_round_trip_and_children(session_factory) -> None:
    root = _group("Root")
    child = _group("Child", parent=root.id)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        await repo.save(root)
        await repo.save(child)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        loaded = await repo.find_by_id_in_workspace(WS, child.id)
        assert loaded is not None
        assert loaded.parent_group_id == root.id
        kids = await repo.find_children(WS, root.id)
        assert [g.id for g in kids] == [child.id]
        all_org = await repo.find_by_workspace(WS, owner_org_id=ORG)
        assert {g.id for g in all_org} == {root.id, child.id}


@pytest.mark.integration
async def test_root_name_unique_nulls_not_distinct(session_factory) -> None:
    ws = uuid.uuid4()
    a = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="Dup", created_by=USER)
    b = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="Dup", created_by=USER)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        await repo.save(a)
        await uow.commit()
    with pytest.raises(IntegrityError):
        async with AsyncUnitOfWork(session_factory) as uow:
            repo = SQLAlchemyPlateGroupRepository(uow)
            await repo.save(b)
            await uow.commit()


@pytest.mark.integration
async def test_find_by_name_null_parent(session_factory) -> None:
    ws = uuid.uuid4()
    g = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="FindMe", created_by=USER)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        await repo.save(g)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        found = await repo.find_by_name(ws, ORG, None, "FindMe")
        assert found is not None and found.id == g.id
        assert await repo.find_by_name(ws, ORG, None, "Nope") is None


@pytest.mark.integration
async def test_plate_group_id_round_trip_and_counts(session_factory) -> None:
    ws = uuid.uuid4()
    g = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="G", created_by=USER)
    plate = RegisteredPlate.register(
        workspace_id=ws,
        owner_org_id=ORG,
        barcode=Barcode(value=f"PG-{uuid.uuid4().hex[:8]}"),
        plate_label="p1",
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=USER,
    )
    plate.assign_to_group(g.id)
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyPlateGroupRepository(uow).save(g)
        await SQLAlchemyRegisteredPlateRepository(uow).save(plate)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        prepo = SQLAlchemyRegisteredPlateRepository(uow)
        loaded = await prepo.find_by_id_in_workspace(ws, plate.id)
        assert loaded is not None and loaded.group_id == g.id
        counts = await SQLAlchemyPlateGroupRepository(uow).count_plates_by_group(ws)
        assert counts == {g.id: 1}
        filtered = await prepo.search(ws, group_id=g.id)
        assert [p.id for p in filtered] == [plate.id]


@pytest.mark.integration
async def test_count_plates_by_group_scoped_to_org(session_factory) -> None:
    ws = uuid.uuid4()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    group_a = PlateGroup.create(workspace_id=ws, owner_org_id=org_a, name="A", created_by=USER)
    group_b = PlateGroup.create(workspace_id=ws, owner_org_id=org_b, name="B", created_by=USER)
    plate_a = RegisteredPlate.register(
        workspace_id=ws,
        owner_org_id=org_a,
        barcode=Barcode(value=f"PG-{uuid.uuid4().hex[:8]}"),
        plate_label="pa",
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=USER,
    )
    plate_a.assign_to_group(group_a.id)
    plate_b = RegisteredPlate.register(
        workspace_id=ws,
        owner_org_id=org_b,
        barcode=Barcode(value=f"PG-{uuid.uuid4().hex[:8]}"),
        plate_label="pb",
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=USER,
    )
    plate_b.assign_to_group(group_b.id)
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyPlateGroupRepository(uow).save(group_a)
        await SQLAlchemyPlateGroupRepository(uow).save(group_b)
        await SQLAlchemyRegisteredPlateRepository(uow).save(plate_a)
        await SQLAlchemyRegisteredPlateRepository(uow).save(plate_b)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        scoped = await repo.count_plates_by_group(ws, owner_org_id=org_a)
        assert scoped == {group_a.id: 1}
        assert group_b.id not in scoped

        unscoped = await repo.count_plates_by_group(ws)
        assert unscoped == {group_a.id: 1, group_b.id: 1}


@pytest.mark.integration
async def test_group_delete_sets_plate_group_null(session_factory) -> None:
    ws = uuid.uuid4()
    g = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="Doomed", created_by=USER)
    plate = RegisteredPlate.register(
        workspace_id=ws,
        owner_org_id=ORG,
        barcode=Barcode(value=f"PG-{uuid.uuid4().hex[:8]}"),
        plate_label="p1",
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=USER,
    )
    plate.assign_to_group(g.id)
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyPlateGroupRepository(uow).save(g)
        await SQLAlchemyRegisteredPlateRepository(uow).save(plate)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyPlateGroupRepository(uow).delete(ws, g.id)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        loaded = await SQLAlchemyRegisteredPlateRepository(uow).find_by_id_in_workspace(
            ws, plate.id
        )
        assert loaded is not None and loaded.group_id is None  # DB SET NULL
