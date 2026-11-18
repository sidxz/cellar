"""Migration 103: readout_data.replicate_count (nullable, >= 1)."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

_M103 = Path(__file__).parents[2] / "alembic" / "versions" / "103_readout_data_replicate_count.py"


def _load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m103", _M103)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _has_column(sync_conn) -> bool:  # type: ignore[no-untyped-def]
    return (
        sync_conn.execute(
            text(
                "select count(*) from information_schema.columns "
                "where table_name='readout_data' and column_name='replicate_count'"
            )
        ).scalar_one()
        == 1
    )


async def test_upgrade_adds_column_and_downgrade_removes_it(session_factory):
    m103 = _load()

    def run(sync_conn):  # type: ignore[no-untyped-def]
        # The test schema is built from the models, so start from the old shape.
        with Operations.context(MigrationContext.configure(sync_conn)):
            m103.downgrade()
            gone = not _has_column(sync_conn)
            m103.upgrade()
            back = _has_column(sync_conn)
            check = sync_conn.execute(
                text(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conname = 'ck_readout_data_replicates'"
                )
            ).scalar_one_or_none()
        return gone, back, check

    async with session_factory() as s:
        gone, back, check = await s.run_sync(lambda sync: run(sync.connection()))
        await s.rollback()
    assert gone and back
    assert check is not None and ">= 1" in check
