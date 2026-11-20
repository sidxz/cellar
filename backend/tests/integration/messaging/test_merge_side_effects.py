"""Merge side effects re-point a tombstoned molecule's rows onto the surviving molecule."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.infrastructure.messaging.merge_handlers import (
    BatchMergeSideEffect,
    DoseResponseCurveMergeSideEffect,
    MoleculeRelationshipMergeSideEffect,
    ReadoutDataMergeSideEffect,
)
from tests.integration.cascade import _rows


async def _molecules(session: AsyncSession, ws: uuid.UUID, count: int = 2) -> list[uuid.UUID]:
    org = await _rows.org(session, ws)
    return [await _rows.molecule(session, ws, org, reg=f"CC-{i:06d}") for i in range(count)]


async def _molecule_of(session: AsyncSession, table: str, row_id: uuid.UUID) -> uuid.UUID:
    return await session.scalar(
        sa.text(f"SELECT molecule_id FROM {table} WHERE id = :id"), {"id": row_id}
    )


async def _relate(
    session: AsyncSession, ws: uuid.UUID, a: uuid.UUID, b: uuid.UUID, kind: str = "analog_of"
) -> uuid.UUID:
    rel = uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO molecule_relationships (id, workspace_id, source_molecule_id, "
            "target_molecule_id, relationship_type, created_by) "
            "VALUES (:id, :ws, :a, :b, :kind, :user)"
        ),
        {"id": rel, "ws": ws, "a": a, "b": b, "kind": kind, "user": _rows.USER},
    )
    return rel


async def _relationships(session: AsyncSession, ws: uuid.UUID) -> set[tuple]:
    rows = await session.execute(
        sa.text(
            "SELECT source_molecule_id, target_molecule_id, relationship_type "
            "FROM molecule_relationships WHERE workspace_id = :ws"
        ),
        {"ws": ws},
    )
    return {tuple(r) for r in rows}


async def test_batches_move_to_the_target(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    source, target, other = await _molecules(db_session, ws, 3)
    moved = await _rows.batch(db_session, ws, source, number="CC-000000-01")
    kept = await _rows.batch(db_session, ws, other, number="CC-000002-01")

    await BatchMergeSideEffect().on_merge(SimpleNamespace(session=db_session), source, target)

    assert await _molecule_of(db_session, "batches", moved) == target
    assert await _molecule_of(db_session, "batches", kept) == other


async def test_readout_data_moves_to_the_target(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    source, target, other = await _molecules(db_session, ws, 3)
    protocol = await _rows.protocol(db_session, ws)
    readout = await _rows.readout_definition(db_session, protocol)
    run = await _rows.run(db_session, ws, protocol)
    moved = await _rows.readout_data(db_session, ws, run, readout, molecule_id=source)
    kept = await _rows.readout_data(db_session, ws, run, readout, molecule_id=other)

    await ReadoutDataMergeSideEffect().on_merge(
        SimpleNamespace(session=db_session), source, target
    )

    assert await _molecule_of(db_session, "readout_data", moved) == target
    assert await _molecule_of(db_session, "readout_data", kept) == other


async def test_curves_move_to_the_target(db_session: AsyncSession) -> None:
    ws = uuid.uuid4()
    source, target = await _molecules(db_session, ws)
    batch = await _rows.batch(db_session, ws, source)
    protocol = await _rows.protocol(db_session, ws)
    readout = await _rows.readout_definition(db_session, protocol)
    run = await _rows.run(db_session, ws, protocol)
    curve = await _rows.curve(
        db_session,
        ws,
        run_id=run,
        protocol_id=protocol,
        readout_definition_id=readout,
        molecule_id=source,
        batch_id=batch,
    )

    await DoseResponseCurveMergeSideEffect().on_merge(
        SimpleNamespace(session=db_session), source, target
    )

    assert await _molecule_of(db_session, "dose_response_curves", curve) == target


async def test_relationships_are_repointed_without_self_links_or_duplicates(
    db_session: AsyncSession,
) -> None:
    ws = uuid.uuid4()
    source, target, x, y, z = await _molecules(db_session, ws, 5)
    await _relate(db_session, ws, source, target)  # would become target -> target
    await _relate(db_session, ws, target, source, "salt_of")  # would become target -> target
    await _relate(db_session, ws, source, x)  # duplicates target -> x
    await _relate(db_session, ws, target, x)
    await _relate(db_session, ws, y, source)  # duplicates y -> target
    await _relate(db_session, ws, y, target)
    await _relate(db_session, ws, source, z)  # moves to target -> z
    await _relate(db_session, ws, z, source, "prodrug_of")  # moves to z -> target

    other_ws = uuid.uuid4()
    p, q = await _molecules(db_session, other_ws)
    await _relate(db_session, other_ws, p, q)

    await MoleculeRelationshipMergeSideEffect().on_merge(
        SimpleNamespace(session=db_session), source, target
    )

    assert await _relationships(db_session, ws) == {
        (target, x, "analog_of"),
        (y, target, "analog_of"),
        (target, z, "analog_of"),
        (z, target, "prodrug_of"),
    }
    assert await _relationships(db_session, other_ws) == {(p, q, "analog_of")}
