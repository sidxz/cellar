"""API tests: protocol & run target links (roll-up, auto-prune, lock guard)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _make_target(client: AsyncClient, name: str) -> str:
    resp = await client.post(
        "/api/v1/targets", json={"name": name, "target_type": "single_protein"}
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _make_protocol(client: AsyncClient, *, target_ids: list[str] | None = None) -> str:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": "TargetProto",
            "protocol_type": "biochemical",
            "target_ids": target_ids or [],
            "readout_definitions": [
                {"name": "IC50", "data_type": "numeric", "display_order": 0}
            ],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _publish(client: AsyncClient, protocol_id: str) -> None:
    resp = await client.post(f"/api/v1/protocols/{protocol_id}/publish")
    assert resp.status_code in (200, 201), resp.text


async def _make_run(client: AsyncClient, protocol_id: str, **extra) -> str:
    body = {"protocol_id": protocol_id, "run_date": "2026-06-05", **extra}
    resp = await client.post("/api/v1/runs", json=body)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


class TestProtocolTargets:
    async def test_create_with_direct_targets(self, client: AsyncClient) -> None:
        t3 = await _make_target(client, "Pks13")

        # The 201 body itself must carry the just-linked targets (mutation
        # responses match GET).
        created = await client.post(
            "/api/v1/protocols",
            json={
                "name": "TargetProtoCreate",
                "protocol_type": "biochemical",
                "target_ids": [t3],
                "readout_definitions": [
                    {"name": "IC50", "data_type": "numeric", "display_order": 0}
                ],
            },
        )
        assert created.status_code in (200, 201), created.text
        assert [t["id"] for t in created.json()["targets"]] == [t3]
        pid = created.json()["id"]

        got = await client.get(f"/api/v1/protocols/{pid}")
        assert got.status_code == 200, got.text
        assert [t["id"] for t in got.json()["targets"]] == [t3]

        # State transitions carry targets too.
        published = await client.post(f"/api/v1/protocols/{pid}/publish")
        assert published.status_code in (200, 201), published.text
        assert [t["id"] for t in published.json()["targets"]] == [t3]

        rich = await client.get(f"/api/v1/protocols/{pid}/targets")
        assert rich.status_code == 200, rich.text
        by_id = {t["id"]: t for t in rich.json()}
        assert by_id[t3]["is_direct"] is True
        assert by_id[t3]["run_count"] == 0

    async def test_add_remove_direct_target(self, client: AsyncClient) -> None:
        pid = await _make_protocol(client)
        t1 = await _make_target(client, "NadD")

        add = await client.post(f"/api/v1/protocols/{pid}/targets/{t1}")
        assert add.status_code == 204, add.text
        rich = await client.get(f"/api/v1/protocols/{pid}/targets")
        assert [t["id"] for t in rich.json()] == [t1]

        rm = await client.delete(f"/api/v1/protocols/{pid}/targets/{t1}")
        assert rm.status_code == 204, rm.text
        rich = await client.get(f"/api/v1/protocols/{pid}/targets")
        assert rich.json() == []


class TestRunTargetRollup:
    async def test_run_target_rolls_up_and_auto_prunes(self, client: AsyncClient) -> None:
        t1 = await _make_target(client, "NadD")
        t2 = await _make_target(client, "PptT")
        t3 = await _make_target(client, "Pks13")
        pid = await _make_protocol(client, target_ids=[t3])
        await _publish(client, pid)
        r1 = await _make_run(client, pid)
        r2 = await _make_run(client, pid)

        # Independent run targets roll up to the protocol.
        assert (await client.post(f"/api/v1/runs/{r1}/targets/{t1}")).status_code == 204
        assert (await client.post(f"/api/v1/runs/{r2}/targets/{t2}")).status_code == 204

        rich = {t["id"]: t for t in (await client.get(f"/api/v1/protocols/{pid}/targets")).json()}
        assert set(rich) == {t1, t2, t3}
        assert rich[t1]["is_direct"] is False and rich[t1]["run_count"] == 1
        assert rich[t3]["is_direct"] is True

        # Run detail carries its independent set.
        run1 = await client.get(f"/api/v1/runs/{r1}")
        assert [t["id"] for t in run1.json()["targets"]] == [t1]

        # Run list grid carries targets too.
        listed = await client.get(f"/api/v1/protocols/{pid}/runs")
        by_run = {r["id"]: r for r in listed.json()}
        assert [t["id"] for t in by_run[r2]["targets"]] == [t2]

        # Remove t1 from its only run → auto-pruned from the protocol.
        assert (await client.delete(f"/api/v1/runs/{r1}/targets/{t1}")).status_code == 204
        rich = {t["id"]: t for t in (await client.get(f"/api/v1/protocols/{pid}/targets")).json()}
        assert t1 not in rich
        # Direct target survives.
        assert t3 in rich

    async def test_create_run_with_targets(self, client: AsyncClient) -> None:
        t1 = await _make_target(client, "NadD")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid, target_ids=[t1])

        run = await client.get(f"/api/v1/runs/{rid}")
        assert [t["id"] for t in run.json()["targets"]] == [t1]

        # Run state transitions carry targets in the response body too.
        started = await client.post(f"/api/v1/runs/{rid}/start")
        assert started.status_code in (200, 201), started.text
        assert [t["id"] for t in started.json()["targets"]] == [t1]

    async def test_locked_run_rejects_target_edit(self, client: AsyncClient) -> None:
        t1 = await _make_target(client, "NadD")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid)

        # Drive the run to a lockable state, then lock it.
        assert (await client.post(f"/api/v1/runs/{rid}/start")).status_code in (200, 201)
        assert (await client.post(f"/api/v1/runs/{rid}/complete", json={})).status_code in (
            200,
            201,
        )
        locked = await client.post(
            f"/api/v1/runs/{rid}/lock", json={"reason": "qc freeze"}
        )
        assert locked.status_code in (200, 201), locked.text

        rejected = await client.post(f"/api/v1/runs/{rid}/targets/{t1}")
        assert rejected.status_code == 409, rejected.text


class TestUnknownTarget404:
    """An unknown / cross-workspace target must 404, never silently succeed."""

    async def test_add_unknown_target_to_protocol_404(self, client: AsyncClient) -> None:
        pid = await _make_protocol(client)
        bogus = str(uuid.uuid4())
        resp = await client.post(f"/api/v1/protocols/{pid}/targets/{bogus}")
        assert resp.status_code == 404, resp.text
        # Nothing was attached.
        rich = await client.get(f"/api/v1/protocols/{pid}/targets")
        assert rich.json() == []

    async def test_add_unknown_target_to_run_404(self, client: AsyncClient) -> None:
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid)
        resp = await client.post(f"/api/v1/runs/{rid}/targets/{uuid.uuid4()}")
        assert resp.status_code == 404, resp.text

    async def test_create_protocol_with_unknown_target_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/protocols",
            json={
                "name": "BadTargetProto",
                "protocol_type": "biochemical",
                "target_ids": [str(uuid.uuid4())],
                "readout_definitions": [
                    {"name": "IC50", "data_type": "numeric", "display_order": 0}
                ],
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_create_run_with_unknown_target_404(self, client: AsyncClient) -> None:
        pid = await _make_protocol(client)
        await _publish(client, pid)
        resp = await client.post(
            "/api/v1/runs",
            json={
                "protocol_id": pid,
                "run_date": "2026-06-05",
                "target_ids": [str(uuid.uuid4())],
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_remove_unlinked_target_is_idempotent_204(self, client: AsyncClient) -> None:
        # DELETE of a never-linked (but real) target stays idempotent.
        pid = await _make_protocol(client)
        t1 = await _make_target(client, "NadD")
        resp = await client.delete(f"/api/v1/protocols/{pid}/targets/{t1}")
        assert resp.status_code == 204, resp.text


class TestTargetsOfUnknownProtocol:
    async def test_targets_of_unknown_protocol_404(self, client: AsyncClient) -> None:
        """Foreign/missing protocol must 404 like every sibling GET-by-id,
        not 200 []."""
        resp = await client.get(f"/api/v1/protocols/{uuid.uuid4()}/targets")
        assert resp.status_code == 404, resp.text


class TestDeleteTargetGuard:
    """Deleting an in-use target must 409 — never silently strip links."""

    async def test_delete_in_use_target_409(self, client: AsyncClient) -> None:
        t1 = await _make_target(client, "InUseTarget")
        pid = await _make_protocol(client, target_ids=[t1])

        resp = await client.delete(f"/api/v1/targets/{t1}")
        assert resp.status_code == 409, resp.text
        assert "in use" in resp.json()["message"]

        # Link survives.
        rich = await client.get(f"/api/v1/protocols/{pid}/targets")
        assert [t["id"] for t in rich.json()] == [t1]

        # Unlink, then the delete goes through.
        rm = await client.delete(f"/api/v1/protocols/{pid}/targets/{t1}")
        assert rm.status_code == 204, rm.text
        resp = await client.delete(f"/api/v1/targets/{t1}")
        assert resp.status_code in (200, 204), resp.text

    async def test_delete_run_referenced_target_409(self, client: AsyncClient) -> None:
        t1 = await _make_target(client, "RunRefTarget")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid, target_ids=[t1])

        resp = await client.delete(f"/api/v1/targets/{t1}")
        assert resp.status_code == 409, resp.text

        assert (
            await client.delete(f"/api/v1/runs/{rid}/targets/{t1}")
        ).status_code == 204
        resp = await client.delete(f"/api/v1/targets/{t1}")
        assert resp.status_code in (200, 204), resp.text
