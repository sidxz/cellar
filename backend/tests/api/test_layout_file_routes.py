"""API tests: reading a labelling layout file, and the registration number on positions."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.test_instrument_import_routes import FILE, LABEL, _count, _import, _seed
from tests.api.test_relabel_positions_routes import _insert_molecule_and_batch
from tests.fakes.fake_auth import FakeAuth


def csv(*lines: str) -> bytes:
    return "\n".join(lines).encode("utf-8")


def _url(run_id: uuid.UUID) -> str:
    return f"/api/v1/runs/{run_id}/resolve-layout-file"


def _layout(body: bytes) -> dict:
    return {"file": ("layout.csv", body, "text/csv")}


async def _scalar(session_factory: async_sessionmaker[AsyncSession], stmt: str, **params):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        return (await session.execute(sa.text(stmt), params)).scalar_one()


async def _registration_number(
    session_factory: async_sessionmaker[AsyncSession], molecule_id: uuid.UUID
) -> str:
    return await _scalar(
        session_factory, "SELECT registration_number FROM molecules WHERE id = :id", id=molecule_id
    )


async def _batch_number(
    session_factory: async_sessionmaker[AsyncSession], batch_id: uuid.UUID
) -> str:
    return await _scalar(
        session_factory, "SELECT batch_number FROM batches WHERE id = :id", id=batch_id
    )


async def test_resolve_layout_file_returns_rows_with_resolved_compound_and_batch(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    body = csv(
        "Position,Label,Role,Compound,Batch,Concentration (µM),Note,Plate",
        f"{LABEL(2)},x,Sample,ABC-0000001,,10,ok,P1",
    )
    resp = await client.post(_url(s.run_id), files=_layout(body))
    assert resp.status_code == 200, resp.text
    out = resp.json()
    (row,) = out["rows"]
    assert (row["position"], row["well_type"], row["dose"], row["problems"]) == (
        LABEL(2),
        "sample",
        10.0,
        [],
    )
    assert (row["label"], row["note"], row["use"]) == ("x", "ok", None)
    assert row["compound"] == {
        "molecule_id": str(s.molecule_id),
        "molecule_name": "Molecule 1",
        "registration_number": await _registration_number(session_factory, s.molecule_id),
        "batch_id": str(s.batch_id),
        "batch_number": await _batch_number(session_factory, s.batch_id),
        "needs_batch_choice": False,
    }
    assert out["unrecognised_columns"] == ["Plate"]


async def test_batch_of_another_compound_is_a_row_problem(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    _, other_batch = await _insert_molecule_and_batch(session_factory, fake_auth.workspace_id)
    other = await _batch_number(session_factory, other_batch)
    body = csv("Position,Label,Compound,Batch", f"{LABEL(2)},x,ABC-0000001,{other}")
    out = (await client.post(_url(s.run_id), files=_layout(body))).json()
    (row,) = out["rows"]
    assert row["compound"] is None and row["label"] == "x"
    assert row["problems"] == [f"Batch '{other}' does not belong to compound 'ABC-0000001'"]


async def test_resolving_writes_nothing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    body = csv("Position,Role,Compound,Concentration", f"{LABEL(1)},Sample,ABC-0000001,1")
    assert (await client.post(_url(s.run_id), files=_layout(body))).status_code == 200
    assert await _count(session_factory, "plates", s.run_id) == 0
    assert await _count(session_factory, "readout_data", s.run_id) == 0
    wells = await _scalar(
        session_factory,
        "SELECT count(*) FROM wells w JOIN plates p ON p.id = w.plate_id WHERE p.run_id = :run",
        run=s.run_id,
    )
    assert wells == 0


async def test_missing_position_column_returns_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    resp = await client.post(_url(s.run_id), files=_layout(csv("Label,Note", "x,y")))
    assert resp.status_code == 422
    assert "The file has no Position column" in resp.text


async def test_oversized_and_overlong_files_return_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    big = await client.post(_url(s.run_id), files=_layout(b"Position\n" + b"x\n" * 11_000_000))
    assert big.status_code == 422 and "larger than 20 MB" in big.text
    long = await client.post(
        _url(s.run_id), files=_layout(csv("Position", *(f"P{n}" for n in range(50_000))))
    )
    assert long.status_code == 422 and "more than 2000 rows" in long.text


async def test_viewer_cannot_resolve(
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    s = await _seed(session_factory, workspace_id)
    resp = await viewer_client.post(_url(s.run_id), files=_layout(csv("Position", LABEL(1))))
    assert resp.status_code == 403


async def test_preview_and_curves_carry_the_registration_number(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    reg = await _registration_number(session_factory, s.molecule_id)
    preview = (await client.post(s.preview_url, files=FILE)).json()
    assert preview["positions"][1]["suggestion"]["registration_number"] == reg
    await _import(client, s)
    curves = (await client.get(f"/api/v1/runs/{s.run_id}/curves")).json()
    assert curves["positions"][1]["registration_number"] == reg
    assert curves["positions"][0]["registration_number"] is None
