"""Migration 091: condition definitions gain a nullable fixed_value; existing rows stay."""

import importlib.util
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
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

_M091 = Path(__file__).parents[2] / "alembic" / "versions" / "091_condition_fixed_value.py"
_PID = uuid.UUID(int=0)


def _load_m091():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m091", _M091)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _has_column(sync_conn) -> bool:  # type: ignore[no-untyped-def]
    return bool(
        sync_conn.execute(
            text(
                "select 1 from information_schema.columns "
                "where table_name='condition_definitions' and column_name='fixed_value'"
            )
        ).scalar()
    )


async def test_repository_round_trips_the_fixed_value(session_factory, workspace_id, user_id):
    protocol = Protocol.create(
        workspace_id=workspace_id,
        name="p",
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
            ),
            ConditionDefinition(protocol_id=_PID, name="Medium", data_type=ConditionDataType.TEXT),
        ],
    )
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
    assert {cd.name: cd.fixed_value for cd in loaded.condition_definitions} == {
        "Incubation time": "72",
        "Medium": None,
    }


async def test_downgrade_drops_and_upgrade_restores_the_column(session_factory):
    m091 = _load_m091()

    def run(sync_conn) -> tuple[bool, bool]:  # type: ignore[no-untyped-def]
        with Operations.context(MigrationContext.configure(sync_conn)):
            m091.downgrade()
            after_down = _has_column(sync_conn)
            m091.upgrade()
        return after_down, _has_column(sync_conn)

    async with session_factory() as s:
        after_down, after_up = await s.run_sync(lambda sync: run(sync.connection()))
        await s.rollback()  # DDL is transactional: the shared test schema stays at head
    assert (after_down, after_up) == (False, True)
