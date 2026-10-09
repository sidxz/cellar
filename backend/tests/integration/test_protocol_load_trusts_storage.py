"""A stored value today's input validation would refuse still loads (validation is input-only)."""

import uuid

from sqlalchemy import text

from cellar.domain.screening_assay.enums import ConditionDataType, ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_PID = uuid.UUID(int=0)


async def test_stale_reference_and_fixed_value_still_load(session_factory, workspace_id, user_id):
    protocol = Protocol.create(
        workspace_id=workspace_id,
        name=f"p {uuid.uuid4()}",
        protocol_type=ProtocolType.WHOLE_CELL,
        created_by=user_id,
        readout_definitions=[
            ReadoutDefinition(protocol_id=_PID, name="MIC", data_type=ReadoutDataType.NUMERIC)
        ],
        condition_definitions=[
            ConditionDefinition(
                protocol_id=_PID,
                name="Incubation time",
                data_type=ConditionDataType.NUMERIC,
                unit="h",
                fixed_value="72",
            )
        ],
    )
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(protocol)
        await uow.commit()

    # Rows written under older, looser rules (or before a validator was tightened).
    async with session_factory() as s:
        await s.execute(
            text(
                'update protocols set "references" = '
                """'[{"kind": "doi", "value": "doi-under-old-rules"}]'::jsonb where id = :id"""
            ),
            {"id": protocol.id},
        )
        await s.execute(
            text("update condition_definitions set fixed_value = '72h' where protocol_id = :id"),
            {"id": protocol.id},
        )
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        loaded = await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(
            workspace_id, protocol.id
        )
    assert loaded is not None
    assert [r.key for r in loaded.references] == ["doi:doi-under-old-rules"]
    assert loaded.condition_definitions[0].fixed_value == "72h"
