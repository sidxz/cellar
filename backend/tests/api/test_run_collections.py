"""API tests: run & protocol collection coverage (attach/detach, coverage, gap).

These cover the HTTP contract — attach/detach idempotency, 404s, the
``collections`` field shape on run responses, the protocol rollup, and the
gap list (== full membership when no readouts exist). The coverage *math*
(covered > 0, fractional coverage, gap shrinking as wells land) is exercised
end-to-end against the read model in
``tests/integration/persistence/screening/test_coverage_query.py`` — seeding
readout_data through the API harness is intentionally avoided here.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _make_org(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/organizations", json={"name": "CoverageOrg", "org_type": "internal"}
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _make_molecule(client: AsyncClient, org_id: str, *, name: str, smiles: str) -> str:
    resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": name,
            "smiles": smiles,
            "molecule_type": "small_molecule",
            "originating_org_id": org_id,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["molecule"]["id"]


async def _make_collection(client: AsyncClient, molecule_ids: list[str], *, name: str) -> str:
    created = await client.post("/api/v1/collections", json={"name": name})
    assert created.status_code == 201, created.text
    coll_id = created.json()["id"]
    if molecule_ids:
        added = await client.post(
            f"/api/v1/collections/{coll_id}/molecules",
            json={"references": [{"value": m, "ref_type": "uuid"} for m in molecule_ids]},
        )
        assert added.status_code in (200, 201), added.text
        assert added.json()["added_count"] == len(molecule_ids)
    return coll_id


async def _make_protocol(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/protocols",
        json={
            "name": "CoverageProto",
            "protocol_type": "biochemical",
            "readout_definitions": [{"name": "IC50", "data_type": "numeric", "display_order": 0}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _publish(client: AsyncClient, protocol_id: str) -> None:
    resp = await client.post(f"/api/v1/protocols/{protocol_id}/publish")
    assert resp.status_code in (200, 201), resp.text


async def _make_run(client: AsyncClient, protocol_id: str, **extra) -> str:
    body = {"protocol_id": protocol_id, "run_date": "2026-06-07", **extra}
    resp = await client.post("/api/v1/runs", json=body)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


class TestRunCollectionAttach:
    async def test_attach_is_idempotent_and_shows_in_run_response(
        self, client: AsyncClient
    ) -> None:
        org = await _make_org(client)
        m1 = await _make_molecule(client, org, name="Mol-A", smiles="CCO")
        m2 = await _make_molecule(client, org, name="Mol-B", smiles="CCN")
        coll = await _make_collection(client, [m1, m2], name="CovList")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid)

        # First attach → 204.
        first = await client.post(f"/api/v1/runs/{rid}/collections/{coll}")
        assert first.status_code == 204, first.text

        # Identical re-attach is idempotent → 204 again.
        second = await client.post(f"/api/v1/runs/{rid}/collections/{coll}")
        assert second.status_code == 204, second.text

        # Run detail carries the collection with the coverage shape. No
        # readouts were seeded, so covered == 0 and fraction == 0.0 (total > 0).
        run = await client.get(f"/api/v1/runs/{rid}")
        assert run.status_code == 200, run.text
        by_id = {c["id"]: c for c in run.json()["collections"]}
        assert coll in by_id
        cov = by_id[coll]
        assert cov["total"] == 2
        assert cov["covered"] == 0
        assert cov["fraction"] == 0.0
        assert cov["name"] == "CovList"
        assert "type" in cov

    async def test_create_run_with_collection_ids(self, client: AsyncClient) -> None:
        org = await _make_org(client)
        m1 = await _make_molecule(client, org, name="Mol-C", smiles="CCC")
        coll = await _make_collection(client, [m1], name="SeedAtCreate")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid, collection_ids=[coll])

        run = await client.get(f"/api/v1/runs/{rid}")
        assert [c["id"] for c in run.json()["collections"]] == [coll]

    async def test_detach(self, client: AsyncClient) -> None:
        org = await _make_org(client)
        m1 = await _make_molecule(client, org, name="Mol-D", smiles="CCCC")
        coll = await _make_collection(client, [m1], name="Detachable")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid)

        assert (await client.post(f"/api/v1/runs/{rid}/collections/{coll}")).status_code == 204
        rm = await client.delete(f"/api/v1/runs/{rid}/collections/{coll}")
        assert rm.status_code == 204, rm.text

        run = await client.get(f"/api/v1/runs/{rid}")
        assert [c["id"] for c in run.json()["collections"]] == []

    async def test_attach_unknown_collection_404(self, client: AsyncClient) -> None:
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid)
        resp = await client.post(f"/api/v1/runs/{rid}/collections/{uuid.uuid4()}")
        assert resp.status_code == 404, resp.text


class TestRunCollectionGap:
    async def test_gap_is_full_membership_without_readouts(self, client: AsyncClient) -> None:
        org = await _make_org(client)
        m1 = await _make_molecule(client, org, name="Gap-A", smiles="CCCCC")
        m2 = await _make_molecule(client, org, name="Gap-B", smiles="CCCCCC")
        coll = await _make_collection(client, [m1, m2], name="GapList")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid)
        assert (await client.post(f"/api/v1/runs/{rid}/collections/{coll}")).status_code == 204

        gap = await client.get(f"/api/v1/runs/{rid}/collections/{coll}/gap")
        assert gap.status_code == 200, gap.text
        # No readouts → every member is unscreened → gap == full membership.
        assert set(gap.json()) == {m1, m2}


class TestProtocolCollectionCoverage:
    async def test_rollup_lists_attached_collection_with_run_count(
        self, client: AsyncClient
    ) -> None:
        org = await _make_org(client)
        m1 = await _make_molecule(client, org, name="Roll-A", smiles="CCCCCCC")
        m2 = await _make_molecule(client, org, name="Roll-B", smiles="CCCCCCCC")
        coll = await _make_collection(client, [m1, m2], name="RollupList")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid)
        assert (await client.post(f"/api/v1/runs/{rid}/collections/{coll}")).status_code == 204

        resp = await client.get(f"/api/v1/protocols/{pid}/collection-coverage")
        assert resp.status_code == 200, resp.text
        by_id = {c["id"]: c for c in resp.json()}
        assert coll in by_id
        eff = by_id[coll]
        assert eff["total"] == 2
        assert eff["covered"] == 0
        assert eff["run_count"] == 1

    async def test_coverage_of_unknown_protocol_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/protocols/{uuid.uuid4()}/collection-coverage")
        assert resp.status_code == 404, resp.text

    async def test_protocol_gap_is_full_membership_without_readouts(
        self, client: AsyncClient
    ) -> None:
        org = await _make_org(client)
        m1 = await _make_molecule(client, org, name="PGap-A", smiles="CCCCCCCCC")
        m2 = await _make_molecule(client, org, name="PGap-B", smiles="CCCCCCCCCC")
        coll = await _make_collection(client, [m1, m2], name="ProtoGapList")
        pid = await _make_protocol(client)
        await _publish(client, pid)
        rid = await _make_run(client, pid)
        assert (await client.post(f"/api/v1/runs/{rid}/collections/{coll}")).status_code == 204

        gap = await client.get(f"/api/v1/protocols/{pid}/collections/{coll}/gap")
        assert gap.status_code == 200, gap.text
        assert set(gap.json()) == {m1, m2}
