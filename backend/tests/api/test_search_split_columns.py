"""POST /search/execute — split columns, whole-result-set sorting, paging."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient

# Force ORM model registration so FK resolution works in test DB.
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
from tests.integration import _screening_seed as seed

JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)


async def _execute(client: AsyncClient, body: dict, **params) -> dict:
    resp = await client.post("/api/v1/search/execute", json=body, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _pages(client: AsyncClient, body: dict, **params) -> tuple[list[str], list[dict]]:
    """Every page of a search; returns (ids in order, the page payloads)."""
    ids: list[str] = []
    payloads: list[dict] = []
    cursor = None
    while True:
        extra = {**params, **({"cursor": cursor} if cursor else {})}
        page = await _execute(client, body, **extra)
        payloads.append(page)
        ids += [m["id"] for m in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            return ids, payloads


def _protocol_query(protocol_id, **criterion) -> dict:
    return {
        "logic": "and",
        "criteria": [{"type": "activity", "protocol_id": str(protocol_id), **criterion}],
    }


@pytest.fixture
async def ic50s(session_factory, workspace_id):
    """Protocol with IC50s: a=30, b=5, c=100 (Jan run); d: inactive curve (ND);
    e: in the protocol (readout only, no curve). ATP condition on two runs."""
    async with session_factory() as s:
        o = await seed.org(s, workspace_id)
        mols = {
            n: await seed.molecule(s, workspace_id, o, n, **seed.descriptors(300.0))
            for n in "abcde"
        }
        p = await seed.protocol(s, workspace_id, conditions=[("ATP", "numeric", "uM")])
        rd = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        raw = await seed.readout_def(s, p, name="Signal", unit="RFU")
        jan = await seed.run(s, workspace_id, p, JAN, conditions={"ATP": "10 uM"})
        feb = await seed.run(s, workspace_id, p, FEB, conditions={"ATP": "1 mM"})
        for n, v in (("a", 30.0), ("b", 5.0), ("c", 100.0)):
            await seed.curve(s, workspace_id, p, jan, mols[n], rd, fitted_value=v)
        await seed.curve(s, workspace_id, p, feb, mols["a"], rd, fitted_value=210.0)
        await seed.curve(
            s, workspace_id, p, jan, mols["d"], rd, fitted_value=1.0, curve_class="inactive"
        )
        await seed.readout(s, workspace_id, jan, raw, mols["e"], 1.0)
        await s.commit()
    return {"mols": {k: str(v) for k, v in mols.items()}, "p": p, "rd": rd, "jan": jan, "feb": feb}


# --- splits -----------------------------------------------------------------------------


async def test_split_by_run_returns_groups_and_group_keys(client, ic50s):
    token = f"drc:{ic50s['rd']}"
    body = {
        "query": _protocol_query(
            ic50s["p"],
            run_scope={"mode": "specific", "run_ids": [str(ic50s["feb"]), str(ic50s["jan"])]},
            split={"by": "run"},
        ),
        "protocol_columns": [token],
    }
    data = await _execute(client, body)
    groups = data["column_groups"][str(ic50s["p"])]
    assert groups["split"] == {"by": "run", "condition": None}
    assert [g["key"] for g in groups["groups"]] == [f"run:{ic50s['jan']}", f"run:{ic50s['feb']}"]
    a = data["activity_data"][ic50s["mols"]["a"]]
    assert a[f"{token}@run:{ic50s['jan']}"]["value"] == pytest.approx(30.0)
    assert a[f"{token}@run:{ic50s['feb']}"]["value"] == pytest.approx(210.0)
    assert token not in a


async def test_split_by_condition_groups_are_the_same_on_every_page(client, ic50s):
    token = f"drc:{ic50s['rd']}"
    body = {
        "query": _protocol_query(ic50s["p"], split={"by": "condition", "condition": "ATP"}),
        "protocol_columns": [token],
    }
    _, pages = await _pages(client, body, limit=1)
    assert len(pages) > 1
    first = pages[0]["column_groups"]
    assert all(p["column_groups"] == first for p in pages)
    assert [g["label"] for g in first[str(ic50s["p"])]["groups"]] == ["10 µM", "1 mM"]


@pytest.mark.parametrize(
    "criterion",
    [
        {"split": {"by": "run"}},
        {"split": {"by": "condition", "condition": "Temperature"}},
        {"split": {"by": "condition", "condition": "ATP"}, "run_scope": {"mode": "latest"}},
        {"split": {"by": "plate"}},
    ],
)
async def test_unsupported_splits_are_422(client, ic50s, criterion):
    body = {
        "query": _protocol_query(ic50s["p"], **criterion),
        "protocol_columns": [f"drc:{ic50s['rd']}"],
    }
    resp = await client.post("/api/v1/search/execute", json=body)
    assert resp.status_code == 422, resp.text


async def test_unsplit_search_has_no_column_groups_and_plain_keys(client, ic50s):
    token = f"drc:{ic50s['rd']}"
    data = await _execute(
        client, {"query": _protocol_query(ic50s["p"]), "protocol_columns": [token]}
    )
    assert data["column_groups"] is None
    # Latest run per compound: a's Feb curve (210) is newer than its Jan one.
    assert data["activity_data"][ic50s["mols"]["a"]][token]["value"] == pytest.approx(210.0)


# --- sorting ----------------------------------------------------------------------------


async def test_sort_by_an_activity_column_ranks_the_whole_result_set(client, ic50s):
    token = f"drc:{ic50s['rd']}"
    m = ic50s["mols"]
    body = {"query": _protocol_query(ic50s["p"]), "protocol_columns": [token]}
    asc, _ = await _pages(client, body, limit=2, sort_by=token, sort_dir="asc")
    desc, _ = await _pages(client, body, limit=2, sort_by=token, sort_dir="desc")
    # b=5 < c=100 < a=210 (latest run); d is ND; e has no curve — both last.
    assert asc == [m["b"], m["c"], m["a"], m["d"], m["e"]]
    assert desc == [m["a"], m["c"], m["b"], m["d"], m["e"]]


async def test_sort_by_a_split_group_column(client, ic50s):
    token = f"drc:{ic50s['rd']}"
    m = ic50s["mols"]
    body = {
        "query": _protocol_query(ic50s["p"], split={"by": "condition", "condition": "ATP"}),
        "protocol_columns": [token],
    }
    ids, _ = await _pages(client, body, limit=10, sort_by=f"{token}@cond:10 µM", sort_dir="asc")
    assert ids[:3] == [m["b"], m["a"], m["c"]]


async def test_sort_by_a_molecule_property_pages_correctly(client, session_factory, workspace_id):
    async with session_factory() as s:
        o = await seed.org(s, workspace_id)
        made = [
            await seed.molecule(
                s, workspace_id, o, f"m{v}", logd=float(v), **seed.descriptors(300.0)
            )
            for v in (3, 1, 2)
        ]
        await s.commit()
    body = {"query": {"logic": "and", "criteria": []}}
    ids, _ = await _pages(client, body, limit=1, sort_by="logd", sort_dir="asc")
    assert ids == [str(made[1]), str(made[2]), str(made[0])]


async def test_similarity_search_pages_most_similar_first(client):
    org = (
        await client.post("/api/v1/organizations", json={"name": "SimOrg", "org_type": "internal"})
    ).json()
    for smi in ("c1ccccc1O", "c1ccccc1CO", "c1ccccc1CCO", "c1ccccc1CCCCO"):
        resp = await client.post(
            "/api/v1/molecules", json={"name": smi, "smiles": smi, "originating_org_id": org["id"]}
        )
        assert resp.status_code == 201, resp.text
    body = {
        "query": {
            "logic": "and",
            "criteria": [
                {
                    "type": "structure",
                    "kind": "similarity",
                    "smiles": "c1ccccc1O",
                    "mode": "similar",
                    "threshold": 0.1,
                }
            ],
        }
    }
    whole = await _execute(client, body, limit=50)
    paged, pages = await _pages(client, body, limit=1)
    assert paged == [m["id"] for m in whole["items"]]
    scores = [p["items"][0]["similarity_score"] for p in pages if p["items"]]
    assert scores == sorted(scores, reverse=True)


async def test_a_ranked_cursor_whose_row_is_gone_is_422(client, ic50s):
    token = f"drc:{ic50s['rd']}"
    body = {"query": _protocol_query(ic50s["p"]), "protocol_columns": [token]}
    resp = await client.post(
        "/api/v1/search/execute",
        json=body,
        params={"sort_by": token, "cursor": f"r1:1:{uuid.uuid4()}", "limit": 2},
    )
    assert resp.status_code == 422
    assert "run the search again" in resp.text


async def test_unknown_sort_column_is_422(client, ic50s):
    resp = await client.post(
        "/api/v1/search/execute",
        json={"query": _protocol_query(ic50s["p"])},
        params={"sort_by": "smiles"},
    )
    assert resp.status_code == 422


# --- run filters per protocol (R1) --------------------------------------------------------


async def test_each_protocol_uses_its_own_run_filter(client, session_factory, workspace_id):
    async with session_factory() as s:
        o = await seed.org(s, workspace_id)
        mol = await seed.molecule(s, workspace_id, o, "x", **seed.descriptors(300.0))
        p1 = await seed.protocol(s, workspace_id)
        p2 = await seed.protocol(s, workspace_id)
        rd1 = await seed.readout_def(s, p1, data_type="dose_response")
        rd2 = await seed.readout_def(s, p2, data_type="dose_response")
        p1_old = await seed.run(s, workspace_id, p1, JAN)
        p1_new = await seed.run(s, workspace_id, p1, MAR)
        p2_run = await seed.run(s, workspace_id, p2, FEB)
        await seed.curve(s, workspace_id, p1, p1_old, mol, rd1, fitted_value=1.0)
        await seed.curve(s, workspace_id, p1, p1_new, mol, rd1, fitted_value=2.0)
        await seed.curve(s, workspace_id, p2, p2_run, mol, rd2, fitted_value=7.0)
        await s.commit()
    body = {
        "query": {
            "logic": "and",
            "criteria": [
                {
                    "type": "activity",
                    "protocol_id": str(p1),
                    "run_scope": {"mode": "specific", "run_ids": [str(p1_old)]},
                },
                {"type": "activity", "protocol_id": str(p2), "run_scope": {"mode": "latest"}},
            ],
        },
        "protocol_columns": [f"drc:{rd1}", f"drc:{rd2}"],
    }
    cells = (await _execute(client, body))["activity_data"][str(mol)]
    assert cells[f"drc:{rd1}"]["value"] == pytest.approx(1.0)
    assert cells[f"drc:{rd2}"]["value"] == pytest.approx(7.0)


async def test_a_saved_search_from_before_splits_still_runs(
    client, session_factory, workspace_id, user_id, ic50s
):
    import json

    import sqlalchemy as sa

    sid = uuid.uuid4()
    query = _protocol_query(
        ic50s["p"], run_scope={"mode": "specific", "run_id": str(ic50s["jan"])}
    )
    query["aggregation"] = "latest_run"
    async with session_factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO saved_searches (id, workspace_id, name, query, visibility, created_by, "
                "version) VALUES (:id, :ws, 'old', cast(:q as jsonb), 'private', :u, 1)"
            ),
            {"id": sid, "ws": workspace_id, "q": json.dumps(query), "u": user_id},
        )
        await s.commit()
    token = f"drc:{ic50s['rd']}"
    data = await _execute(client, {"saved_search_id": str(sid), "protocol_columns": [token]})
    assert data["activity_data"][ic50s["mols"]["a"]][token]["value"] == pytest.approx(30.0)
    assert data["column_groups"] is None


async def test_sort_by_an_intercept_ranks_reported_endpoints_by_their_value(
    client, session_factory, workspace_id
):
    async with session_factory() as s:
        o = await seed.org(s, workspace_id)
        fitted = await seed.molecule(s, workspace_id, o, "fitted", **seed.descriptors(300.0))
        reported = await seed.molecule(s, workspace_id, o, "reported", **seed.descriptors(300.0))
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, data_type="dose_response")
        r = await seed.run(s, workspace_id, p, JAN)
        await seed.curve(s, workspace_id, p, r, fitted, rd, fitted_value=50.0)
        await seed.readout(s, workspace_id, r, rd, reported, 2.0, wellless=True)
        await s.commit()
    token = f"drc:{rd}"
    body = {"query": _protocol_query(p), "protocol_columns": [token]}
    ids, _ = await _pages(client, body, sort_by=f"{token}:ic:50.0", sort_dir="asc")
    assert ids == [str(reported), str(fitted)]
