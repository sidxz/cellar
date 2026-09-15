"""Raw-SQL row builders for cascade integration tests.

Each helper inserts the columns its table requires and returns the new id.
Tests pass a fresh workspace id, so their rows never collide.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

USER = uuid.UUID("bbbbbbbb-0000-0000-0000-00000000cafe")
RUN_DATE = date(2026, 9, 15)


async def _insert(session: AsyncSession, sql: str, **params: Any) -> uuid.UUID:
    params.setdefault("id", uuid.uuid4())
    await session.execute(sa.text(sql), params)
    return params["id"]


async def exists(session: AsyncSession, table: str, row_id: uuid.UUID) -> bool:
    count = await session.scalar(
        sa.text(f"SELECT count(*) FROM {table} WHERE id = :id"), {"id": row_id}
    )
    return count == 1


async def org(session: AsyncSession, ws: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
        "VALUES (:id, :ws, 'Org', 'internal', true, 1)",
        ws=ws,
    )


async def protocol(
    session: AsyncSession,
    ws: uuid.UUID,
    *,
    name: str = "Kinase assay",
    parent_protocol_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO protocols (id, workspace_id, name, protocol_type, status, is_locked, "
        "dose_unit, pos_control_signal, version, protocol_version, created_by, "
        "parent_protocol_id) VALUES (:id, :ws, :name, 'biochemical', 'active', false, "
        "'uM', 'high', 1, 1, :user, :parent)",
        ws=ws,
        name=name,
        user=USER,
        parent=parent_protocol_id,
    )


async def readout_definition(session: AsyncSession, protocol_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO readout_definitions (id, protocol_id, name, data_type, aggregation, "
        "display_order) VALUES (:id, :proto, 'IC50', 'numeric', 'none', 0)",
        proto=protocol_id,
    )


async def run(session: AsyncSession, ws: uuid.UUID, protocol_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, status, "
        "is_locked, version) VALUES (:id, :ws, :proto, :d, :user, 'draft', false, 1)",
        ws=ws,
        proto=protocol_id,
        d=RUN_DATE,
        user=USER,
    )


async def plate(session: AsyncSession, run_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO plates (id, run_id, plate_number) VALUES (:id, :run, 1)",
        run=run_id,
    )


async def wells(
    session: AsyncSession, plate_id: uuid.UUID, count: int, *, batch_id: uuid.UUID | None = None
) -> None:
    await session.execute(
        sa.text(
            'INSERT INTO wells (id, plate_id, "row", "column", batch_id) '
            "SELECT gen_random_uuid(), :plate, 'A', g, CAST(:batch AS uuid) "
            "FROM generate_series(1, :n) AS g"
        ),
        {"plate": plate_id, "n": count, "batch": batch_id},
    )


async def readout_data(
    session: AsyncSession,
    ws: uuid.UUID,
    run_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    *,
    molecule_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO readout_data (id, workspace_id, run_id, readout_definition_id, "
        "molecule_id, batch_id, value_numeric) VALUES (:id, :ws, :run, :rd, :mol, :batch, 1.0)",
        ws=ws,
        run=run_id,
        rd=readout_definition_id,
        mol=molecule_id,
        batch=batch_id,
    )


async def curve(
    session: AsyncSession,
    ws: uuid.UUID,
    *,
    run_id: uuid.UUID,
    protocol_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    molecule_id: uuid.UUID,
    batch_id: uuid.UUID,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO dose_response_curves (id, workspace_id, molecule_id, batch_id, "
        "protocol_id, run_id, readout_definition_id, curve_type, fitted_value, hill_slope, "
        "top, bottom, r_squared, num_points) VALUES (:id, :ws, :mol, :batch, :proto, :run, "
        ":rd, 'ic50', 1.0, 1.0, 100.0, 0.0, 0.99, 8)",
        ws=ws,
        mol=molecule_id,
        batch=batch_id,
        proto=protocol_id,
        run=run_id,
        rd=readout_definition_id,
    )


async def molecule(
    session: AsyncSession,
    ws: uuid.UUID,
    org_id: uuid.UUID,
    *,
    reg: str = "CC-000001",
    merged_into_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
        "originating_org_id, merged_into_id, version) "
        "VALUES (:id, :ws, :reg, :reg, 'small_molecule', :org, :merged, 1)",
        ws=ws,
        reg=reg,
        org=org_id,
        merged=merged_into_id,
    )


async def batch(
    session: AsyncSession, ws: uuid.UUID, molecule_id: uuid.UUID, *, number: str = "CC-000001-01"
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, amount_value, "
        "amount_unit, source, chemist, version) "
        "VALUES (:id, :ws, :mol, :num, 1.0, 'mg', 'synthesized', :user, 1)",
        ws=ws,
        mol=molecule_id,
        num=number,
        user=USER,
    )


async def campaign(
    session: AsyncSession,
    ws: uuid.UUID,
    *,
    name: str = "Kinase panel",
    seed_runs: list[tuple[uuid.UUID, uuid.UUID]] | None = None,
) -> uuid.UUID:
    """A draft campaign. Close it with ``set_campaign_status`` after adding rows:
    row-lock triggers reject writes to a closed campaign's results."""
    seeds = [{"run_id": str(r), "protocol_id": str(p)} for r, p in seed_runs or []]
    return await _insert(
        session,
        "INSERT INTO campaign (id, workspace_id, project_id, name, created_by, seed_runs) "
        "VALUES (:id, :ws, :proj, :name, :user, CAST(:seeds AS jsonb))",
        ws=ws,
        proj=uuid.uuid4(),
        name=name,
        user=USER,
        seeds=json.dumps(seeds),
    )


async def set_campaign_status(session: AsyncSession, campaign_id: uuid.UUID, status: str) -> None:
    await session.execute(
        sa.text("UPDATE campaign SET status = :status WHERE id = :id"),
        {"status": status, "id": campaign_id},
    )


async def channel(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    protocol_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO campaign_channel (id, campaign_id, label, protocol_id, "
        "readout_definition_id, source_kind, selection_rule, qualifier_handling) "
        "VALUES (:id, :cid, 'IC50', :proto, :rd, 'readout_data', 'latest_approved_run', "
        "'include_qualified')",
        cid=campaign_id,
        proto=protocol_id,
        rd=readout_definition_id,
    )


async def result(
    session: AsyncSession, campaign_id: uuid.UUID, molecule_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO campaign_result (id, campaign_id, molecule_id) VALUES (:id, :cid, :mol)",
        cid=campaign_id,
        mol=molecule_id,
    )


async def measurement(
    session: AsyncSession,
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    *,
    source_run_id: uuid.UUID | None = None,
    contributing_run_ids: list[uuid.UUID] | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO campaign_measurement (id, result_id, channel_id, value_qualifier, unit, "
        "protocol_name_snapshot, protocol_version_snapshot, source_run_id, "
        "contributing_run_ids) VALUES (:id, :res, :ch, '=', 'uM', 'Kinase assay', 1, :run, "
        "CAST(:contributing AS uuid[]))",
        res=result_id,
        ch=channel_id,
        run=source_run_id,
        contributing=contributing_run_ids,
    )


async def compound_flag(
    session: AsyncSession, ws: uuid.UUID, *, protocol_id: uuid.UUID, molecule_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO compound_flags (id, workspace_id, molecule_id, protocol_id, flagged_by, "
        "flag_type, created_at) VALUES (:id, :ws, :mol, :proto, :user, 'pains', now())",
        ws=ws,
        mol=molecule_id,
        proto=protocol_id,
        user=USER,
    )


async def import_template(
    session: AsyncSession, ws: uuid.UUID, *, default_protocol_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO import_templates (id, workspace_id, name, column_mappings, created_by, "
        "default_protocol_id) VALUES (:id, :ws, 'CRO sheet', CAST('{}' AS jsonb), :user, :proto)",
        ws=ws,
        user=USER,
        proto=default_protocol_id,
    )


async def attachment(
    session: AsyncSession, ws: uuid.UUID, kind: str, owner_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO attachments (id, workspace_id, file_name, mime_type, file_size, "
        "storage_key, attachable_type, attachable_id, uploaded_by, version) "
        "VALUES (:id, :ws, 'plate.csv', 'text/csv', 10, 'files/plate.csv', :kind, :owner, "
        ":user, 1)",
        ws=ws,
        kind=kind,
        owner=owner_id,
        user=USER,
    )


async def sample_request(
    session: AsyncSession,
    ws: uuid.UUID,
    molecule_id: uuid.UUID,
    *,
    status: str,
    batch_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO sample_requests (id, workspace_id, requester_id, molecule_id, batch_id, "
        "requested_amount_value, requested_amount_unit, purpose, priority, status, version) "
        "VALUES (:id, :ws, :user, :mol, :batch, 1.0, 'mg', 'Assay', 'normal', :status, 1)",
        ws=ws,
        user=USER,
        mol=molecule_id,
        batch=batch_id,
        status=status,
    )


async def synthesis_request(
    session: AsyncSession, ws: uuid.UUID, molecule_id: uuid.UUID, *, status: str
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO synthesis_requests (id, workspace_id, requester_id, molecule_id, "
        "requested_amount_value, requested_amount_unit, purpose, priority, status, version) "
        "VALUES (:id, :ws, :user, :mol, 5.0, 'mg', 'Scale-up', 'normal', :status, 1)",
        ws=ws,
        user=USER,
        mol=molecule_id,
        status=status,
    )


async def registered_plate(
    session: AsyncSession, ws: uuid.UUID, *, barcode: str, well_map: dict | None
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO registered_plates (id, workspace_id, barcode, plate_label, format, "
        "plate_type, registered_by, well_map, version) "
        "VALUES (:id, :ws, :bc, :bc, '384', 'compound', :user, CAST(:wm AS jsonb), 1)",
        ws=ws,
        bc=barcode,
        user=USER,
        wm=json.dumps(well_map),
    )


async def cdd_sync(session: AsyncSession, ws: uuid.UUID, molecule_id: uuid.UUID) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO cdd_molecule_sync (id, workspace_id, cdd_vault_id, cdd_molecule_id, "
        "molecule_id, last_synced_at, created_at, updated_at) "
        "VALUES (:id, :ws, 'vault-1', 42, :mol, now(), now(), now())",
        ws=ws,
        mol=molecule_id,
    )


async def synthesis_route(
    session: AsyncSession, ws: uuid.UUID, target_molecule_id: uuid.UUID
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO synthesis_routes (id, workspace_id, target_molecule_id, name, route_type, "
        "status, total_steps, source, created_by, version) "
        "VALUES (:id, :ws, :mol, 'Route A', 'linear', 'draft', 1, 'manual', :user, 1)",
        ws=ws,
        mol=target_molecule_id,
        user=USER,
    )


async def reaction_step(
    session: AsyncSession,
    route_id: uuid.UUID,
    *,
    product_molecule_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO reaction_steps (id, route_id, step_number, product_molecule_id, batch_id) "
        "VALUES (:id, :route, 1, :prod, :batch)",
        route=route_id,
        prod=product_molecule_id,
        batch=batch_id,
    )


async def disclosure_request(
    session: AsyncSession,
    ws: uuid.UUID,
    molecule_id: uuid.UUID,
    *,
    matched_molecule_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO disclosure_requests (id, workspace_id, molecule_id, disclosed_smiles, "
        "requested_by, requested_at, matched_molecule_id, version) "
        "VALUES (:id, :ws, :mol, 'CCO', :user, now(), :matched, 1)",
        ws=ws,
        mol=molecule_id,
        user=USER,
        matched=matched_molecule_id,
    )


async def merge_event(
    session: AsyncSession,
    ws: uuid.UUID,
    *,
    source_molecule_id: uuid.UUID,
    target_molecule_id: uuid.UUID,
    disclosure_request_id: uuid.UUID | None = None,
) -> uuid.UUID:
    return await _insert(
        session,
        "INSERT INTO merge_events (id, workspace_id, source_molecule_id, target_molecule_id, "
        "reason, merged_by, merged_at, snapshot, disclosure_request_id) "
        "VALUES (:id, :ws, :src, :tgt, 'manual_merge', :user, now(), CAST('{}' AS json), :dr)",
        ws=ws,
        src=source_molecule_id,
        tgt=target_molecule_id,
        user=USER,
        dr=disclosure_request_id,
    )
