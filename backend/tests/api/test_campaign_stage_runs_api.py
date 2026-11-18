"""Stage-owned campaign values through the API (spec §10).

Runs join a stage and read back with it, a column describes itself on every read,
a run leaves a stage, and a column picks the one concentration it reads. Screening
data is seeded with raw SQL (the screening API has no single-step way to write a
reading); everything campaign-side goes through the routes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.research_organization.measurement_facts import TEST_CONCENTRATION
from tests.api._protocols import protocol_body
from tests.integration import _screening_seed as seed

PI = "percent_inhibition"


@dataclass(frozen=True)
class Seeded:
    protocol_id: str
    readout_id: str
    run_ids: list[str]
    molecule_id: str
    batch_id: str


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    ws: uuid.UUID,
    readings: list[tuple[str, float]],
) -> Seeded:
    """One compound, one batch; one approved summary run per (Test concentration, value),
    each holding a well-less % inhibition reading that is the mean of 3 replicates."""
    async with session_factory() as s:
        mol = await seed.molecule(
            s, ws, await seed.org(s, ws), "Stage-runs mol", **seed.descriptors(46.07)
        )
        batch = await seed.batch(s, ws, mol, "B1")
        p = await seed.protocol(s, ws, conditions=[(TEST_CONCENTRATION, "numeric", "uM")])
        rd = await seed.readout_def(s, p, name="Signal", normalizations=[PI])
        runs = []
        for i, (conc, value) in enumerate(readings):
            run = await seed.run(
                s,
                ws,
                p,
                date(2026, 1, i + 1),
                status="approved",
                conditions={TEST_CONCENTRATION: conc},
            )
            await seed.readout(
                s, ws, run, rd, mol, value,
                wellless=True, batch_id=batch, normalization=PI, replicate_count=3,
            )  # fmt: skip
            runs.append(str(run))
        await s.commit()
    return Seeded(str(p), str(rd), runs, str(mol), str(batch))


async def _campaign(client: AsyncClient) -> str:
    project = await client.post("/api/v1/projects", json={"name": f"P-{uuid.uuid4().hex[:6]}"})
    assert project.status_code == 201, project.text
    resp = await client.post(
        "/api/v1/campaigns", json={"name": "Stage runs", "project_id": project.json()["id"]}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _stage(client: AsyncClient, campaign_id: str, name: str) -> str:
    resp = await client.post(f"/api/v1/campaigns/{campaign_id}/stages", json={"name": name})
    assert resp.status_code == 200, resp.text
    return next(s["id"] for s in resp.json()["stages"] if s["name"] == name)


def _config(d: Seeded) -> dict:
    return {
        "protocol_id": d.protocol_id,
        "readout_definition_id": d.readout_id,
        "label": "Signal",
        "source_kind": "readout_data",
        "selection_rule": "mean_across_runs",
        "normalization_applied": PI,
    }


async def _add_runs(
    client: AsyncClient, campaign_id: str, d: Seeded, run_ids: list[str], stage_id: str | None
) -> dict:
    body: dict = {"run_ids": run_ids, "channel_configs": [_config(d)], "scope": "all"}
    if stage_id is not None:
        body["stage_id"] = stage_id
    resp = await client.post(f"/api/v1/campaigns/{campaign_id}/add-from-runs", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _read(client: AsyncClient, campaign_id: str) -> dict:
    resp = await client.get(f"/api/v1/campaigns/{campaign_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _cell(campaign: dict) -> dict:
    [result] = campaign["results"]
    [cell] = result["measurements"]
    return cell


async def test_add_from_runs_with_stage_id_reads_back_stage_ids(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    d = await _seed(session_factory, workspace_id, [("10 µM", 40.0), ("10 µM", 60.0)])
    campaign_id = await _campaign(client)
    stage_id = await _stage(client, campaign_id, "Primary")

    # One run per call, as Daikon adds them: the stage's value is over both runs.
    await _add_runs(client, campaign_id, d, [d.run_ids[0]], stage_id)
    await _add_runs(client, campaign_id, d, [d.run_ids[1]], stage_id)

    campaign = await _read(client, campaign_id)
    assert campaign["seed_runs"] == [
        {"run_id": r, "protocol_id": d.protocol_id, "stage_ids": [stage_id]} for r in d.run_ids
    ]
    [channel] = campaign["channels"]
    assert channel["stage_id"] == stage_id
    assert channel["test_concentration"] is None
    cell = _cell(campaign)
    assert cell["value"] == 50.0
    assert set(cell["contributing_run_ids"]) == set(d.run_ids)
    assert cell["replicate_count"] == 6
    assert (cell["test_concentration_value"], cell["test_concentration_unit"]) == (10.0, "µM")
    assert cell["basis"] == "reported"
    assert cell["batch_ids"] == [d.batch_id]
    assert cell["concentration_series"] is False
    assert cell["unresolved_reason"] is None
    assert cell["concentrations_found"] == [{"value": 10.0, "unit": "µM"}]
    # Approved runs, no z′ recorded: the default QC heuristic passes.
    assert cell["qc_pass"] is True


async def test_preview_with_stage_id_shows_the_stage_wide_value(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    d = await _seed(session_factory, workspace_id, [("10 µM", 40.0), ("10 µM", 60.0)])
    campaign_id = await _campaign(client)
    primary = await _stage(client, campaign_id, "Primary")
    retest = await _stage(client, campaign_id, "Retest")
    await _add_runs(client, campaign_id, d, [d.run_ids[0]], primary)

    async def preview_cell(stage_id: str) -> dict:
        resp = await client.post(
            f"/api/v1/campaigns/{campaign_id}/preview-run-import",
            json={
                "run_ids": [d.run_ids[1]],
                "channel_configs": [_config(d)],
                "stage_id": stage_id,
            },
        )
        assert resp.status_code == 200, resp.text
        [row] = resp.json()["rows"]
        [cell] = row["cells"]
        return cell

    # Exactly what the commit would write: the mean over the stage's runs.
    cell = await preview_cell(primary)
    assert cell["value"] == 50.0
    assert cell["qc_pass"] is True
    assert "qc_reason" not in cell
    assert (await preview_cell(retest))["value"] == 60.0


async def test_channel_description_in_summary(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    d = await _seed(session_factory, workspace_id, [("10 µM", 40.0), ("10 µM", 60.0)])
    campaign_id = await _campaign(client)
    stage_id = await _stage(client, campaign_id, "Primary")
    await _add_runs(client, campaign_id, d, d.run_ids, stage_id)

    summary = await client.get(f"/api/v1/campaigns/{campaign_id}/summary")
    assert summary.status_code == 200, summary.text
    [channel] = summary.json()["channels"]
    short = "single concentration 10 µM · mean of 6 replicates · 2 runs · mean across runs"
    assert channel["description"] == {
        "stage_name": "Primary",
        "readout_label": "Signal (% Inhibition)",
        "design": "single_concentration",
        "concentrations": [{"value": 10.0, "unit": "µM", "count": 1}],
        "replicates": {"min": 6, "max": 6, "not_recorded": 0},
        "run_count": 2,
        "rule": "mean across runs",
        "basis": ["reported"],
        "needs_concentration": False,
        "label": f"Primary · Signal (% Inhibition) · {short}",
        "short_label": short,
    }
    assert "needs_concentration" not in channel  # only inside the description

    # The full read and the list carry the same description.
    assert (await _read(client, campaign_id))["channels"][0]["description"] == channel[
        "description"
    ]
    listed = await client.get(
        "/api/v1/campaigns", params={"project_id": summary.json()["project_id"]}
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["channels"][0]["description"] == channel["description"]


async def test_patch_test_concentration(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    d = await _seed(session_factory, workspace_id, [("10 µM", 40.0), ("1 µM", 20.0)])
    campaign_id = await _campaign(client)
    stage_id = await _stage(client, campaign_id, "Primary")
    await _add_runs(client, campaign_id, d, d.run_ids, stage_id)

    campaign = await _read(client, campaign_id)
    [channel] = campaign["channels"]
    assert channel["description"]["needs_concentration"] is True
    assert channel["description"]["concentrations"] == [
        {"value": 1.0, "unit": "µM", "count": 1},
        {"value": 10.0, "unit": "µM", "count": 1},
    ]
    cell = _cell(campaign)
    assert (cell["value"], cell["unresolved_reason"]) == (None, "several_concentrations")
    assert cell["concentrations_found"] == [
        {"value": 1.0, "unit": "µM"},
        {"value": 10.0, "unit": "µM"},
    ]

    url = f"/api/v1/campaigns/{campaign_id}/channels/{channel['id']}"
    resp = await client.patch(url, json={"test_concentration": {"value": 10000, "unit": "nM"}})
    assert resp.status_code == 200, resp.text
    campaign = await _read(client, campaign_id)
    [channel] = campaign["channels"]
    assert channel["test_concentration"] == {"value": 10000.0, "unit": "nM"}
    assert channel["description"]["needs_concentration"] is False
    cell = _cell(campaign)
    assert (cell["value"], cell["unresolved_reason"]) == (40.0, None)
    assert (cell["test_concentration_value"], cell["test_concentration_unit"]) == (10.0, "µM")

    # Clearing it brings the choice back.
    assert (await client.patch(url, json={"test_concentration": None})).status_code == 200
    campaign = await _read(client, campaign_id)
    assert campaign["channels"][0]["test_concentration"] is None
    assert campaign["channels"][0]["description"]["needs_concentration"] is True
    assert _cell(campaign)["unresolved_reason"] == "several_concentrations"

    # Not a concentration: refused at the boundary.
    bad = await client.patch(url, json={"test_concentration": {"value": 10, "unit": "banana"}})
    assert bad.status_code == 422, bad.text


async def test_delete_stage_run_204_and_recompute(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    d = await _seed(session_factory, workspace_id, [("10 µM", 40.0), ("10 µM", 60.0)])
    campaign_id = await _campaign(client)
    stage_id = await _stage(client, campaign_id, "Primary")
    await _add_runs(client, campaign_id, d, d.run_ids, stage_id)
    r1, r2 = d.run_ids

    resp = await client.delete(f"/api/v1/campaigns/{campaign_id}/stages/{stage_id}/runs/{r2}")
    assert resp.status_code == 204, resp.text
    campaign = await _read(client, campaign_id)
    # The run stays in the campaign, as a campaign run; the stage recomputes without it.
    assert campaign["seed_runs"][1] == {
        "run_id": r2,
        "protocol_id": d.protocol_id,
        "stage_ids": [],
    }
    cell = _cell(campaign)
    assert (cell["value"], cell["contributing_run_ids"]) == (40.0, [r1])

    resp = await client.delete(f"/api/v1/campaigns/{campaign_id}/stages/{stage_id}/runs/{r1}")
    assert resp.status_code == 204, resp.text
    cell = _cell(await _read(client, campaign_id))
    assert (cell["value"], cell["unresolved_reason"]) == (None, "no_runs_at_stage")


async def test_delete_run_not_on_stage_204(
    client: AsyncClient,
    viewer_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    d = await _seed(session_factory, workspace_id, [("10 µM", 40.0)])
    campaign_id = await _campaign(client)
    stage_id = await _stage(client, campaign_id, "Primary")
    [run] = d.run_ids
    await _add_runs(client, campaign_id, d, [run], None)  # a campaign run, on no stage
    before = await _read(client, campaign_id)

    base = f"/api/v1/campaigns/{campaign_id}/stages"
    assert (await client.delete(f"{base}/{stage_id}/runs/{run}")).status_code == 204
    assert (await client.delete(f"{base}/{stage_id}/runs/{uuid.uuid4()}")).status_code == 204
    assert await _read(client, campaign_id) == before

    assert (await client.delete(f"{base}/{uuid.uuid4()}/runs/{run}")).status_code == 404
    assert (await viewer_client.delete(f"{base}/{stage_id}/runs/{run}")).status_code == 403


async def test_closed_campaign_stage_run_delete_rejected(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    d = await _seed(session_factory, workspace_id, [("10 µM", 40.0)])
    campaign_id = await _campaign(client)
    stage_id = await _stage(client, campaign_id, "Primary")
    [run] = d.run_ids
    await _add_runs(client, campaign_id, d, [run], stage_id)
    close = await client.post(f"/api/v1/campaigns/{campaign_id}/close", json={})
    assert close.status_code == 200, close.text

    resp = await client.delete(f"/api/v1/campaigns/{campaign_id}/stages/{stage_id}/runs/{run}")
    assert resp.status_code == 423, resp.text
    assert (await _read(client, campaign_id))["seed_runs"][0]["stage_ids"] == [stage_id]


async def test_criterion_other_stage_422(client: AsyncClient) -> None:
    campaign_id = await _campaign(client)
    stage_a = await _stage(client, campaign_id, "A")
    stage_b = await _stage(client, campaign_id, "B")
    protocol = await client.post(
        "/api/v1/protocols",
        json={
            **await _protocol_body(client),
            "readout_definitions": [{"name": "IC50", "data_type": "numeric", "display_order": 0}],
        },
    )
    assert protocol.status_code in (200, 201), protocol.text
    pid, rd = protocol.json()["id"], protocol.json()["readout_definitions"][0]["id"]

    async def add_channel(label: str, stage_id: str | None) -> str:
        body = {
            "label": label,
            "protocol_id": pid,
            "readout_definition_id": rd,
            "source_kind": "readout_data",
            "selection_rule": "latest_run",
            "qualifier_handling": "include_qualified",
            "stage_id": stage_id,
        }
        resp = await client.post(f"/api/v1/campaigns/{campaign_id}/channels", json=body)
        assert resp.status_code == 200, resp.text
        channel = next(c for c in resp.json()["channels"] if c["label"] == label)
        assert channel["stage_id"] == stage_id
        return channel["id"]

    on_a = await add_channel("On A", stage_a)
    campaign_wide = await add_channel("Campaign-wide", None)

    def criteria(channel_id: str) -> list[dict]:
        return [{"channel_id": channel_id, "operator": "lt", "value": 10.0}]

    stages = f"/api/v1/campaigns/{campaign_id}/stages"
    created = await client.post(stages, json={"name": "C", "criteria": criteria(on_a)})
    assert created.status_code == 422, created.text
    for channel_id in (on_a, campaign_wide):
        resp = await client.patch(f"{stages}/{stage_b}", json={"criteria": criteria(channel_id)})
        assert resp.status_code == 422, resp.text
    own = await client.patch(f"{stages}/{stage_a}", json={"criteria": criteria(on_a)})
    assert own.status_code == 200, own.text


async def test_mirror_protocol_with_stage_id_puts_columns_on_the_stage(
    client: AsyncClient,
) -> None:
    campaign_id = await _campaign(client)
    stage_id = await _stage(client, campaign_id, "Primary")
    protocol = await client.post(
        "/api/v1/protocols",
        json={
            **await _protocol_body(client),
            "readout_definitions": [{"name": "IC50", "data_type": "numeric", "display_order": 0}],
        },
    )
    assert protocol.status_code in (200, 201), protocol.text
    resp = await client.post(
        f"/api/v1/campaigns/{campaign_id}/channels/mirror-protocol",
        json={"protocol_id": protocol.json()["id"], "stage_id": stage_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["stage_created"] is False
    assert [c["stage_id"] for c in resp.json()["campaign"]["channels"]] == [stage_id]


async def _protocol_body(client: AsyncClient) -> dict:
    return {**await protocol_body(client), "protocol_type": "biochemical"}
