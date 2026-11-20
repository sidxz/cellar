"""Migration 092: protocols gain a JSONB references list (not null, default [])."""

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ProtocolReference, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_PID = uuid.UUID(int=0)


def _protocol(workspace_id, user_id, refs):  # type: ignore[no-untyped-def]
    return Protocol.create(
        workspace_id=workspace_id,
        name=f"p {uuid.uuid4()}",
        protocol_type=ProtocolType.WHOLE_CELL,
        created_by=user_id,
        readout_definitions=[
            ReadoutDefinition(protocol_id=_PID, name="MIC", data_type=ReadoutDataType.NUMERIC)
        ],
        references=refs,
    )


async def _round_trip(session_factory, workspace_id, protocol):  # type: ignore[no-untyped-def]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(protocol)
        await uow.commit()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        loaded = await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(
            workspace_id, protocol.id
        )
    assert loaded is not None
    return loaded


async def test_repository_round_trips_references(session_factory, workspace_id, user_id):
    refs = [
        ProtocolReference(kind="chembl_assay", value="CHEMBL1054500"),
        ProtocolReference(kind="doi", value="https://doi.org/10.1021/jm901137j"),
    ]
    loaded = await _round_trip(
        session_factory, workspace_id, _protocol(workspace_id, user_id, refs)
    )
    assert loaded.references == refs
    assert [r.key for r in loaded.references] == [
        "chembl_assay:CHEMBL1054500",
        "doi:10.1021/jm901137j",
    ]


async def test_no_references_round_trip_as_an_empty_list(session_factory, workspace_id, user_id):
    loaded = await _round_trip(session_factory, workspace_id, _protocol(workspace_id, user_id, []))
    assert loaded.references == []
