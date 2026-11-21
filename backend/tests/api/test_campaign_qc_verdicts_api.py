"""PUT /campaigns/{id}/qc-verdicts: a person's QC verdict on many cells, through the API.

The campaign is the managed-campaign test's one-stage, one-column campaign (unmanaged
here), plus a second compound with no reading, so its cell holds no result.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.test_managed_campaigns_api import Managed, _build
from tests.integration import _screening_seed as seed


async def _with_unread_compound(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], ws: uuid.UUID
) -> Managed:
    m = await _build(client, session_factory, ws, managed=False)
    async with session_factory() as s:
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "Unread mol")
        await s.commit()
    added = await client.post(
        f"/api/v1/campaigns/{m.campaign_id}/results", json={"molecule_id": str(mol)}
    )
    assert added.status_code == 204, added.text
    return m


async def test_put_qc_verdicts_returns_counts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    m = await _with_unread_compound(client, session_factory, workspace_id)
    url = f"/api/v1/campaigns/{m.campaign_id}/qc-verdicts"

    verified = await client.put(
        url,
        json={
            "verdict": "verified",
            "targets": [{"channel_ids": [m.channel_id], "result_ids": None}],
            "note": "curve looks clean",
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json() == {"changed": 1, "unchanged": 0, "kept": 0, "no_result": 1}

    campaign = (await client.get(f"/api/v1/campaigns/{m.campaign_id}")).json()
    cells = {r["id"]: r["measurements"][0] for r in campaign["results"]}
    cell = cells.pop(m.result_id)
    assert cell["qc_verdict"] == "verified"
    assert cell["qc_verdict_by"] == str(user_id)
    assert cell["qc_verdict_at"] is not None
    assert cell["qc_verdict_note"] == "curve looks clean"
    assert cell["holds_result"] is True
    [unread] = cells.values()
    assert (unread["qc_verdict"], unread["holds_result"]) == ("not_tested", False)

    # The stage's hits (the measured compound only), failed without overwrite: kept.
    failed = await client.put(
        url,
        json={
            "verdict": "failed",
            "targets": [
                {
                    "channel_ids": [m.channel_id],
                    "where": {"stage_id": m.stage_id, "outcome": ["hit"]},
                }
            ],
        },
    )
    assert failed.status_code == 200, failed.text
    assert failed.json() == {"changed": 0, "unchanged": 0, "kept": 1, "no_result": 0}


async def test_overwrite_without_a_note_key_keeps_the_note(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id, managed=False)
    url = f"/api/v1/campaigns/{m.campaign_id}/qc-verdicts"
    target = {"channel_ids": [m.channel_id], "result_ids": [m.result_id]}

    async def put(**extra: object) -> dict:
        r = await client.put(url, json={"verdict": "verified", "targets": [target], **extra})
        assert r.status_code == 200, r.text
        return r.json()

    async def note() -> str | None:
        campaign = (await client.get(f"/api/v1/campaigns/{m.campaign_id}")).json()
        return campaign["results"][0]["measurements"][0]["qc_verdict_note"]

    assert (await put(note="clean curve"))["changed"] == 1
    assert (await put(overwrite=True))["unchanged"] == 1
    assert await note() == "clean curve"
    assert (await put(overwrite=True, note=None))["changed"] == 1
    assert await note() is None


async def test_both_result_ids_and_where_is_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id, managed=False)
    response = await client.put(
        f"/api/v1/campaigns/{m.campaign_id}/qc-verdicts",
        json={
            "verdict": "verified",
            "targets": [
                {
                    "channel_ids": [m.channel_id],
                    "result_ids": [m.result_id],
                    "where": {"stage_id": m.stage_id},
                }
            ],
        },
    )
    assert response.status_code == 422, response.text


_C, _R = str(uuid.uuid4()), str(uuid.uuid4())


@pytest.mark.parametrize(
    "body",
    [
        # A target names its rows: no selector is not "every row".
        {"verdict": "not_tested", "targets": [{"channel_ids": [_C]}]},
        {"verdict": "verified", "targets": [{"channel_ids": [_C], "where": None}]},
        {
            "verdict": "verified",
            "targets": [{"channel_ids": [_C], "result_ids": None, "where": {}}],
        },
        # Caps: 100 targets, 500 columns per target.
        {"verdict": "verified", "targets": [{"channel_ids": [_C], "result_ids": [_R]}] * 101},
        {
            "verdict": "verified",
            "targets": [
                {"channel_ids": [str(uuid.uuid4()) for _ in range(501)], "result_ids": None}
            ],
        },
    ],
    ids=[
        "no_selector",
        "null_where_alone",
        "null_result_ids_and_where",
        "101_targets",
        "501_columns",
    ],
)
async def test_badly_named_target_is_422(client: AsyncClient, body: dict) -> None:
    # Refused before the campaign is looked up, so an unknown campaign id serves.
    response = await client.put(f"/api/v1/campaigns/{uuid.uuid4()}/qc-verdicts", json=body)
    assert response.status_code == 422, response.text


async def test_note_with_not_tested_is_422_even_when_no_cell_matches(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id, managed=False)
    response = await client.put(
        f"/api/v1/campaigns/{m.campaign_id}/qc-verdicts",
        json={
            "verdict": "not_tested",
            "targets": [
                {
                    "channel_ids": [m.channel_id],
                    "where": {"stage_id": m.stage_id, "outcome": ["pending"]},
                }
            ],
            "note": "bad well",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "ValidationError"


async def test_closed_campaign_is_423(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id, managed=False)
    closed = await client.post(f"/api/v1/campaigns/{m.campaign_id}/close", json={})
    assert closed.status_code == 200, closed.text

    response = await client.put(
        f"/api/v1/campaigns/{m.campaign_id}/qc-verdicts",
        json={
            "verdict": "verified",
            "targets": [{"channel_ids": [m.channel_id], "result_ids": None}],
        },
    )
    assert response.status_code == 423, response.text
    assert response.json()["error"] == "DataLockedError"


async def test_old_filter_value_is_422_on_search(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: uuid.UUID,
) -> None:
    m = await _build(client, session_factory, workspace_id, managed=False)
    response = await client.post(
        f"/api/v1/campaigns/{m.campaign_id}/results/search",
        json={"filters": {"measurements": [{"channel_id": m.channel_id, "qc": "passed"}]}},
    )
    assert response.status_code == 422, response.text
