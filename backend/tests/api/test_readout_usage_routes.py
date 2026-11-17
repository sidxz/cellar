"""API tests: a published protocol's unused readout can be renamed, changed or removed."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.screening_assay.protocol import ReadoutUsage
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_usage_reader import (
    SQLAlchemyReadoutUsageReader,
)
from tests.fakes.fake_auth import FakeAuth
from tests.integration import _screening_seed as seed


@dataclass
class _Seeded:
    protocol_id: uuid.UUID
    used: uuid.UUID  # "Signal": has values in one run
    unused: uuid.UUID  # "Sginal": the readout that should never have been

    @property
    def url(self) -> str:
        return f"/api/v1/protocols/{self.protocol_id}"

    def readout_url(self, rd: uuid.UUID) -> str:
        return f"{self.url}/readout-definitions/{rd}"


async def _published(
    session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID, *, locked: bool = False
) -> _Seeded:
    async with session_factory() as s, s.begin():
        pid = await seed.protocol(s, ws)
        used = await seed.readout_def(s, pid, name="Signal")
        unused = await seed.readout_def(s, pid, name="Sginal")
        run = await seed.run(s, ws, pid, date(2026, 11, 2))
        await seed.readout(s, ws, run, used, uuid.uuid4(), 1.0)
        if locked:
            await s.execute(
                sa.text(
                    "UPDATE protocols SET is_locked = true, lock_reason = 'review' WHERE id = :id"
                ),
                {"id": pid},
            )
    return _Seeded(pid, used, unused)


async def _names(client: AsyncClient, p: _Seeded) -> list[str]:
    got = (await client.get(p.url)).json()
    return sorted(rd["name"] for rd in got["readout_definitions"])


async def test_usage_names_what_uses_each_readout(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth: FakeAuth
) -> None:
    p = await _published(session_factory, fake_auth.workspace_id)
    resp = await client.get(f"{p.url}/readout-usage")
    assert resp.status_code == 200, resp.text
    assert {row["readout_definition_id"]: row for row in resp.json()} == {
        str(p.used): {
            "readout_definition_id": str(p.used),
            "in_use": True,
            "reasons": ["has values in 1 run"],
        },
        str(p.unused): {"readout_definition_id": str(p.unused), "in_use": False, "reasons": []},
    }


async def test_a_viewer_may_read_usage(
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
) -> None:
    p = await _published(session_factory, fake_auth.workspace_id)
    resp = await viewer_client.get(f"{p.url}/readout-usage")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2


async def test_usage_of_another_workspaces_protocol_is_404(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    p = await _published(session_factory, uuid.uuid4())
    resp = await client.get(f"{p.url}/readout-usage")
    assert resp.status_code == 404, resp.text


async def test_remove_an_unused_readout_of_a_published_protocol(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth: FakeAuth
) -> None:
    p = await _published(session_factory, fake_auth.workspace_id)
    resp = await client.delete(p.readout_url(p.unused))
    assert resp.status_code == 200, resp.text
    assert await _names(client, p) == ["Signal"]


async def test_remove_a_used_readout_is_a_conflict_that_says_why(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth: FakeAuth
) -> None:
    p = await _published(session_factory, fake_auth.workspace_id)
    resp = await client.delete(p.readout_url(p.used))
    assert resp.status_code == 409, resp.text
    message = resp.json()["message"]
    assert "create a new version" in message
    assert "has values in 1 run" in message
    assert await _names(client, p) == ["Sginal", "Signal"]


async def test_rename_and_restructure_an_unused_readout_of_a_published_protocol(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth: FakeAuth
) -> None:
    p = await _published(session_factory, fake_auth.workspace_id)
    resp = await client.put(
        p.readout_url(p.unused), json={"name": "Background", "aggregation": "median"}
    )
    assert resp.status_code == 200, resp.text
    changed = next(rd for rd in resp.json()["readout_definitions"] if rd["id"] == str(p.unused))
    assert (changed["name"], changed["aggregation"]) == ("Background", "median")
    assert await _names(client, p) == ["Background", "Signal"]


async def test_rename_a_used_readout_is_a_conflict_that_says_why(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth: FakeAuth
) -> None:
    p = await _published(session_factory, fake_auth.workspace_id)
    resp = await client.put(p.readout_url(p.used), json={"name": "Response"})
    assert resp.status_code == 409, resp.text
    message = resp.json()["message"]
    assert "create a new version" in message
    assert "has values in 1 run" in message
    # Cosmetic fields stay editable.
    resp = await client.put(p.readout_url(p.used), json={"precision": 2})
    assert resp.status_code == 200, resp.text
    assert await _names(client, p) == ["Sginal", "Signal"]


async def test_a_readout_another_readout_is_calculated_from_is_in_use(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth: FakeAuth
) -> None:
    p = await _published(session_factory, fake_auth.workspace_id)
    added = await client.post(
        f"{p.url}/readout-definitions",
        json={
            "name": "Half",
            "data_type": "numeric",
            "is_calculated": True,
            "calculation_formula": "Sginal / 2",
        },
    )
    assert added.status_code == 201, added.text
    resp = await client.delete(p.readout_url(p.unused))
    assert resp.status_code == 409, resp.text
    assert "named by the formula of 'Half'" in resp.json()["message"]
    usage = {
        r["readout_definition_id"]: r for r in (await client.get(f"{p.url}/readout-usage")).json()
    }
    assert usage[str(p.unused)]["reasons"] == ["named by the formula of 'Half'"]


async def test_a_locked_protocol_still_refuses(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], fake_auth: FakeAuth
) -> None:
    p = await _published(session_factory, fake_auth.workspace_id, locked=True)
    for resp in (
        await client.delete(p.readout_url(p.unused)),
        await client.put(p.readout_url(p.unused), json={"name": "Background"}),
    ):
        assert resp.status_code == 409, resp.text
        assert "locked" in resp.json()["message"]
    assert await _names(client, p) == ["Sginal", "Signal"]


async def test_a_value_written_after_the_check_ends_as_a_conflict(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    fake_auth: FakeAuth,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The race: the usage check saw nothing, then a value landed before the delete.
    The foreign key refuses, and the answer says the readout is now in use."""
    p = await _published(session_factory, fake_auth.workspace_id)
    real = SQLAlchemyReadoutUsageReader.for_readout
    asked = 0

    async def blind_the_first_time(self: SQLAlchemyReadoutUsageReader, *args: uuid.UUID):
        nonlocal asked
        asked += 1
        return ReadoutUsage() if asked == 1 else await real(self, *args)

    monkeypatch.setattr(SQLAlchemyReadoutUsageReader, "for_readout", blind_the_first_time)
    resp = await client.delete(p.readout_url(p.used))
    assert resp.status_code == 409, resp.text
    assert resp.json() == {
        "error": "ConflictError",
        "message": (
            "This readout is now in use (has values in 1 run), so it can no longer be "
            "removed. Create a new version to change it."
        ),
    }
    monkeypatch.undo()
    assert await _names(client, p) == ["Sginal", "Signal"]
