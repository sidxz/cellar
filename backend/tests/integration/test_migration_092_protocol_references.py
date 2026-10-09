"""Migration 092: protocols gain a JSONB references list (not null, default [])."""

import importlib.util
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ProtocolReference, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_M092 = Path(__file__).parents[2] / "alembic" / "versions" / "092_protocol_references.py"
_PID = uuid.UUID(int=0)


def _load_m092():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m092", _M092)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _column(sync_conn) -> tuple[str, str] | None:  # type: ignore[no-untyped-def]
    row = sync_conn.execute(
        text(
            "select is_nullable, column_default from information_schema.columns "
            "where table_name='protocols' and column_name='references'"
        )
    ).first()
    return None if row is None else (row[0], row[1])


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


async def test_downgrade_drops_and_upgrade_restores_the_column(session_factory):
    m092 = _load_m092()

    def run(sync_conn):  # type: ignore[no-untyped-def]
        with Operations.context(MigrationContext.configure(sync_conn)):
            m092.downgrade()
            after_down = _column(sync_conn)
            m092.upgrade()
        return after_down, _column(sync_conn)

    async with session_factory() as s:
        after_down, after_up = await s.run_sync(lambda sync: run(sync.connection()))
        await s.rollback()  # DDL is transactional: the shared test schema stays at head
    assert after_down is None
    assert after_up is not None
    nullable, default = after_up
    assert nullable == "NO"
    assert default is not None and "'[]'::jsonb" in default
