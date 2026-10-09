"""Protocol aliases round-trip through the repository in order."""

import uuid

from cellar.domain.screening_assay.enums import AliasKind, ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _protocol(ws, user):
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=ws,
        name="M. tuberculosis growth inhibition [resazurin]",
        protocol_type=ProtocolType.WHOLE_CELL,
        created_by=user,
        code="PRT-00001",
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="Signal", data_type=ReadoutDataType.NUMERIC)
        ],
    )


async def test_aliases_persist_in_order(session_factory, workspace_id, user_id):
    p = _protocol(workspace_id, user_id)
    p.add_nickname("MABA")
    p.add_nickname("Alamar MIC")
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(p)
        await uow.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        loaded = await repo.find_by_id_in_workspace(workspace_id, p.id)
        assert [(a.label, a.kind) for a in loaded.aliases] == [
            ("MABA", AliasKind.NICKNAME),
            ("Alamar MIC", AliasKind.NICKNAME),
        ]
        loaded.remove_nickname("maba")
        await repo.save(loaded)
        await uow.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        again = await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(workspace_id, p.id)
        assert [a.label for a in again.aliases] == ["Alamar MIC"]
