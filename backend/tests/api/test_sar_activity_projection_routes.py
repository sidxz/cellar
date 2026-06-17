"""API tests for the activity-projection endpoints + heatmap + rows activity.

Wiring-level: route validation, DI, an inline happy path through HTTP, 404s, and
a seeded heatmap/rows-activity happy path. The argmin/cap/join internals are
covered by the reader integration tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.domain.sar_analysis.activity_projection_types import ActivityScalar
from cellar.domain.sar_analysis.rgroup_decomposition_run import RGroupDecompositionRun
from cellar.domain.sar_analysis.rgroup_types import RGroupAssignment
from cellar.domain.sar_analysis.sar_activity_projection import SarActivityProjection
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.rgroup_decomposition_run_repository import (  # noqa: E501
    SQLAlchemyRGroupDecompositionRunRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.sar_analysis.sar_activity_projection_repository import (  # noqa: E501
    SQLAlchemySarActivityProjectionRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


def _channel(column="drc:" + str(uuid.uuid4())):
    return {"column": column, "source": "dr_curve"}


async def _seed_molecule(session, ws, org, reg):
    mid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, version, originating_org_id) "
            "VALUES (:id, :ws, :r, :r, 'small_molecule', 'Fc1ccccc1', 1, :org)"
        ),
        {"id": mid, "ws": ws, "r": reg, "org": org},
    )
    return mid


async def _seed_heatmap_fixture(api_app, ws):
    """run + 3 assignments (2 in one cell) + projection + 3 values. Returns (run_id, projection_id, potent_id)."""
    sf = api_app.state.container[async_sessionmaker]
    org = uuid.uuid4()
    async with sf() as session:
        await session.execute(
            text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'org-hm', 'internal', true, 1)"
            ),
            {"id": org, "ws": ws},
        )
        potent = await _seed_molecule(session, ws, org, "CV-POTENT")
        weak = await _seed_molecule(session, ws, org, "CV-WEAK")
        other = await _seed_molecule(session, ws, org, "CV-OTHER")
        await session.commit()

    uow = AsyncUnitOfWork(sf)
    async with uow:
        run = RGroupDecompositionRun.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            core_smiles="c1ccccc1", core_hash="ch", now=_NOW,
        )
        run.mark_running(_NOW)
        run.mark_ready(
            rgroup_labels=["R1", "R2"], matched_count=3, unmatched_count=0, total_count=3, now=_NOW
        )
        proj = SarActivityProjection.create(
            workspace_id=ws, requested_by=uuid.uuid4(), membership_hash="m",
            channel_hash="ch", channel_spec={"column": "drc:x"}, now=_NOW,
        )
        proj.mark_running(_NOW)
        proj.mark_ready(value_count=3, now=_NOW)
        await SQLAlchemyRGroupDecompositionRunRepository(uow).save(run)
        await SQLAlchemyRGroupDecompositionRunRepository(uow).write_assignments(run.id, [
            RGroupAssignment(molecule_id=potent, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=weak, rgroups={"R1": "F", "R2": "Cl"}),
            RGroupAssignment(molecule_id=other, rgroups={"R1": "Br", "R2": "Cl"}),
        ])
        pr = SQLAlchemySarActivityProjectionRepository(uow)
        await pr.save(proj)
        await pr.write_values(proj.id, [
            ActivityScalar(molecule_id=potent, scalar=0.1, unit="uM", qualifier=None, source="dose_response", snapshot={"value": 0.1}),
            ActivityScalar(molecule_id=weak, scalar=5.0, unit="uM", qualifier=None, source="dose_response", snapshot={"value": 5.0}),
            ActivityScalar(molecule_id=other, scalar=2.0, unit="uM", qualifier=None, source="dose_response", snapshot={"value": 2.0}),
        ])
        await uow.commit()
    return run.id, proj.id, potent


@pytest.mark.asyncio
async def test_projection_rejects_both_inputs(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/activity-projection",
        json={"molecule_ids": [], "collection_id": str(uuid.uuid4()), "channel": _channel()},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_projection_rejects_empty_column(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/sar/activity-projection",
        json={"molecule_ids": [], "channel": {"column": "  ", "source": "dr_curve"}},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_projection_inline_empty_is_ready(client: AsyncClient) -> None:
    # No molecules -> ready with zero values (exercises HTTP -> DI -> enrich -> persist).
    res = await client.post(
        "/api/v1/sar/activity-projection",
        json={"molecule_ids": [], "channel": _channel()},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["value_count"] == 0
    assert uuid.UUID(body["projection_id"])
    # Poll returns ready.
    poll = await client.get(f"/api/v1/sar/activity-projection/jobs/{body['projection_id']}")
    assert poll.status_code == 200 and poll.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_projection_get_and_cancel_nonexistent_404(client: AsyncClient) -> None:
    assert (await client.get(f"/api/v1/sar/activity-projection/jobs/{uuid.uuid4()}")).status_code == 404
    assert (await client.post(f"/api/v1/sar/activity-projection/jobs/{uuid.uuid4()}/cancel")).status_code == 404


@pytest.mark.asyncio
async def test_heatmap_happy_path(client, api_app, workspace_id) -> None:
    run_id, projection_id, potent = await _seed_heatmap_fixture(api_app, workspace_id)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/heatmap",
        json={"axis_y": "R1", "axis_x": "R2", "projection_id": str(projection_id)},
    )
    assert res.status_code == 200
    body = res.json()
    cells = {(c["y"], c["x"]): c for c in body["cells"]}
    assert cells[("F", "Cl")]["count"] == 2
    assert cells[("F", "Cl")]["best_scalar"] == pytest.approx(0.1)  # argmin
    assert cells[("F", "Cl")]["best_molecule_id"] == str(potent)
    assert body["truncated"] is False
    # Shared color anchor is served so heatmap + table shade against one reference.
    assert body["activity_reference"] is not None


@pytest.mark.asyncio
async def test_heatmap_rejects_unknown_axis(client, api_app, workspace_id) -> None:
    # A stale/bogus axis must 422 — never a silent empty matrix that reads as "no data".
    run_id, projection_id, _potent = await _seed_heatmap_fixture(api_app, workspace_id)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/heatmap",
        json={"axis_y": "R1", "axis_x": "R9", "projection_id": str(projection_id)},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_heatmap_nonexistent_run_404(client: AsyncClient) -> None:
    res = await client.post(
        f"/api/v1/sar/decomposition/{uuid.uuid4()}/heatmap",
        json={"axis_y": "R1", "axis_x": "R2", "projection_id": str(uuid.uuid4())},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_rows_carry_activity_when_projection_given(client, api_app, workspace_id) -> None:
    run_id, projection_id, potent = await _seed_heatmap_fixture(api_app, workspace_id)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows",
        json={"offset": 0, "limit": 50, "projection_id": str(projection_id),
              "sort": [{"col": "activity", "dir": "asc"}]},
    )
    assert res.status_code == 200
    rows = res.json()["rows"]
    assert rows[0]["registration_number"] == "CV-POTENT"  # lowest activity first
    assert rows[0]["activity"] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_rows_rejects_unknown_projection(client, api_app, workspace_id) -> None:
    # Valid run + a projection_id not owned by this workspace -> 404, never a
    # 200 with silently-null activity. Proves /rows validates projection
    # ownership (no cross-tenant activity leak), mirroring the heatmap route.
    run_id, _projection_id, _potent = await _seed_heatmap_fixture(api_app, workspace_id)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows",
        json={"offset": 0, "limit": 50, "projection_id": str(uuid.uuid4())},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_rows_return_snapshot_and_reference(client, api_app, workspace_id) -> None:
    run_id, projection_id, potent = await _seed_heatmap_fixture(api_app, workspace_id)
    res = await client.post(
        f"/api/v1/sar/decomposition/{run_id}/rows",
        json={"offset": 0, "limit": 50, "projection_id": str(projection_id),
              "sort": [{"col": "activity", "dir": "asc"}]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["activity_reference"] == pytest.approx(0.1)  # min across the set
    top = body["rows"][0]
    assert top["registration_number"] == "CV-POTENT"
    assert top["activity_snapshot"] == {"value": 0.1}  # the stored snapshot, per row
