"""Protocol codes: minted per workspace, sequential, shared by versions."""

import asyncio
import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.protocol_versioning_service import ProtocolVersioningService
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _protocol(ws, user, code):
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=ws, name=f"P {code}", protocol_type=ProtocolType.BIOCHEMICAL, created_by=user, code=code,
        readout_definitions=[ReadoutDefinition(protocol_id=pid, name="Signal", data_type=ReadoutDataType.NUMERIC)],
    )


async def test_codes_are_sequential_per_workspace(uow, workspace_id, user_id):
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        first = await repo.next_protocol_code(workspace_id, prefix="PRT-", width=5)
        await repo.save(_protocol(workspace_id, user_id, first))
        second = await repo.next_protocol_code(workspace_id, prefix="PRT-", width=5)
        await uow.commit()
    assert (first, second) == ("PRT-00001", "PRT-00002")


async def test_concurrent_mints_never_collide(session_factory, workspace_id, user_id):
    async def mint_and_save():
        uow = AsyncUnitOfWork(session_factory)
        async with uow:
            repo = SQLAlchemyProtocolRepository(uow)
            code = await repo.next_protocol_code(workspace_id, prefix="PRT-", width=5)
            await repo.save(_protocol(workspace_id, user_id, code))
            await uow.commit()
        return code

    codes = await asyncio.gather(*(mint_and_save() for _ in range(4)))
    assert len(set(codes)) == 4


async def test_new_version_shares_the_code(uow, workspace_id, user_id):
    p = _protocol(workspace_id, user_id, "PRT-00007")
    p.publish()
    child = ProtocolVersioningService().create_new_version(p)
    assert child.code == "PRT-00007" and child.protocol_version == 2
