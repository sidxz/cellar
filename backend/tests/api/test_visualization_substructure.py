"""API: POST /api/v1/visualization/substructure-match."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

URL = "/api/v1/visualization/substructure-match"


async def _seed(session_factory, ws: uuid.UUID) -> dict[str, uuid.UUID]:
    uow = AsyncUnitOfWork(session_factory)
    ids: dict[str, uuid.UUID] = {}
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        for name, smiles in (
            ("toluene", "Cc1ccccc1"),
            ("cyclohexane", "C1CCCCC1"),
            ("blank", None),
        ):
            ids[name] = await seed.molecule(s, ws, org, name)
            await s.execute(
                sa.text("UPDATE molecules SET smiles = :smiles WHERE id = :id"),
                {"smiles": smiles, "id": ids[name]},
            )
        await uow.commit()
    return ids


def _body(ids, query="c1ccccc1", kind="smiles"):
    return {"query": query, "query_kind": kind, "molecule_ids": [str(i) for i in ids.values()]}


async def test_matches_the_given_molecules(client, session_factory, fake_auth):
    ids = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(URL, json=_body(ids))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "matched_ids": [str(ids["toluene"])],
        "searched": 3,
        "without_structure": 1,
    }


async def test_an_unreadable_query_is_422_naming_it(client, session_factory, fake_auth):
    ids = await _seed(session_factory, fake_auth.workspace_id)

    resp = await client.post(URL, json=_body(ids, query="C1CC"))

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"] == "ValidationError"
    assert "C1CC" in resp.json()["message"]


async def test_another_workspaces_molecules_are_not_searched(client, session_factory, fake_auth):
    ids = await _seed(session_factory, uuid.uuid4())  # data lives in another workspace

    resp = await client.post(URL, json=_body(ids))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"matched_ids": [], "searched": 0, "without_structure": 0}
