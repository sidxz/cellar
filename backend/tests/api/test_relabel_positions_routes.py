"""API tests: editing a run's positions after an instrument import."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.api.test_instrument_import_routes import (
    LABEL,
    _count,
    _import,
    _insert_batch,
    _seed,
)
from tests.fakes.fake_auth import FakeAuth
from tests.fixtures.dose_response_curves import _insert_org


def _url(run_id: uuid.UUID) -> str:
    return f"/api/v1/runs/{run_id}/relabel-positions"


def _values(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": p["label"] or "",
        "note": p["note"] or "",
        "well_type": p["well_type"],
        "batch_id": p["batch_id"],
        "dose": p["dose"],
    }


def edit(position: dict[str, Any], **new: Any) -> dict[str, Any]:
    """One position edit whose ``expected`` is the position as read."""
    expected = _values(position)
    return {"well_id": position["well_id"], "expected": expected, "new": expected | new}


def _bare_body() -> dict[str, Any]:
    """A body naming a position no run has."""
    values = {"label": "", "note": "", "well_type": "sample", "batch_id": None, "dose": None}
    return {"positions": [{"well_id": str(uuid.uuid4()), "expected": values, "new": values}]}


async def _positions(client: AsyncClient, run_id: uuid.UUID) -> list[dict[str, Any]]:
    resp = await client.get(f"/api/v1/runs/{run_id}/curves")
    assert resp.status_code == 200, resp.text
    return resp.json()["positions"]


async def _imported(client: AsyncClient, session_factory, ws: uuid.UUID):  # type: ignore[no-untyped-def]
    s = await _seed(session_factory, ws)
    await _import(client, s)
    return s, await _positions(client, s.run_id)


async def _insert_molecule_and_batch(
    session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    molecule_id, batch_id = uuid.uuid4(), uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_org(uow, uuid.uuid4(), ws)  # a no-op when the workspace has its test org
        org_id = (
            await uow.session.execute(
                sa.text("SELECT id FROM organizations WHERE workspace_id = :ws LIMIT 1"),
                {"ws": ws},
            )
        ).scalar_one()
        await uow.session.execute(
            sa.text(
                "INSERT INTO molecules "
                "(id, workspace_id, name, molecule_type, structure_status, "
                "registration_status, synthesis_status, lifecycle_stage, "
                "registration_number, originating_org_id, version) "
                "VALUES (:id, :ws, 'Molecule 2', 'small_molecule', 'undisclosed', "
                "'approved', 'virtual', 'registered', :reg, :org, 1)"
            ),
            {"id": molecule_id, "ws": ws, "reg": f"REG-{uuid.uuid4().hex[:8]}", "org": org_id},
        )
        await _insert_batch(uow, batch_id, ws, molecule_id)
        await uow.commit()
    return molecule_id, batch_id


async def _sql(session_factory: async_sessionmaker[AsyncSession], stmt: str, **params: Any):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        result = await session.execute(sa.text(stmt), params)
        await session.commit()
        return result


async def test_relabel_label_and_note_then_read_back(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, (p1, _, _) = await _imported(client, session_factory, fake_auth.workspace_id)
    resp = await client.post(
        _url(s.run_id), json={"positions": [edit(p1, label="buffer only", note="bubble")]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "positions_changed": 1,
        "readouts_repointed": 0,
        "recalculated": False,
        "compute_warning": None,
    }
    curves = (await client.get(f"/api/v1/runs/{s.run_id}/curves")).json()
    assert (curves["positions"][0]["label"], curves["positions"][0]["note"]) == (
        "buffer only",
        "bubble",
    )
    assert len(curves["curves"]) == 3
    assert await _count(session_factory, "measured_curves", s.run_id) == 12


async def test_batch_change_moves_readout_rows_to_the_new_compound(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, (_, p2, _) = await _imported(client, session_factory, fake_auth.workspace_id)
    molecule2, batch2 = await _insert_molecule_and_batch(session_factory, fake_auth.workspace_id)

    resp = await client.post(_url(s.run_id), json={"positions": [edit(p2, batch_id=str(batch2))]})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert (out["readouts_repointed"], out["recalculated"], out["compute_warning"]) == (
        1,
        True,
        None,
    )
    rows = (
        await _sql(
            session_factory,
            "SELECT batch_id, molecule_id FROM readout_data "
            "WHERE well_id = :w AND is_computed = false",
            w=p2["well_id"],
        )
    ).all()
    assert [tuple(r) for r in rows] == [(batch2, molecule2)]
    wells = (await client.get(f"/api/v1/runs/{s.run_id}/plate-map")).json()["plates"][0]["wells"]
    assert (wells[1]["batch_id"], wells[1]["molecule_id"]) == (str(batch2), str(molecule2))


async def test_stale_edit_returns_409_and_writes_nothing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, (p1, p2, _) = await _imported(client, session_factory, fake_auth.workspace_id)
    first, second = edit(p2, label="mine"), edit(p2, label="theirs")
    assert (await client.post(_url(s.run_id), json={"positions": [first]})).status_code == 200
    resp = await client.post(_url(s.run_id), json={"positions": [second, edit(p1, note="n")]})
    assert resp.status_code == 409 and LABEL(2) in resp.text
    # Its own error name: the only 409 a reload can help with.
    assert resp.json()["error"] == "StaleEditError"
    positions = await _positions(client, s.run_id)
    assert positions[1]["label"] == "mine" and positions[0]["note"] is None


async def test_completed_run_refuses_role_change_and_requires_a_reason_for_a_label(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, (_, p2, _) = await _imported(client, session_factory, fake_auth.workspace_id)
    await _sql(session_factory, "UPDATE runs SET status = 'completed' WHERE id = :id", id=s.run_id)
    url = _url(s.run_id)
    role = await client.post(url, json={"positions": [edit(p2, well_type="blank")], "reason": "r"})
    assert role.status_code == 409
    assert (await client.post(url, json={"positions": [edit(p2, label="y")]})).status_code == 422
    resp = await client.post(url, json={"positions": [edit(p2, label="y")], "reason": "typo"})
    assert resp.status_code == 200, resp.text
    assert (await _positions(client, s.run_id))[1]["well_type"] == "sample"


async def test_locked_run_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, (_, p2, _) = await _imported(client, session_factory, fake_auth.workspace_id)
    await _sql(
        session_factory,
        "UPDATE runs SET status = 'completed', is_locked = true WHERE id = :id",
        id=s.run_id,
    )
    resp = await client.post(
        _url(s.run_id), json={"positions": [edit(p2, label="y")], "reason": "typo"}
    )
    assert resp.status_code == 409, resp.text
    assert (await _positions(client, s.run_id))[1]["label"] == p2["label"]


async def test_run_without_curves_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    never_imported = await _seed(session_factory, fake_auth.workspace_id)
    resp = await client.post(_url(never_imported.run_id), json=_bare_body())
    assert resp.status_code == 409 and "no measured curves" in resp.text


async def test_batch_from_another_workspace_is_404_and_nothing_written(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, (_, p2, _) = await _imported(client, session_factory, fake_auth.workspace_id)
    _, foreign_batch = await _insert_molecule_and_batch(session_factory, uuid.uuid4())
    resp = await client.post(
        _url(s.run_id),
        json={"positions": [edit(p2, batch_id=str(foreign_batch), label="moved")]},
    )
    assert resp.status_code == 404, resp.text
    after = (await _positions(client, s.run_id))[1]
    assert (after["batch_id"], after["label"]) == (str(s.batch_id), p2["label"])
    assert (
        await _count(session_factory, "readout_data", s.run_id, where=f"batch_id = '{s.batch_id}'")
        == 1
    )


async def test_no_changes_returns_zero_counts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s, (p1, _, _) = await _imported(client, session_factory, fake_auth.workspace_id)
    resp = await client.post(_url(s.run_id), json={"positions": [edit(p1)]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "positions_changed": 0,
        "readouts_repointed": 0,
        "recalculated": False,
        "compute_warning": None,
    }


async def test_viewer_cannot_relabel(
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    s = await _seed(session_factory, workspace_id)
    assert (await viewer_client.post(_url(s.run_id), json=_bare_body())).status_code == 403


async def test_relabel_missing_run_returns_404(client: AsyncClient) -> None:
    assert (await client.post(_url(uuid.uuid4()), json=_bare_body())).status_code == 404


async def test_body_validation_returns_422(client: AsyncClient) -> None:
    body = _bare_body()
    body["positions"][0]["new"] = body["positions"][0]["new"] | {"dose": -1}
    assert (await client.post(_url(uuid.uuid4()), json=body)).status_code == 422
    assert (await client.post(_url(uuid.uuid4()), json={"positions": []})).status_code == 422
    too_many = {"positions": _bare_body()["positions"] * 2001}
    assert (await client.post(_url(uuid.uuid4()), json=too_many)).status_code == 422
