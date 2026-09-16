"""API tests: campaign libraries (link/unlink, coverage, gap).

The HTTP contract only — idempotency, the 404s, the closed-campaign refusal,
the coverage shape, the gap list, and the FK that keeps a linked library
undeletable. The coverage *math* over seed runs (covered > 0, the union across
several runs, the gap shrinking as readouts land) is exercised against the read
model in ``tests/integration/persistence/screening/test_coverage_query.py`` —
seeding readout_data through the API harness is intentionally avoided here.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.api.test_campaigns_api import (
    ASPIRIN_SMILES,
    CAFFEINE_SMILES,
    _create_empty_campaign,
    _create_project,
    _register_molecule,
    _seed_closeable_campaign,
)

pytestmark = pytest.mark.asyncio


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
    return coll_id


async def _draft_campaign(client: AsyncClient, name: str) -> str:
    project_id = await _create_project(client, name=f"{name} Project")
    campaign = await _create_empty_campaign(client, project_id, name=name)
    return campaign["id"]


class TestCampaignCollectionLink:
    async def test_link_is_idempotent_and_shows_in_coverage(self, client: AsyncClient) -> None:
        m1 = await _register_molecule(client, ASPIRIN_SMILES, "Lib-A")
        m2 = await _register_molecule(client, CAFFEINE_SMILES, "Lib-B")
        coll = await _make_collection(client, [m1, m2], name="CampaignLib")
        campaign_id = await _draft_campaign(client, "Linkable")

        first = await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        assert first.status_code == 204, first.text

        # Identical re-link is idempotent → 204 again, still one entry.
        second = await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        assert second.status_code == 204, second.text

        resp = await client.get(f"/api/v1/campaigns/{campaign_id}/collection-coverage")
        assert resp.status_code == 200, resp.text
        entries = resp.json()
        assert len(entries) == 1
        cov = entries[0]
        assert cov["id"] == coll
        assert cov["name"] == "CampaignLib"
        assert "type" in cov
        # The campaign has no seed runs, so nothing was screened *in it*.
        assert cov["total"] == 2
        assert cov["covered"] == 0
        assert cov["fraction"] == 0.0

    async def test_unlink(self, client: AsyncClient) -> None:
        m1 = await _register_molecule(client, ASPIRIN_SMILES, "Unlink-A")
        coll = await _make_collection(client, [m1], name="UnlinkableLib")
        campaign_id = await _draft_campaign(client, "Unlinkable")

        assert (
            await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        ).status_code == 204
        rm = await client.delete(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        assert rm.status_code == 204, rm.text

        resp = await client.get(f"/api/v1/campaigns/{campaign_id}/collection-coverage")
        assert resp.json() == []

    async def test_link_unknown_collection_404(self, client: AsyncClient) -> None:
        campaign_id = await _draft_campaign(client, "UnknownColl")
        resp = await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{uuid.uuid4()}")
        assert resp.status_code == 404, resp.text

    async def test_link_unknown_campaign_404(self, client: AsyncClient) -> None:
        m1 = await _register_molecule(client, ASPIRIN_SMILES, "NoCampaign-A")
        coll = await _make_collection(client, [m1], name="OrphanLib")
        resp = await client.post(f"/api/v1/campaigns/{uuid.uuid4()}/collections/{coll}")
        assert resp.status_code == 404, resp.text

    async def test_link_on_closed_campaign_409(self, client: AsyncClient) -> None:
        project_id = await _create_project(client, name="ClosedLink Project")
        mol_id = await _register_molecule(client, ASPIRIN_SMILES, "ClosedLink-A")
        campaign_id = await _seed_closeable_campaign(client, project_id, mol_id)
        coll = await _make_collection(client, [mol_id], name="TooLateLib")

        closed = await client.post(f"/api/v1/campaigns/{campaign_id}/close", json={})
        assert closed.status_code == 200, closed.text

        resp = await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        assert resp.status_code == 409, resp.text
        # Coverage stays readable on a closed campaign — only edits are refused.
        assert (
            await client.get(f"/api/v1/campaigns/{campaign_id}/collection-coverage")
        ).status_code == 200

    async def test_linked_collection_cannot_be_deleted(self, client: AsyncClient) -> None:
        m1 = await _register_molecule(client, ASPIRIN_SMILES, "Undeletable-A")
        coll = await _make_collection(client, [m1], name="PinnedLib")
        campaign_id = await _draft_campaign(client, "Pinner")
        assert (
            await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        ).status_code == 204

        # FK RESTRICT — the campaign still points at it.
        resp = await client.delete(f"/api/v1/collections/{coll}")
        assert resp.status_code == 409, resp.text

        # Unlink, and the delete goes through.
        await client.delete(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        assert (await client.delete(f"/api/v1/collections/{coll}")).status_code in (200, 204)


class TestCampaignCollectionCoverage:
    async def test_coverage_of_unknown_campaign_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/campaigns/{uuid.uuid4()}/collection-coverage")
        assert resp.status_code == 404, resp.text

    async def test_coverage_is_empty_without_links(self, client: AsyncClient) -> None:
        campaign_id = await _draft_campaign(client, "NoLibraries")
        resp = await client.get(f"/api/v1/campaigns/{campaign_id}/collection-coverage")
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    async def test_empty_collection_reports_null_fraction(self, client: AsyncClient) -> None:
        coll = await _make_collection(client, [], name="EmptyLib")
        campaign_id = await _draft_campaign(client, "EmptyLibHolder")
        assert (
            await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        ).status_code == 204

        cov = (await client.get(f"/api/v1/campaigns/{campaign_id}/collection-coverage")).json()[0]
        assert cov["total"] == 0
        assert cov["fraction"] is None


class TestCampaignCollectionGap:
    async def test_gap_is_full_membership_without_seed_runs(self, client: AsyncClient) -> None:
        m1 = await _register_molecule(client, ASPIRIN_SMILES, "CGap-A")
        m2 = await _register_molecule(client, CAFFEINE_SMILES, "CGap-B")
        coll = await _make_collection(client, [m1, m2], name="CampaignGapLib")
        campaign_id = await _draft_campaign(client, "Gapped")
        assert (
            await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")
        ).status_code == 204

        gap = await client.get(f"/api/v1/campaigns/{campaign_id}/collections/{coll}/gap")
        assert gap.status_code == 200, gap.text
        # No seed runs → nothing was read → the gap is the whole library.
        assert set(gap.json()) == {m1, m2}

    async def test_gap_of_unknown_campaign_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/campaigns/{uuid.uuid4()}/collections/{uuid.uuid4()}/gap")
        assert resp.status_code == 404, resp.text

    async def test_gap_limit_is_capped(self, client: AsyncClient) -> None:
        campaign_id = await _draft_campaign(client, "GapLimit")
        resp = await client.get(
            f"/api/v1/campaigns/{campaign_id}/collections/{uuid.uuid4()}/gap",
            params={"limit": 501},
        )
        assert resp.status_code == 422, resp.text


class TestCampaignCollectionStageCounts:
    """?include=stages — the campaign's funnel, counted per library."""

    async def _campaign_with_two_rows(self, client: AsyncClient) -> tuple[str, str, str]:
        """A draft campaign with two result rows. Returns (campaign_id, mol_a, mol_b)."""
        project_id = await _create_project(client, name="StageCounts Project")
        mol_a = await _register_molecule(client, ASPIRIN_SMILES, "StageCount-A")
        mol_b = await _register_molecule(client, CAFFEINE_SMILES, "StageCount-B")
        campaign_id = await _seed_closeable_campaign(client, project_id, mol_a)
        added = await client.post(
            f"/api/v1/campaigns/{campaign_id}/results", json={"molecule_id": mol_b}
        )
        assert added.status_code == 204, added.text
        return campaign_id, mol_a, mol_b

    async def _add_manual_stage(self, client: AsyncClient, campaign_id: str) -> str:
        """A manual stage parks every row at `pending` — no measurement values
        needed to prove the per-library split."""
        resp = await client.post(
            f"/api/v1/campaigns/{campaign_id}/stages",
            json={"name": "Triage", "kind": "manual"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["stages"][0]["id"]

    async def test_stages_absent_without_the_flag(self, client: AsyncClient) -> None:
        campaign_id, mol_a, _ = await self._campaign_with_two_rows(client)
        await self._add_manual_stage(client, campaign_id)
        coll = await _make_collection(client, [mol_a], name="FlagOffLib")
        await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")

        entry = (await client.get(f"/api/v1/campaigns/{campaign_id}/collection-coverage")).json()[
            0
        ]
        assert entry["stages"] is None

    async def test_counts_only_the_rows_in_that_library(self, client: AsyncClient) -> None:
        campaign_id, mol_a, _ = await self._campaign_with_two_rows(client)
        stage_id = await self._add_manual_stage(client, campaign_id)
        # The library holds one of the campaign's two compounds.
        coll = await _make_collection(client, [mol_a], name="HalfTheCampaign")
        await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")

        resp = await client.get(
            f"/api/v1/campaigns/{campaign_id}/collection-coverage", params={"include": "stages"}
        )
        assert resp.status_code == 200, resp.text
        entry = resp.json()[0]
        assert [s["stage_id"] for s in entry["stages"]] == [stage_id]
        counts = entry["stages"][0]["counts"]
        assert counts["population"] == 1
        assert counts["pending"] == 1
        # Coverage is untouched by the flag.
        assert entry["total"] == 1
        assert entry["covered"] == 0

        # The campaign's own summary still counts both rows.
        summary = (await client.get(f"/api/v1/campaigns/{campaign_id}")).json()
        assert summary["stages"][0]["counts"]["population"] == 2

    async def test_library_sharing_no_compound_reports_zeros(self, client: AsyncClient) -> None:
        campaign_id, _, _ = await self._campaign_with_two_rows(client)
        await self._add_manual_stage(client, campaign_id)
        stranger = await _register_molecule(client, "CCCCCCCCCCCC", "StageCount-Stranger")
        coll = await _make_collection(client, [stranger], name="NoOverlapLib")
        await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")

        entry = (
            await client.get(
                f"/api/v1/campaigns/{campaign_id}/collection-coverage",
                params={"include": "stages"},
            )
        ).json()[0]
        assert entry["stages"][0]["counts"]["population"] == 0
        assert entry["stages"][0]["counts"]["pending"] == 0

    async def test_campaign_without_stages_reports_empty_list(self, client: AsyncClient) -> None:
        campaign_id, mol_a, _ = await self._campaign_with_two_rows(client)
        coll = await _make_collection(client, [mol_a], name="StagelessLib")
        await client.post(f"/api/v1/campaigns/{campaign_id}/collections/{coll}")

        entry = (
            await client.get(
                f"/api/v1/campaigns/{campaign_id}/collection-coverage",
                params={"include": "stages"},
            )
        ).json()[0]
        # [] (no stages) is not None (not asked for).
        assert entry["stages"] == []

    async def test_unknown_include_value_is_rejected(self, client: AsyncClient) -> None:
        campaign_id, _, _ = await self._campaign_with_two_rows(client)
        resp = await client.get(
            f"/api/v1/campaigns/{campaign_id}/collection-coverage", params={"include": "wat"}
        )
        assert resp.status_code == 422, resp.text
