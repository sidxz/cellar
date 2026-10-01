"""API tests for search execution endpoint."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

# Force ORM model registration so FK resolution works in test DB.
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.dose_response_config import (
    InterceptBasis,
    InterceptKind,
    InterceptSpec,
)
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveClass, CurveType
from cellar.infrastructure.persistence.sqlalchemy.screening_assay import (
    dose_response_curve_repository as _dr_repo_module,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

SQLAlchemyDoseResponseCurveRepository = _dr_repo_module.SQLAlchemyDoseResponseCurveRepository


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
    async def test_empty_criteria_returns_all(self, client: AsyncClient, org_id: str) -> None:
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

    async def test_text_name_contains(self, client: AsyncClient, org_id: str) -> None:
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
                        {
                            "type": "text",
                            "field": "name",
                            "operator": "contains",
                            "value": "SearchTarget",
                        }
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(m["name"] == "SearchTarget" for m in items)
        assert not any(m["name"] == "Other" for m in items)

    async def test_property_mw_between(self, client: AsyncClient, org_id: str) -> None:
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
                        {
                            "type": "property",
                            "field": "molecular_weight",
                            "operator": "between",
                            "min": 40,
                            "max": 50,
                        }
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(m["name"] == "Ethanol" for m in items)

    async def test_saved_search_execution(self, client: AsyncClient, org_id: str) -> None:
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
                        {
                            "type": "text",
                            "field": "name",
                            "operator": "contains",
                            "value": "SavedTarget",
                        }
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

    async def test_pagination(self, client: AsyncClient, org_id: str) -> None:
        """Verify cursor pagination works on search results."""
        for i in range(3):
            await client.post(
                "/api/v1/molecules",
                json={
                    "name": f"PageMol{i}",
                    "smiles": f"{'C' * (i + 5)}",
                    "originating_org_id": org_id,
                },
            )
        resp = await client.post(
            "/api/v1/search/execute?limit=2",
            json={
                "query": {
                    "criteria": [
                        {
                            "type": "text",
                            "field": "name",
                            "operator": "contains",
                            "value": "PageMol",
                        }
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
                        {
                            "type": "text",
                            "field": "name",
                            "operator": "contains",
                            "value": "PageMol",
                        }
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
                        {
                            "type": "text",
                            "field": "nonexistent",
                            "operator": "contains",
                            "value": "x",
                        }
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
                        {
                            "type": "text",
                            "field": "name",
                            "operator": "contains",
                            "value": "CountTarget",
                        }
                    ],
                    "logic": "and",
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_count" in data
        assert data["total_count"] >= 1

    async def test_empty_criteria_counts_all(self, client: AsyncClient, org_id: str) -> None:
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

    async def test_zero_match_returns_zero(self, client: AsyncClient, org_id: str) -> None:
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

    async def test_count_matches_execute_total(self, client: AsyncClient, org_id: str) -> None:
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
    dose_unit: str = "uM",
    fitted_value: float = 5.0,
    intercepts: list[tuple[str, float, float]] | None = None,
    curve_class: CurveClass = CurveClass.FULL,
) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """Seed a protocol + DR readout-def + N runs + N curves for one molecule.

    Returns ``(protocol_id, readout_definition_id, run_ids)``. Run dates are
    spaced one day apart starting today and decreasing back in time, so the
    aggregator can resolve "latest" deterministically.

    ``intercepts`` = list of ``(kind, level, value)`` stored on every curve's
    ``intercept_values`` (e.g. ``[("ic", 50, 5.0), ("ic", 90, 40.0)]``).
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
                "false, :dose_unit, 'high', 1, 1, :user)"
            ),
            {
                "id": protocol_id,
                "ws": workspace_id,
                "name": f"AggTest-{protocol_id.hex[:8]}",
                "dose_unit": dose_unit,
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

            intercept_values = (
                [
                    InterceptValue(
                        spec=InterceptSpec(
                            kind=InterceptKind(kind),
                            level=level,
                            basis=InterceptBasis.RELATIVE_PERCENT,
                            label=f"{kind.upper()}{int(level)}",
                        ),
                        value=value,
                        confidence_interval_low=None,
                        confidence_interval_high=None,
                        at_bound=False,
                    )
                    for kind, level, value in intercepts
                ]
                if intercepts
                else None
            )
            curve = DoseResponseCurve(
                workspace_id=workspace_id,
                molecule_id=molecule_id,
                batch_id=uuid.uuid4(),
                protocol_id=protocol_id,
                run_id=run_id,
                readout_definition_id=rd_id,
                curve_type=CurveType.IC50,
                fitted_value=fitted_value + i * 0.1,
                hill_slope=1.0,
                top=100.0,
                bottom=0.0,
                r_squared=0.97,
                num_points=8,
                curve_class=curve_class,
                raw_data=[],
                intercept_values=intercept_values,
            )
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            await repo.save(curve)

        await uow.commit()
    return protocol_id, rd_id, run_ids


async def _seed_numeric_readout(
    uow: AsyncUnitOfWork,
    *,
    workspace_id: uuid.UUID,
    molecule_id: uuid.UUID,
    readout_name: str,
    unit: str | None,
    value: float,
) -> uuid.UUID:
    """One protocol + one numeric readout-def + one run + one readout_data row."""
    protocol_id, rd_id, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO protocols (id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, protocol_version, "
                "created_by) "
                "VALUES (:id, :ws, :name, 'biochemical', 'active', false, 'uM', 'high', 1, 1, "
                ":user)"
            ),
            {
                "id": protocol_id,
                "ws": workspace_id,
                "name": f"RD-{protocol_id.hex[:8]}",
                "user": _SEED_USER_ID,
            },
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, unit, display_order, is_calculated) "
                "VALUES (:id, :proto, :name, 'numeric', :unit, 0, false)"
            ),
            {"id": rd_id, "proto": protocol_id, "name": readout_name, "unit": unit},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, "
                "status, is_locked, version, notes) "
                "VALUES (:id, :ws, :proto, :run_date, :user, 'approved', false, 1, NULL)"
            ),
            {
                "id": run_id,
                "ws": workspace_id,
                "proto": protocol_id,
                "run_date": date.today(),
                "user": _SEED_USER_ID,
            },
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO readout_data (id, workspace_id, run_id, molecule_id, "
                "readout_definition_id, value_numeric, is_outlier, is_computed) "
                "VALUES (:id, :ws, :run, :mol, :rd, :val, false, false)"
            ),
            {
                "id": uuid.uuid4(),
                "ws": workspace_id,
                "run": run_id,
                "mol": molecule_id,
                "rd": rd_id,
                "val": value,
            },
        )
        await uow.commit()
    return protocol_id


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


class TestActivityAnyProtocol:
    """``protocol_id: null`` spans every protocol; potency cutoffs are in µM
    and normalized through each protocol's dose_unit."""

    async def test_potency_cutoff_normalizes_units_across_protocols(
        self,
        client: AsyncClient,
        org_id: str,
        uow: AsyncUnitOfWork,
        workspace_id: uuid.UUID,
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "AnyProtoMol", "smiles": "CCCCO", "originating_org_id": org_id},
        )
        assert resp.status_code == 201
        mol_id = str(resp.json()["molecule"]["id"])

        # 5 µM in a µM protocol, 5 nM (= 0.005 µM) in an nM protocol.
        await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=uuid.UUID(mol_id), run_count=1
        )
        await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol_id),
            run_count=1,
            dose_unit="nM",
        )

        async def ids_for(where: list[dict]) -> set[str]:
            body = {
                "query": {
                    "criteria": [{"type": "activity", "protocol_id": None, "where": where}],
                    "logic": "and",
                }
            }
            res = await client.post("/api/v1/search/execute", json=body)
            assert res.status_code == 200, res.text
            return {m["id"] for m in res.json()["items"]}

        # < 1 µM: only the nM curve qualifies once normalized.
        assert mol_id in await ids_for([{"source": "dr_curve", "operator": "lt", "value": 1.0}])
        # < 0.001 µM: nothing qualifies — proves nM was scaled, not compared raw.
        assert mol_id not in await ids_for(
            [{"source": "dr_curve", "operator": "lt", "value": 0.001}]
        )
        # Curve class across any protocol.
        assert mol_id in await ids_for([{"source": "curve_class", "curve_classes": ["full"]}])
        assert mol_id not in await ids_for(
            [{"source": "curve_class", "curve_classes": ["inactive"]}]
        )

    async def test_intercept_key_across_protocols(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "AnyIcMol", "smiles": "CCCCCO", "originating_org_id": org_id},
        )
        mol_id = str(resp.json()["molecule"]["id"])
        # Protocol A (µM): IC50 5 µM, IC90 40 µM.  Protocol B (nM): IC50 5 nM.
        await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol_id),
            run_count=1,
            intercepts=[("ic", 50, 5.0), ("ic", 90, 40.0)],
        )
        await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol_id),
            run_count=1,
            dose_unit="nM",
            intercepts=[("ic", 50, 5.0)],
        )

        async def ids_for(where: list[dict]) -> set[str]:
            body = {
                "query": {
                    "criteria": [{"type": "activity", "protocol_id": None, "where": where}],
                    "logic": "and",
                }
            }
            res = await client.post("/api/v1/search/execute", json=body)
            assert res.status_code == 200, res.text
            return {m["id"] for m in res.json()["items"]}

        ic50 = {"kind": "ic", "level": 50}
        ic90 = {"kind": "ic", "level": 90}
        # IC50 < 1 µM: only B (5 nM) qualifies after normalization.
        assert mol_id in await ids_for(
            [{"source": "dr_curve", "intercept_key": ic50, "operator": "lt", "value": 1.0}]
        )
        # IC90 < 10 µM: A's IC90 is 40 µM, B has no IC90 → no match.
        assert mol_id not in await ids_for(
            [{"source": "dr_curve", "intercept_key": ic90, "operator": "lt", "value": 10.0}]
        )
        # IC90 < 50 µM: A qualifies.
        assert mol_id in await ids_for(
            [{"source": "dr_curve", "intercept_key": ic90, "operator": "lt", "value": 50.0}]
        )

    async def test_readout_name_across_protocols(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "AnyRdMol", "smiles": "CCCCCCO", "originating_org_id": org_id},
        )
        mol_id = uuid.UUID(resp.json()["molecule"]["id"])
        await _seed_numeric_readout(
            uow,
            workspace_id=workspace_id,
            molecule_id=mol_id,
            readout_name="% Inhibition",
            unit="%",
            value=20.0,
        )
        await _seed_numeric_readout(
            uow,
            workspace_id=workspace_id,
            molecule_id=mol_id,
            readout_name="%  inhibition",
            unit="%",
            value=80.0,
        )
        await _seed_numeric_readout(
            uow,
            workspace_id=workspace_id,
            molecule_id=mol_id,
            readout_name="% Inhibition",
            unit=None,
            value=99.0,
        )

        async def ids_for(where: list[dict]) -> set[str]:
            body = {
                "query": {
                    "criteria": [{"type": "activity", "protocol_id": None, "where": where}],
                    "logic": "and",
                }
            }
            res = await client.post("/api/v1/search/execute", json=body)
            assert res.status_code == 200, res.text
            return {m["id"] for m in res.json()["items"]}

        # > 50 in "% Inhibition (%)": second protocol (80) matches despite spacing/case.
        assert str(mol_id) in await ids_for(
            [
                {
                    "source": "readout_data",
                    "readout_name": "% Inhibition",
                    "unit": "%",
                    "operator": "gt",
                    "value": 50,
                }
            ]
        )
        # > 90 in "% Inhibition (%)": 99 is in the unit-less group, so no match.
        assert str(mol_id) not in await ids_for(
            [
                {
                    "source": "readout_data",
                    "readout_name": "% Inhibition",
                    "unit": "%",
                    "operator": "gt",
                    "value": 90,
                }
            ]
        )

    async def test_any_column_returns_entries(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "AnyColMol", "smiles": "CCCCCCCO", "originating_org_id": org_id},
        )
        mol_id = str(resp.json()["molecule"]["id"])
        await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol_id),
            run_count=1,
            intercepts=[("ic", 50, 5.0)],
        )
        await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol_id),
            run_count=1,
            dose_unit="nM",
            intercepts=[("ic", 50, 5.0)],
        )
        await _seed_numeric_readout(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol_id),
            readout_name="% Inhibition",
            unit="%",
            value=77.0,
        )

        body = {
            "query": {
                "criteria": [
                    {
                        "type": "activity",
                        "protocol_id": None,
                        "where": [
                            {
                                "source": "readout_data",
                                "readout_name": "% inhibition",
                                "unit": "%",
                                "operator": "gt",
                                "value": 50,
                            }
                        ],
                    }
                ],
                "logic": "and",
            },
            "protocol_columns": ["any"],
        }
        res = await client.post("/api/v1/search/execute", json=body)
        assert res.status_code == 200, res.text
        entries = res.json()["activity_data"][mol_id]["any"]["entries"]
        # nM curve first (0.005 µM), then µM curve, readouts (no µM) last.
        assert [e["unit"] for e in entries] == ["nM", "uM", "%"]
        assert entries[2]["label"] == "% Inhibition" and entries[2]["value"] == 77.0
        assert all(e["protocol_name"] for e in entries)

    async def test_readout_name_ignores_normalized_layer_rows(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """The any-protocol readout filter matches raw-layer rows only. A
        normalized row (``normalization_applied`` set) on the *same*
        readout-def name+unit group must not leak into the match even when
        its value would otherwise satisfy the cutoff."""
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "AnyRdNormMol", "smiles": "CCCCCCCCO", "originating_org_id": org_id},
        )
        assert resp.status_code == 201
        mol_id = uuid.UUID(resp.json()["molecule"]["id"])

        # Raw-layer row that does NOT satisfy ">50".
        await _seed_numeric_readout(
            uow,
            workspace_id=workspace_id,
            molecule_id=mol_id,
            readout_name="% Inhibition",
            unit="%",
            value=10.0,
        )

        # Normalized-layer row, same readout-def name+unit group, value that
        # WOULD satisfy ">50" if the filter wrongly included it.
        protocol_id, rd_id, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO protocols (id, workspace_id, name, protocol_type, status, "
                    "is_locked, dose_unit, pos_control_signal, version, protocol_version, "
                    "created_by) "
                    "VALUES (:id, :ws, :name, 'biochemical', 'active', false, 'uM', 'high', 1, "
                    "1, :user)"
                ),
                {
                    "id": protocol_id,
                    "ws": workspace_id,
                    "name": f"RDNorm-{protocol_id.hex[:8]}",
                    "user": _SEED_USER_ID,
                },
            )
            await uow.session.execute(
                sa.text(
                    "INSERT INTO readout_definitions "
                    "(id, protocol_id, name, data_type, unit, display_order, is_calculated) "
                    "VALUES (:id, :proto, :name, 'numeric', :unit, 0, false)"
                ),
                {"id": rd_id, "proto": protocol_id, "name": "% Inhibition", "unit": "%"},
            )
            await uow.session.execute(
                sa.text(
                    "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, "
                    "status, is_locked, version, notes) "
                    "VALUES (:id, :ws, :proto, :run_date, :user, 'approved', false, 1, NULL)"
                ),
                {
                    "id": run_id,
                    "ws": workspace_id,
                    "proto": protocol_id,
                    "run_date": date.today(),
                    "user": _SEED_USER_ID,
                },
            )
            await uow.session.execute(
                sa.text(
                    "INSERT INTO readout_data (id, workspace_id, run_id, molecule_id, "
                    "readout_definition_id, value_numeric, is_outlier, is_computed, "
                    "normalization_applied) "
                    "VALUES (:id, :ws, :run, :mol, :rd, :val, false, false, :norm)"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": workspace_id,
                    "run": run_id,
                    "mol": mol_id,
                    "rd": rd_id,
                    "val": 95.0,
                    "norm": "percent_inhibition",
                },
            )
            await uow.commit()

        body = {
            "query": {
                "criteria": [
                    {
                        "type": "activity",
                        "protocol_id": None,
                        "where": [
                            {
                                "source": "readout_data",
                                "readout_name": "% Inhibition",
                                "unit": "%",
                                "operator": "gt",
                                "value": 50,
                            }
                        ],
                    }
                ],
                "logic": "and",
            }
        }
        res = await client.post("/api/v1/search/execute", json=body)
        assert res.status_code == 200, res.text
        ids = {m["id"] for m in res.json()["items"]}
        assert str(mol_id) not in ids

    async def test_mg_ml_dose_unit_normalizes_via_molecular_weight(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """A ``mg/mL`` protocol converts to µM via the molecule's molecular
        weight (µM = mg/mL × 1e6 / MW), not left uncoverted or raising."""
        resp = await client.post(
            "/api/v1/molecules",
            json={"name": "MgMlMol", "smiles": "CCO", "originating_org_id": org_id},
        )
        assert resp.status_code == 201
        mol = resp.json()["molecule"]
        mol_id = mol["id"]
        mw = mol["descriptors"]["molecular_weight"]
        assert mw

        # Pick fitted_value so µM = fitted_value * 1e6 / MW is clearly < 1 µM.
        target_um = 0.5
        fitted_value = target_um * mw / 1e6

        await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol_id),
            run_count=1,
            dose_unit="mg/mL",
            intercepts=[("ic", 50, fitted_value)],
        )

        async def ids_for(value: float) -> set[str]:
            body = {
                "query": {
                    "criteria": [
                        {
                            "type": "activity",
                            "protocol_id": None,
                            "where": [
                                {
                                    "source": "dr_curve",
                                    "intercept_key": {"kind": "ic", "level": 50},
                                    "operator": "lt",
                                    "value": value,
                                }
                            ],
                        }
                    ],
                    "logic": "and",
                }
            }
            res = await client.post("/api/v1/search/execute", json=body)
            assert res.status_code == 200, res.text
            return {m["id"] for m in res.json()["items"]}

        assert mol_id in await ids_for(1.0)
        assert mol_id not in await ids_for(target_um / 10)


# ---------------------------------------------------------------------------
# Chemist-facing correctness: what a med-chemist types must mean what it says.
# ---------------------------------------------------------------------------


async def _register(client: AsyncClient, org_id: str, name: str, smiles: str) -> str:
    resp = await client.post(
        "/api/v1/molecules",
        json={"name": name, "smiles": smiles, "originating_org_id": org_id},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["molecule"]["id"])


async def _ids(client: AsyncClient, criteria: list[dict]) -> set[str]:
    res = await client.post(
        "/api/v1/search/execute", json={"query": {"criteria": criteria, "logic": "and"}}
    )
    assert res.status_code == 200, res.text
    return {m["id"] for m in res.json()["items"]}


async def _count_status(client: AsyncClient, criteria: list[dict]) -> int:
    res = await client.post(
        "/api/v1/search/count", json={"query": {"criteria": criteria, "logic": "and"}}
    )
    return res.status_code


class TestChemistSearchCorrectness:
    async def test_potency_cutoff_ignores_inactive_curves(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """An inactive fit parks a meaningless scalar on fitted_value (here
        0.001 µM). The grid reports it ND, so "IC50 < 10" must not call it a hit
        — not per-protocol, not across protocols, not in "every run" mode."""
        active = await _register(client, org_id, "ActiveHit", "CCCCCCN")
        inactive = await _register(client, org_id, "InactiveJunk", "CCCCCCCN")
        proto_a, rd_a, _ = await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=uuid.UUID(active), run_count=1
        )
        proto_i, rd_i, _ = await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(inactive),
            run_count=1,
            fitted_value=0.001,
            curve_class=CurveClass.INACTIVE,
        )

        def where(rd: uuid.UUID) -> list[dict]:
            return [
                {
                    "source": "dr_curve",
                    "readout_definition_id": str(rd),
                    "operator": "lt",
                    "value": 10,
                }
            ]

        assert active in await _ids(
            client, [{"type": "activity", "protocol_id": str(proto_a), "where": where(rd_a)}]
        )
        assert inactive not in await _ids(
            client, [{"type": "activity", "protocol_id": str(proto_i), "where": where(rd_i)}]
        )
        assert inactive not in await _ids(
            client,
            [
                {
                    "type": "activity",
                    "protocol_id": str(proto_i),
                    "run_scope": {"mode": "all"},
                    "where": where(rd_i),
                }
            ],
        )
        any_protocol = await _ids(
            client,
            [
                {
                    "type": "activity",
                    "protocol_id": None,
                    "where": [{"source": "dr_curve", "operator": "lt", "value": 10}],
                }
            ],
        )
        assert active in any_protocol
        assert inactive not in any_protocol

    async def test_readout_filter_targets_one_layer(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """Raw signal and its % inhibition layer share a readout-def. A raw
        filter must not match normalized rows, and naming the layer must."""
        mol = await _register(client, org_id, "LayerMol", "CCCCCCCCCN")
        protocol_id = await _seed_numeric_readout(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol),
            readout_name="Signal",
            unit="AU",
            value=0.2,
        )
        async with uow:
            rd_id, run_id = (
                await uow.session.execute(
                    sa.text(
                        "SELECT rd.id, r.id FROM readout_definitions rd "
                        "JOIN runs r ON r.protocol_id = rd.protocol_id WHERE rd.protocol_id = :p"
                    ),
                    {"p": protocol_id},
                )
            ).one()
            await uow.session.execute(
                sa.text(
                    # Plate-derived layer rows carry a well (the well-less
                    # unique index only covers summary imports).
                    "INSERT INTO readout_data (id, workspace_id, run_id, well_id, molecule_id, "
                    "readout_definition_id, value_numeric, is_outlier, is_computed, "
                    "normalization_applied) "
                    "VALUES (:id, :ws, :run, :well, :mol, :rd, 95, false, false, "
                    "'percent_inhibition')"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": workspace_id,
                    "run": run_id,
                    "well": uuid.uuid4(),
                    "mol": mol,
                    "rd": rd_id,
                },
            )
            await uow.commit()

        def crit(**layer: str) -> list[dict]:
            cond = {
                "source": "readout_data",
                "readout_definition_id": str(rd_id),
                "operator": "gt",
                "value": 50,
                **layer,
            }
            return [{"type": "activity", "protocol_id": str(protocol_id), "where": [cond]}]

        assert mol not in await _ids(client, crit())
        assert mol in await _ids(client, crit(normalization="percent_inhibition"))

    async def test_selectivity_normalizes_units_and_skips_inactive(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """Target 50 nM (= 0.05 µM) vs counter 10 µM is a 200× window. Divided
        raw (10 / 50) it would read 0.2× — the unit bug this pins."""
        mol = await _register(client, org_id, "SelectiveMol", "CCCCCCCCCCN")
        _, target_rd, _ = await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol),
            run_count=1,
            dose_unit="nM",
            fitted_value=50.0,
        )
        _, counter_rd, _ = await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol),
            run_count=1,
            fitted_value=10.0,
        )
        _, inactive_rd, _ = await _seed_multi_run_dr(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol),
            run_count=1,
            fitted_value=1000.0,
            curve_class=CurveClass.INACTIVE,
        )

        def sel(counter: uuid.UUID, ratio: float) -> list[dict]:
            return [
                {
                    "type": "selectivity",
                    "target_readout_definition_id": str(target_rd),
                    "counter_readout_definition_id": str(counter),
                    "ratio_operator": "gte",
                    "ratio_value": ratio,
                }
            ]

        assert mol in await _ids(client, sel(counter_rd, 100))
        assert mol not in await _ids(client, sel(counter_rd, 300))
        assert mol not in await _ids(client, sel(inactive_rd, 1))

    async def test_half_filled_numeric_rows_are_422_not_500(self, client: AsyncClient) -> None:
        for criterion in (
            {"type": "property", "field": "molecular_weight", "operator": "between"},
            {"type": "property", "field": "logp", "operator": "lte"},
            {"type": "batch", "field_type": "numeric", "field": "purity", "operator": "gte"},
            {"type": "custom_field", "field": "sol", "mode": "numeric", "operator": "gt"},
            {
                "type": "selectivity",
                "target_readout_definition_id": str(uuid.uuid4()),
                "counter_readout_definition_id": str(uuid.uuid4()),
                "ratio_operator": "gte",
            },
        ):
            assert await _count_status(client, [criterion]) == 422, criterion

    async def test_open_ended_property_range(self, client: AsyncClient, org_id: str) -> None:
        """Only a max (MW ≤ 100) — the most common med-chem filter."""
        small = await _register(client, org_id, "Methanol", "CO")
        big = await _register(client, org_id, "Decane", "CCCCCCCCCC")
        hits = await _ids(
            client,
            [{"type": "property", "field": "molecular_weight", "operator": "between", "max": 100}],
        )
        assert small in hits
        assert big not in hits

    async def test_any_keyword_matches_names_and_external_ids(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        by_name = await _register(client, org_id, "Kinostatin", "CCCCCCCCCCCN")
        by_ext = await _register(client, org_id, "Unrelated", "CCCCCCCCCCCCN")
        async with uow:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO molecule_identifiers (id, molecule_id, workspace_id, identifier, "
                    "identifier_type, source, registered_by) "
                    "VALUES (:id, :mol, :ws, 'VENDOR-KINO-77', 'custom', 'vendor', :user)"
                ),
                {"id": uuid.uuid4(), "mol": by_ext, "ws": workspace_id, "user": _SEED_USER_ID},
            )
            await uow.commit()

        def any_(value: str) -> list[dict]:
            return [{"type": "text", "field": "any", "operator": "contains", "value": value}]

        assert by_name in await _ids(client, any_("kinostatin"))
        assert by_ext in await _ids(client, any_("KINO-77"))
        assert by_ext not in await _ids(client, any_("kinostatin"))

    async def test_keyword_list_and_exact_resolve_pasted_structures(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        aspirin = await _register(client, org_id, "Aspirin", "CC(=O)Oc1ccccc1C(=O)O")
        ext = await _register(client, org_id, "ExtOnly", "CCCCCCCCCCCCCN")
        async with uow:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO molecule_identifiers (id, molecule_id, workspace_id, identifier, "
                    "identifier_type, source, registered_by) "
                    "VALUES (:id, :mol, :ws, 'EXT-000123', 'custom', 'vendor', :user)"
                ),
                {"id": uuid.uuid4(), "mol": ext, "ws": workspace_id, "user": _SEED_USER_ID},
            )
            await uow.commit()

        def kwl(ref_type: str, values: list[str]) -> list[dict]:
            return [{"type": "keyword_list", "ref_type": ref_type, "values": values}]

        # Kekulé SMILES for aspirin still standardizes to the registered compound.
        assert aspirin in await _ids(client, kwl("smiles", ["CC(=O)OC1=CC=CC=C1C(O)=O"]))
        assert ext in await _ids(client, kwl("external_id", ["EXT-000123"]))
        assert await _ids(client, kwl("external_id", ["NO-SUCH-ID"])) == set()
        assert aspirin in await _ids(
            client, [{"type": "structure", "kind": "exact", "smiles": "OC(=O)c1ccccc1OC(C)=O"}]
        )
        assert (
            await _count_status(
                client, [{"type": "structure", "kind": "exact", "smiles": "not-a-smiles"}]
            )
            == 422
        )

    async def test_latest_run_scope_means_most_recent_run_date(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """Run 0 is dated today (IC50 5.0), run 1 yesterday (IC50 5.1)."""
        mol = await _register(client, org_id, "LatestMol", "CCCCCCCCCCCCCCN")
        proto, rd, _ = await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=uuid.UUID(mol), run_count=2
        )

        def latest_lt(value: float) -> list[dict]:
            cond = {"source": "dr_curve", "readout_definition_id": str(rd), "operator": "lt"}
            return [
                {
                    "type": "activity",
                    "protocol_id": str(proto),
                    "run_scope": {"mode": "latest"},
                    "where": [{**cond, "value": value}],
                }
            ]

        assert mol in await _ids(client, latest_lt(5.05))
        assert mol not in await _ids(client, latest_lt(4.9))

    async def test_search_export_with_activity_columns_completes(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """Exporting a search that carries a dose-response column must render
        (it failed on every such export once ListProtocols started returning
        ProtocolWithTargets)."""
        import asyncio

        mol = await _register(client, org_id, "ExportMol", "CCCCCCCCCCCCCCCN")
        _, rd, _ = await _seed_multi_run_dr(
            uow, workspace_id=workspace_id, molecule_id=uuid.UUID(mol), run_count=1
        )
        start = await client.post(
            "/api/v1/exports",
            json={
                "format": "csv",
                "payload": {
                    "query": {
                        "criteria": [{"type": "keyword_list", "ref_type": "uuid", "values": [mol]}]
                    },
                    "protocol_columns": [f"drc:{rd}"],
                },
            },
        )
        assert start.status_code == 202, start.text
        job_id = start.json()["job_id"]
        for _ in range(50):
            body = (await client.get(f"/api/v1/exports/{job_id}")).json()
            if body["status"] in {"ready", "failed"}:
                break
            await asyncio.sleep(0.1)
        assert body["status"] == "ready", body
        assert body["row_count"] == 1

    async def test_censored_readout_values_match_only_when_certain(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """A reported ">50" IC50 is no hit for "< 60" — and is one for "> 40"."""
        mol = await _register(client, org_id, "CensoredMol", "CCCCCCCCCCCCCCCCN")
        protocol_id = await _seed_numeric_readout(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol),
            readout_name="IC50",
            unit="uM",
            value=50.0,
        )
        async with uow:
            rd_id = (
                await uow.session.execute(
                    sa.text("SELECT id FROM readout_definitions WHERE protocol_id = :p"),
                    {"p": protocol_id},
                )
            ).scalar_one()
            await uow.session.execute(
                sa.text("UPDATE readout_data SET value_qualifier = '>' WHERE molecule_id = :m"),
                {"m": mol},
            )
            await uow.commit()

        def crit(op: str, value: float) -> list[dict]:
            cond = {"source": "readout_data", "readout_definition_id": str(rd_id)}
            return [
                {
                    "type": "activity",
                    "protocol_id": str(protocol_id),
                    "where": [{**cond, "operator": op, "value": value}],
                }
            ]

        assert mol not in await _ids(client, crit("lt", 60))
        assert mol in await _ids(client, crit("gt", 40))
        assert mol in await _ids(client, crit("gt", 50))
        assert mol not in await _ids(client, crit("gt", 60))
        any_lt = [
            {
                "type": "activity",
                "protocol_id": None,
                "where": [
                    {
                        "source": "readout_data",
                        "readout_name": "IC50",
                        "unit": "uM",
                        "operator": "lt",
                        "value": 60,
                    }
                ],
            }
        ]
        assert mol not in await _ids(client, any_lt)

    async def test_control_wells_do_not_empty_every_run_or_negated_filters(
        self, client: AsyncClient, org_id: str, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
    ) -> None:
        """Control wells store readouts with molecule_id NULL. One failing
        control in a NOT IN subquery used to make "every run" (and negated
        readout filters) match no compound at all."""
        mol = await _register(client, org_id, "EveryRunMol", "CCCCCCCCCCCCCCCCCN")
        protocol_id = await _seed_numeric_readout(
            uow,
            workspace_id=workspace_id,
            molecule_id=uuid.UUID(mol),
            readout_name="Signal",
            unit="AU",
            value=80.0,
        )
        async with uow:
            rd_id, run_id = (
                await uow.session.execute(
                    sa.text(
                        "SELECT rd.id, r.id FROM readout_definitions rd "
                        "JOIN runs r ON r.protocol_id = rd.protocol_id WHERE rd.protocol_id = :p"
                    ),
                    {"p": protocol_id},
                )
            ).one()
            await uow.session.execute(
                sa.text(
                    "INSERT INTO readout_data (id, workspace_id, run_id, well_id, molecule_id, "
                    "readout_definition_id, value_numeric, is_outlier, is_computed) "
                    "VALUES (:id, :ws, :run, :well, NULL, :rd, 1, false, false)"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": workspace_id,
                    "run": run_id,
                    "well": uuid.uuid4(),
                    "rd": rd_id,
                },
            )
            await uow.commit()

        cond = {
            "source": "readout_data",
            "readout_definition_id": str(rd_id),
            "operator": "gt",
            "value": 50,
        }
        every_run = [
            {
                "type": "activity",
                "protocol_id": str(protocol_id),
                "run_scope": {"mode": "all"},
                "where": [cond],
            }
        ]
        assert mol in await _ids(client, every_run)
        negated_fail = [
            {
                "type": "activity",
                "protocol_id": str(protocol_id),
                "negate": True,
                "where": [{**cond, "value": 90}],
            }
        ]
        assert mol in await _ids(client, negated_fail)

    async def test_export_keeps_compounds_that_belong_to_a_project(
        self, client: AsyncClient, org_id: str
    ) -> None:
        """No project chips selected: the grid shows a project's compounds, so
        the export must too (it used to apply "unassigned only")."""
        import asyncio

        mol = await _register(client, org_id, "ProjectMol", "CCCCCCCCCCCCCCCCCCN")
        proj = await client.post("/api/v1/projects", json={"name": "Export Scope Project"})
        assert proj.status_code == 201, proj.text
        add = await client.post(f"/api/v1/projects/{proj.json()['id']}/molecules/{mol}")
        assert add.status_code == 204, add.text

        query = {"criteria": [{"type": "keyword_list", "ref_type": "uuid", "values": [mol]}]}
        assert mol in await _ids(client, query["criteria"])
        start = await client.post(
            "/api/v1/exports", json={"format": "csv", "payload": {"query": query}}
        )
        job_id = start.json()["job_id"]
        for _ in range(50):
            body = (await client.get(f"/api/v1/exports/{job_id}")).json()
            if body["status"] in {"ready", "failed"}:
                break
            await asyncio.sleep(0.1)
        assert body["status"] == "ready", body
        assert body["row_count"] == 1
