"""API tests for search execution endpoint."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

# Force ORM model registration so FK resolution works in test DB.
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveClass, CurveType
from cellar.infrastructure.persistence.sqlalchemy.screening_assay import (
    dose_response_curve_repository as _dr_repo_module,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

SQLAlchemyDoseResponseCurveRepository = (
    _dr_repo_module.SQLAlchemyDoseResponseCurveRepository
)


@pytest.fixture
async def org_id(client: AsyncClient) -> str:
    """Create an organization so molecules can reference it."""
    resp = await client.post(
        "/api/v1/organizations",
        json={
            "name": "SearchTestOrg",
            "org_type": "internal",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestExecuteSearch:
    async def test_empty_criteria_returns_all(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Empty criteria should return molecules (no filter)."""
        await client.post(
            "/api/v1/molecules",
            json={"name": "Mol A", "smiles": "C", "originating_org_id": org_id},
        )
        resp = await client.post(
            "/api/v1/search/execute",
            json={"query": {"criteria": [], "logic": "and"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1

    async def test_text_name_contains(
        self, client: AsyncClient, org_id: str
    ) -> None:
        await client.post(
            "/api/v1/molecules",
            json={"name": "SearchTarget", "smiles": "CC", "originating_org_id": org_id},
        )
        await client.post(
            "/api/v1/molecules",
            json={"name": "Other", "smiles": "CCC", "originating_org_id": org_id},
        )
        resp = await client.post(
            "/api/v1/search/execute",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "SearchTarget"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(m["name"] == "SearchTarget" for m in items)
        assert not any(m["name"] == "Other" for m in items)

    async def test_property_mw_between(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Register ethanol (MW ~46) and filter by MW range."""
        await client.post(
            "/api/v1/molecules",
            json={"name": "Ethanol", "smiles": "CCO", "originating_org_id": org_id},
        )
        resp = await client.post(
            "/api/v1/search/execute",
            json={
                "query": {
                    "criteria": [
                        {"type": "property", "field": "molecular_weight", "operator": "between", "min": 40, "max": 50}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(m["name"] == "Ethanol" for m in items)

    async def test_saved_search_execution(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Create saved search, register molecule, execute saved search."""
        await client.post(
            "/api/v1/molecules",
            json={"name": "SavedTarget", "smiles": "CCCC", "originating_org_id": org_id},
        )
        ss = await client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Find SavedTarget",
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "SavedTarget"}
                    ],
                    "logic": "and",
                },
            },
        )
        assert ss.status_code == 201
        ss_id = ss.json()["id"]

        resp = await client.post(
            "/api/v1/search/execute",
            json={"saved_search_id": ss_id},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(m["name"] == "SavedTarget" for m in items)

    async def test_no_query_or_saved_search_422(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/search/execute", json={})
        assert resp.status_code == 422

    async def test_saved_search_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json={"saved_search_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    async def test_pagination(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """Verify cursor pagination works on search results."""
        for i in range(3):
            await client.post(
                "/api/v1/molecules",
                json={"name": f"PageMol{i}", "smiles": f"{'C' * (i + 5)}", "originating_org_id": org_id},
            )
        resp = await client.post(
            "/api/v1/search/execute?limit=2",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "PageMol"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["next_cursor"] is not None

        # Fetch next page
        resp2 = await client.post(
            f"/api/v1/search/execute?limit=2&cursor={data['next_cursor']}",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "PageMol"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) >= 1

    async def test_invalid_field_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/search/execute",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "nonexistent", "operator": "contains", "value": "x"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 422


class TestCountSearch:
    """API tests for /api/v1/search/count -- the lightweight 'Search N compounds'
    preview endpoint. Mirrors the structure validation of /execute but never
    materializes rows, scores similarity, or enriches activity."""

    async def test_inline_text_filter_returns_count(
        self, client: AsyncClient, org_id: str
    ) -> None:
        await client.post(
            "/api/v1/molecules",
            json={"name": "CountTarget", "smiles": "CC", "originating_org_id": org_id},
        )
        await client.post(
            "/api/v1/molecules",
            json={"name": "Other", "smiles": "CCC", "originating_org_id": org_id},
        )
        resp = await client.post(
            "/api/v1/search/count",
            json={
                "query": {
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "CountTarget"}
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_count" in data
        assert data["total_count"] >= 1

    async def test_empty_criteria_counts_all(
        self, client: AsyncClient, org_id: str
    ) -> None:
        await client.post(
            "/api/v1/molecules",
            json={"name": "AnyMol", "smiles": "C", "originating_org_id": org_id},
        )
        resp = await client.post(
            "/api/v1/search/count",
            json={"query": {"criteria": [], "logic": "and"}},
        )
        assert resp.status_code == 200
        assert resp.json()["total_count"] >= 1

    async def test_zero_match_returns_zero(
        self, client: AsyncClient, org_id: str
    ) -> None:
        resp = await client.post(
            "/api/v1/search/count",
            json={
                "query": {
                    "criteria": [
                        {
                            "type": "text",
                            "field": "name",
                            "operator": "equals",
                            "value": "definitely-not-a-real-molecule-name-zzz",
                        }
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0

    async def test_count_matches_execute_total(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """The count endpoint and the execute endpoint must agree on total_count
        for the same query -- otherwise the chemist sees one number on the
        button and a different one on the result panel."""
        for i in range(3):
            await client.post(
                "/api/v1/molecules",
                json={
                    "name": f"ParityMol{i}",
                    "smiles": f"{'C' * (i + 4)}",
                    "originating_org_id": org_id,
                },
            )
        body = {
            "query": {
                "criteria": [
                    {"type": "text", "field": "name", "operator": "contains", "value": "ParityMol"}
                ],
                "logic": "and",
            }
        }

        count_resp = await client.post("/api/v1/search/count", json=body)
        exec_resp = await client.post("/api/v1/search/execute", json=body)

        assert count_resp.status_code == 200
        assert exec_resp.status_code == 200
        assert count_resp.json()["total_count"] == exec_resp.json()["total_count"]

    async def test_no_query_or_saved_search_422(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/search/count", json={})
        assert resp.status_code == 422

    async def test_saved_search_not_found_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/search/count",
            json={"saved_search_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    async def test_invalid_structure_clause_422(self, client: AsyncClient) -> None:
        """Structure-clause validation runs at the route level, same as /execute."""
        resp = await client.post(
            "/api/v1/search/count",
            json={
                "query": {
                    "criteria": [
                        {"type": "structure", "kind": "exact"}  # missing smiles + inchi_key
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Aggregation + per-criterion run_scope wiring tests
#
# These tests exercise the full ExecuteSearch → MoleculeActivityService path:
# we register a molecule via the public API and then directly seed a protocol
# + readout-def + multiple approved runs and their fitted DR curves in the
# DB. The search response's ``activity_data`` should reflect the body's
# ``aggregation`` field and any per-criterion ``run_scope``.
# ---------------------------------------------------------------------------


_SEED_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000002")


async def _seed_multi_run_dr(
    uow: AsyncUnitOfWork,
    *,
    workspace_id: uuid.UUID,
    molecule_id: uuid.UUID,
    run_count: int,
    approved: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """Seed a protocol + DR readout-def + N runs + N curves for one molecule.

    Returns ``(protocol_id, readout_definition_id, run_ids)``. Run dates are
    spaced one day apart starting today and decreasing back in time, so the
    aggregator can resolve "latest" deterministically.
    """
    protocol_id = uuid.uuid4()
    rd_id = uuid.uuid4()
    run_ids: list[uuid.UUID] = []

    async with uow:
        # Protocol
        await uow.session.execute(
            sa.text(
                "INSERT INTO protocols "
                "(id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, "
                "protocol_version, created_by) "
                "VALUES (:id, :ws, :name, 'biochemical', 'active', "
                "false, 'uM', 'high', 1, 1, :user)"
            ),
            {
                "id": protocol_id,
                "ws": workspace_id,
                "name": f"AggTest-{protocol_id.hex[:8]}",
                "user": _SEED_USER_ID,
            },
        )
        # Readout def — minimal numeric so curves can FK to it.
        await uow.session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, is_calculated) "
                "VALUES (:id, :proto, :name, 'numeric', 0, false)"
            ),
            {
                "id": rd_id,
                "proto": protocol_id,
                "name": f"DR-{rd_id.hex[:8]}",
            },
        )

        # N runs, each with a single curve for the molecule.
        status = "approved" if approved else "draft"
        for i in range(run_count):
            run_id = uuid.uuid4()
            run_ids.append(run_id)
            await uow.session.execute(
                sa.text(
                    "INSERT INTO runs "
                    "(id, workspace_id, protocol_id, run_date, operator, "
                    "status, is_locked, version, notes) "
                    "VALUES (:id, :ws, :proto, :run_date, :user, "
                    ":status, false, 1, NULL)"
                ),
                {
                    "id": run_id,
                    "ws": workspace_id,
                    "proto": protocol_id,
                    # Newest first: today, today-1, today-2, ...
                    "run_date": date.today() - timedelta(days=i),
                    "user": _SEED_USER_ID,
                    "status": status,
                },
            )

            curve = DoseResponseCurve(
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                batch_id=uuid.uuid4(),
                protocol_id=protocol_id,
                run_id=run_id,
                readout_definition_id=rd_id,
                curve_type=CurveType.IC50,
                fitted_value=5.0 + i * 0.1,
                hill_slope=1.0,
                top=100.0,
                bottom=0.0,
                r_squared=0.97,
                num_points=8,
                curve_class=CurveClass.FULL,
                raw_data=[],
            )
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            await repo.save(curve)

        await uow.commit()
    return protocol_id, rd_id, run_ids


class TestExecuteSearchAggregationWiring:
    """Verify ExecuteSearchBody.aggregation + per-criterion run_scope thread
    through ExecuteSearchQuery into MoleculeActivityService.enrich_molecules."""

    async def test_aggregation_passes_to_activity_service(
        self,
        client: AsyncClient,
        org_id: str,
        uow: AsyncUnitOfWork,
        workspace_id: uuid.UUID,
    ) -> None:
        """Setting aggregation=geometric_mean in the body changes selection_rule
        on the response and run_count surfaces the number of seeded runs."""
        # Register molecule via the public API so the search composer can find it.
        resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "AggMol",
                "smiles": "CCN",
                "originating_org_id": org_id,
            },
        )
        assert resp.status_code == 201
        mol_id = uuid.UUID(resp.json()["molecule"]["id"])

        _proto_id, rd_id, _run_ids = await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=mol_id, run_count=3
        )

        body = {
            "query": {
                "criteria": [
                    {
                        "type": "text",
                        "field": "name",
                        "operator": "contains",
                        "value": "AggMol",
                    }
                ],
                "logic": "and",
            },
            "protocol_columns": [f"drc:{rd_id}"],
            "aggregation": "geometric_mean",
        }
        res = await client.post("/api/v1/search/execute", json=body)
        assert res.status_code == 200
        data = res.json()
        assert data["activity_data"] is not None
        cell = data["activity_data"][str(mol_id)][f"drc:{rd_id}"]
        assert cell["selection_rule"] == "geometric_mean"
        assert cell["run_count"] == 3

    async def test_default_aggregation_is_latest_approved_run(
        self,
        client: AsyncClient,
        org_id: str,
        uow: AsyncUnitOfWork,
        workspace_id: uuid.UUID,
    ) -> None:
        """A body without ``aggregation`` defaults to LATEST_APPROVED_RUN."""
        resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "DefaultAggMol",
                "smiles": "CCC",
                "originating_org_id": org_id,
            },
        )
        assert resp.status_code == 201
        mol_id = uuid.UUID(resp.json()["molecule"]["id"])

        _proto_id, rd_id, _ = await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=mol_id, run_count=2
        )

        body = {
            "query": {
                "criteria": [
                    {
                        "type": "text",
                        "field": "name",
                        "operator": "contains",
                        "value": "DefaultAggMol",
                    }
                ],
                "logic": "and",
            },
            "protocol_columns": [f"drc:{rd_id}"],
        }
        res = await client.post("/api/v1/search/execute", json=body)
        assert res.status_code == 200
        data = res.json()
        cell = data["activity_data"][str(mol_id)][f"drc:{rd_id}"]
        assert cell["selection_rule"] == "latest_approved_run"

    async def test_per_criterion_run_scope_narrows_aggregation(
        self,
        client: AsyncClient,
        org_id: str,
        uow: AsyncUnitOfWork,
        workspace_id: uuid.UUID,
    ) -> None:
        """``run_scope`` on the activity criterion narrows the cell summary
        to only the in-scope runs, so the aggregator's run_count reflects
        the scope, not the total run set on the protocol.

        We seed 5 approved runs and narrow the criterion's ``run_scope`` to
        two of them. The ``where`` clause uses a permissive ``fitted_value
        > 0`` filter on the dr_curve source so the SQL composer finds the
        molecule (it doesn't index ReadoutData rows in this test), and the
        scope itself is what trims the aggregation to 2 runs.
        """
        resp = await client.post(
            "/api/v1/molecules",
            json={
                "name": "ScopedMol",
                "smiles": "CCCO",
                "originating_org_id": org_id,
            },
        )
        assert resp.status_code == 201
        mol_id = uuid.UUID(resp.json()["molecule"]["id"])

        proto_id, rd_id, run_ids = await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=mol_id, run_count=5
        )
        scoped_run_ids = [str(run_ids[0]), str(run_ids[1])]

        body = {
            "query": {
                "criteria": [
                    {
                        "type": "activity",
                        "protocol_id": str(proto_id),
                        "where": [
                            {
                                "source": "dr_curve",
                                "readout_definition_id": str(rd_id),
                                "operator": "gt",
                                "value": 0,
                            }
                        ],
                        "run_scope": {
                            "mode": "specific",
                            "run_ids": scoped_run_ids,
                        },
                    }
                ],
                "logic": "and",
            },
            "protocol_columns": [f"drc:{rd_id}"],
        }
        res = await client.post("/api/v1/search/execute", json=body)
        assert res.status_code == 200
        data = res.json()
        assert data["activity_data"] is not None
        cell = data["activity_data"][str(mol_id)][f"drc:{rd_id}"]
        assert cell["run_count"] == 2
