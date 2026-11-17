"""API tests: reading a run's position labels as compound identifiers."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.api.test_instrument_import_routes import _insert_batch, _seed
from tests.api.test_layout_file_routes import _batch_number, _registration_number
from tests.api.test_relabel_positions_routes import _insert_molecule_and_batch
from tests.fakes.fake_auth import FakeAuth


def _url(run_id: uuid.UUID) -> str:
    return f"/api/v1/runs/{run_id}/resolve-position-labels"


async def test_labels_resolve_by_identifier_or_registration_number_with_the_only_batch(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    reg = await _registration_number(session_factory, s.molecule_id)
    resp = await client.post(_url(s.run_id), json={"labels": ["ABC-0000001", "DMSO", reg]})
    assert resp.status_code == 200, resp.text
    compound = {
        "molecule_id": str(s.molecule_id),
        "molecule_name": "Molecule 1",
        "registration_number": reg,
        "batch_id": str(s.batch_id),
        "batch_number": await _batch_number(session_factory, s.batch_id),
        "needs_batch_choice": False,
    }
    assert resp.json() == {
        "matches": [
            {"label": "ABC-0000001", "compound": compound},
            {"label": "DMSO", "compound": None},
            {"label": reg, "compound": compound},
        ]
    }


async def test_compound_with_several_batches_needs_a_batch_choice(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_batch(uow, uuid.uuid4(), fake_auth.workspace_id, s.molecule_id)
        await uow.commit()
    resp = await client.post(_url(s.run_id), json={"labels": ["ABC-0000001", "ABC-0000001"]})
    assert resp.status_code == 200, resp.text
    (match,) = resp.json()["matches"]
    assert match["compound"]["molecule_id"] == str(s.molecule_id)
    assert (
        match["compound"]["batch_id"],
        match["compound"]["batch_number"],
        match["compound"]["needs_batch_choice"],
    ) == (None, None, True)


async def test_viewer_cannot_resolve(
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    s = await _seed(session_factory, workspace_id)
    resp = await viewer_client.post(_url(s.run_id), json={"labels": ["ABC-0000001"]})
    assert resp.status_code == 403


async def test_another_workspaces_run_is_not_found_and_its_compounds_do_not_match(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    other_ws = uuid.uuid4()
    foreign = await _seed(session_factory, other_ws)
    resp = await client.post(_url(foreign.run_id), json={"labels": ["ABC-0000001"]})
    assert resp.status_code == 404

    s = await _seed(session_factory, fake_auth.workspace_id)
    foreign_molecule, _ = await _insert_molecule_and_batch(session_factory, other_ws)
    foreign_reg = await _registration_number(session_factory, foreign_molecule)
    resp = await client.post(_url(s.run_id), json={"labels": [foreign_reg]})
    assert resp.json() == {"matches": [{"label": foreign_reg, "compound": None}]}


async def test_too_many_empty_or_overlong_labels_return_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    at_cap = await client.post(_url(s.run_id), json={"labels": ["DMSO"] * 500})
    assert at_cap.status_code == 200, at_cap.text
    for labels in (["DMSO"] * 501, [], ["x" * 201]):
        resp = await client.post(_url(s.run_id), json={"labels": labels})
        assert resp.status_code == 422, resp.text
