"""Readout definitions load in display_order, not in the order the rows were stored."""

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def test_readouts_load_in_display_order(session_factory, workspace_id, user_id):
    pid = uuid.uuid4()
    # Stored in reverse of their display order, so heap order disagrees with display_order.
    readouts = [
        ReadoutDefinition(
            protocol_id=pid, name=name, data_type=ReadoutDataType.NUMERIC, display_order=order
        )
        for name, order in [("% inhibition", 3), ("GI50", 2), ("Signal", 1)]
    ]
    p = Protocol.create(
        workspace_id=workspace_id,
        name="A549 growth inhibition",
        protocol_type=ProtocolType.CELL_BASED,
        created_by=user_id,
        code="PRT-00001",
        readout_definitions=readouts,
    )
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(p)
        await uow.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        loaded = await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(
            workspace_id, p.id
        )
        assert [r.name for r in loaded.readout_definitions] == ["Signal", "GI50", "% inhibition"]
