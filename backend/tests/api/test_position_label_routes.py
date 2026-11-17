"""API tests: matching a run's position labels to registered compounds again."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.api.test_instrument_import_routes import FILE, _insert_batch, _seed
from tests.api.test_layout_file_routes import _batch_number, _registration_number
from tests.fakes.fake_auth import FakeAuth


def _url(run_id: uuid.UUID) -> str:
    return f"/api/v1/runs/{run_id}/resolve-position-labels"


async def test_labels_match_as_at_import_whole_or_before_a_bracketed_suffix(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    reg = await _registration_number(session_factory, s.molecule_id)
    labels = ["ABC-0000001", "DMSO", "ABC-0000001 (50 µM)", "DMSO (5%)", reg]
    resp = await client.post(_url(s.run_id), json={"labels": labels})
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
            # Each label comes back as written, matched or not.
            {"label": "ABC-0000001 (50 µM)", "compound": compound},
            {"label": "DMSO (5%)", "compound": None},
            # A registration number is not a registered identifier; the import skips it too.
            {"label": reg, "compound": None},
        ]
    }


async def test_a_label_matches_exactly_when_the_import_preview_suggests_its_compound(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    s = await _seed(session_factory, fake_auth.workspace_id)
    preview = (await client.post(s.preview_url, files=FILE)).json()
    labels = [p["label"] for p in preview["positions"] if p["label"]]
    assert any(p["suggestion"] for p in preview["positions"])
    matches = (await client.post(_url(s.run_id), json={"labels": labels})).json()["matches"]
    matched = {m["label"]: m["compound"] and m["compound"]["batch_id"] for m in matches}
    suggested = {
        p["label"]: p["suggestion"] and p["suggestion"]["batch_id"]
        for p in preview["positions"]
        if p["label"]
    }
    assert matched == suggested


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

    async with session_factory() as session:
        await session.execute(
            sa.text(
                "INSERT INTO molecule_identifiers "
                "(id, molecule_id, workspace_id, identifier, identifier_type, source, "
                "registered_by) VALUES (:id, :mol, :ws, 'XYZ-0000009', 'custom', 'test', :by)"
            ),
            {"id": uuid.uuid4(), "mol": foreign.molecule_id, "ws": other_ws, "by": uuid.uuid4()},
        )
        await session.commit()
    s = await _seed(session_factory, fake_auth.workspace_id)
    resp = await client.post(_url(s.run_id), json={"labels": ["XYZ-0000009", "ABC-0000001"]})
    first, second = resp.json()["matches"]
    assert first == {"label": "XYZ-0000009", "compound": None}
    assert second["compound"]["molecule_id"] == str(s.molecule_id)


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
