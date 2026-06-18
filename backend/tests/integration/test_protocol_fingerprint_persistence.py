"""Integration test: protocol fingerprint is computed on save and round-trips correctly."""
from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def test_fingerprint_is_written_and_round_trips(uow: AsyncUnitOfWork) -> None:
    ws = uuid.uuid4()
    pid = uuid.uuid4()
    protocol = Protocol.create(
        workspace_id=ws,
        name="MDH Resazurin dose response",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="IC50", data_type=ReadoutDataType.NUMERIC),
            ReadoutDefinition(protocol_id=pid, name="Hill slope", data_type=ReadoutDataType.NUMERIC),
        ],
    )
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(protocol)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        reloaded = await repo.find_by_id_in_workspace(ws, protocol.id)
        assert reloaded is not None
        assert reloaded.fingerprint is not None
        assert reloaded.fingerprint["readout_kinds"] == ["hill slope", "ic50"]
        assert reloaded.fingerprint["protocol_type"] == "biochemical"
