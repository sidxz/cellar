"""Migration 098: the ``latest_approved_run`` selection rule is stored as ``latest_run``.

Every stored copy moves: campaign channels, saved-search and export-job
aggregation, SAR channel specs and cached SAR value snapshots. The audit
trail is append-only and is never touched.
"""

import importlib.util
import json
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

_M098 = Path(__file__).parents[2] / "alembic" / "versions" / "098_rename_latest_run_rule.py"


def _load_m098():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m098", _M098)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ROWS = {
    "campaign_channel": "select selection_rule from campaign_channel where id = :id",
    "saved_searches": "select query->>'aggregation' from saved_searches where id = :id",
    "export_jobs": "select query_snapshot->>'aggregation' from export_jobs where id = :id",
    "sar_activity_projections": (
        "select channel_spec->>'selection_rule' from sar_activity_projections where id = :id"
    ),
    "sar_activity_values": (
        "select snapshot->>'selection_rule' from sar_activity_values where projection_id = :id"
    ),
}


def _seed(sync_conn, ids: dict[str, uuid.UUID], ws: uuid.UUID, user: uuid.UUID) -> None:  # type: ignore[no-untyped-def]
    old = "latest_approved_run"
    campaign_id = uuid.uuid4()
    sync_conn.execute(
        text(
            "insert into campaign (id, workspace_id, project_id, name, created_by) "
            "values (:id, :ws, :pid, 'c', :u)"
        ),
        {"id": campaign_id, "ws": ws, "pid": uuid.uuid4(), "u": user},
    )
    sync_conn.execute(
        text(
            "insert into campaign_channel (id, campaign_id, label, protocol_id, "
            "readout_definition_id, source_kind, selection_rule, qualifier_handling) "
            "values (:id, :cid, 'IC50', :p, :rd, 'dr_curve', :rule, 'exclude_qualified')"
        ),
        {
            "id": ids["campaign_channel"],
            "cid": campaign_id,
            "p": uuid.uuid4(),
            "rd": uuid.uuid4(),
            "rule": old,
        },
    )
    sync_conn.execute(
        text(
            "insert into saved_searches (id, workspace_id, name, query, visibility, "
            "created_by, version) values (:id, :ws, 's', cast(:q as jsonb), 'private', :u, 1)"
        ),
        {
            "id": ids["saved_searches"],
            "ws": ws,
            "u": user,
            "q": json.dumps({"logic": "and", "criteria": [], "aggregation": old}),
        },
    )
    sync_conn.execute(
        text(
            "insert into export_jobs (id, workspace_id, requested_by, source, format, "
            "query_snapshot, status, requested_at) "
            "values (:id, :ws, :u, 'search', 'csv', cast(:q as jsonb), 'queued', now())"
        ),
        {
            "id": ids["export_jobs"],
            "ws": ws,
            "u": user,
            "q": json.dumps({"query": {"criteria": []}, "aggregation": old}),
        },
    )
    sync_conn.execute(
        text(
            "insert into sar_activity_projections (id, workspace_id, requested_by, "
            "membership_hash, channel_hash, channel_spec, requested_at, status) "
            "values (:id, :ws, :u, 'm', 'h', cast(:spec as jsonb), now(), 'ready')"
        ),
        {
            "id": ids["sar_activity_projections"],
            "ws": ws,
            "u": user,
            "spec": json.dumps({"column": "drc:x", "selection_rule": old}),
        },
    )
    sync_conn.execute(
        text(
            "insert into sar_activity_values (projection_id, molecule_id, scalar, source, "
            "snapshot) values (:id, :m, 1.0, 'dose_response', cast(:snap as jsonb))"
        ),
        {
            "id": ids["sar_activity_projections"],
            "m": uuid.uuid4(),
            "snap": json.dumps({"value": 1.0, "selection_rule": old}),
        },
    )


def _read(sync_conn, ids: dict[str, uuid.UUID]) -> dict[str, str]:  # type: ignore[no-untyped-def]
    key_for_values = ids["sar_activity_projections"]
    out: dict[str, str] = {}
    for table, sql in _ROWS.items():
        row_id = key_for_values if table == "sar_activity_values" else ids[table]
        out[table] = sync_conn.execute(text(sql), {"id": row_id}).scalar_one()
    return out


def _audit_count(sync_conn) -> int:  # type: ignore[no-untyped-def]
    return int(sync_conn.execute(text("select count(*) from audit_operations")).scalar_one())


async def test_upgrade_renames_every_stored_copy_and_downgrade_restores(
    session_factory, workspace_id, user_id
):
    m098 = _load_m098()
    ids = {t: uuid.uuid4() for t in _ROWS if t != "sar_activity_values"}

    def run(sync_conn):  # type: ignore[no-untyped-def]
        _seed(sync_conn, ids, workspace_id, user_id)
        audit_before = _audit_count(sync_conn)
        with Operations.context(MigrationContext.configure(sync_conn)):
            m098.upgrade()
            after_up = _read(sync_conn, ids)
            audit_after = _audit_count(sync_conn)
            m098.downgrade()
            after_down = _read(sync_conn, ids)
        return after_up, after_down, audit_before, audit_after

    async with session_factory() as s:
        after_up, after_down, audit_before, audit_after = await s.run_sync(
            lambda sync: run(sync.connection())
        )
        await s.rollback()

    assert set(after_up.values()) == {"latest_run"}
    assert set(after_down.values()) == {"latest_approved_run"}
    assert audit_before == audit_after


async def test_upgrade_leaves_other_rules_alone(session_factory, workspace_id, user_id):
    m098 = _load_m098()
    sid = uuid.uuid4()

    def run(sync_conn):  # type: ignore[no-untyped-def]
        sync_conn.execute(
            text(
                "insert into saved_searches (id, workspace_id, name, query, visibility, "
                "created_by, version) values (:id, :ws, 's', cast(:q as jsonb), 'private', :u, 1)"
            ),
            {
                "id": sid,
                "ws": workspace_id,
                "u": user_id,
                "q": json.dumps({"criteria": [], "aggregation": "geometric_mean"}),
            },
        )
        with Operations.context(MigrationContext.configure(sync_conn)):
            m098.upgrade()
        return sync_conn.execute(
            text("select query->>'aggregation' from saved_searches where id = :id"), {"id": sid}
        ).scalar_one()

    async with session_factory() as s:
        value = await s.run_sync(lambda sync: run(sync.connection()))
        await s.rollback()
    assert value == "geometric_mean"
