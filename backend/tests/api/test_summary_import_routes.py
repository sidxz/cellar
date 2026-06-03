"""API tests: preview-summary-file + import-summary-file routes.

Drives the full HTTP stack (real DI container, real DB, FakeAuth) to prove the
read UoW is active end-to-end: a route that didn't enter the use case's UoW
would raise ``UnitOfWork is not active`` on the first repo call instead of
returning a 200/201.

Flow:
  1. Seed a protocol with an ``IC50`` numeric readout def + a run + a
     registered molecule (so ``registration_number`` resolves on upsert).
  2. POST the file to ``preview-summary-file`` → 200, a suggestion has
     role ``readout`` bound to the IC50 def id.
  3. POST file + mapping JSON to ``import-summary-file`` → 201,
     ``values_inserted == 1``.
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth
from tests.fixtures.dose_response_curves import (
    _insert_org,
    _insert_protocol,
    _insert_run,
)


async def _insert_readout_def(
    uow: AsyncUnitOfWork,
    rd_id: uuid.UUID,
    protocol_id: uuid.UUID,
    *,
    name: str,
    data_type: str,
    display_order: int,
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO readout_definitions "
            "(id, protocol_id, name, data_type, display_order, is_calculated) "
            "VALUES (:id, :proto, :name, :dt, :ord, false)"
        ),
        {"id": rd_id, "proto": protocol_id, "name": name, "dt": data_type, "ord": display_order},
    )


async def _insert_molecule(
    uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID, reg: str
) -> None:
    org_id = uuid.uuid4()
    await uow.session.execute(
        sa.text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :name, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws_id, "name": f"Org-{reg}"},
    )
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecules "
            "(id, workspace_id, name, molecule_type, structure_status, "
            "registration_status, synthesis_status, lifecycle_stage, "
            "registration_number, originating_org_id, version) "
            "VALUES (:id, :ws, :name, 'small_molecule', 'undisclosed', "
            "'approved', 'virtual', 'registered', :reg, :org, 1)"
        ),
        {"id": mol_id, "ws": ws_id, "name": f"M-{reg}", "reg": reg, "org": org_id},
    )
    # Summary import now resolves compound_ref via ``find_by_identifier`` (which
    # JOINs molecule_identifiers, NOT the registration_number column), so seed an
    # identifier row equal to the reg value the file's compound_ref carries.
    await uow.session.execute(
        sa.text(
            "INSERT INTO molecule_identifiers "
            "(id, molecule_id, workspace_id, identifier, identifier_type, source, registered_by) "
            "VALUES (:id, :mol, :ws, :ident, 'custom', 'test', :by)"
        ),
        {
            "id": uuid.uuid4(),
            "mol": mol_id,
            "ws": ws_id,
            "ident": reg,
            "by": uuid.uuid4(),
        },
    )


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], workspace_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, str]:
    """Seed org + protocol + IC50 readout def + run + registered molecule.

    Returns (run_id, ic50_def_id, registration_number).
    """
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    ic50_id = uuid.uuid4()
    molecule_id = uuid.uuid4()
    reg = f"REG-{uuid.uuid4().hex[:8]}"

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await _insert_org(uow, org_id, workspace_id)
        await _insert_protocol(uow, protocol_id, workspace_id)
        await _insert_readout_def(
            uow, ic50_id, protocol_id, name="IC50", data_type="numeric", display_order=0
        )
        await _insert_run(uow, run_id, protocol_id, workspace_id)
        await _insert_molecule(uow, molecule_id, workspace_id, reg)
        await uow.commit()

    return run_id, ic50_id, reg


class TestSummaryImportRoutes:
    async def test_preview_then_import_flow(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        fake_auth: FakeAuth,
    ) -> None:
        ws = fake_auth.workspace_id
        run_id, ic50_id, reg = await _seed(session_factory, ws)

        csv = f"Compound,IC50\n{reg},5.2\n".encode()

        # --- Preview ---
        preview_resp = await client.post(
            f"/api/v1/runs/{run_id}/preview-summary-file",
            files={"file": ("summary.csv", csv, "text/csv")},
        )
        assert preview_resp.status_code == 200, preview_resp.text
        preview = preview_resp.json()
        assert preview["headers"] == ["Compound", "IC50"]
        assert preview["total_rows"] == 1

        by_header = {s["header"]: s for s in preview["suggestions"]}
        assert by_header["Compound"]["role"] == "compound_ref"
        ic50 = by_header["IC50"]
        assert ic50["role"] == "readout"
        assert ic50["readout_definition_id"] == str(ic50_id)

        # --- Import ---
        mapping = {
            "compound_ref": "Compound",
            "readout_columns": {"IC50": str(ic50_id)},
        }
        import_resp = await client.post(
            f"/api/v1/runs/{run_id}/import-summary-file",
            files={"file": ("summary.csv", csv, "text/csv")},
            data={"mapping": json.dumps(mapping)},
        )
        assert import_resp.status_code == 201, import_resp.text
        out = import_resp.json()
        assert out["values_inserted"] == 1
        assert out["values_updated"] == 0
        assert out["rows_processed"] == 1
        assert out["errors"] == []

    async def test_import_missing_run_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        mapping = {"compound_ref": "Compound", "readout_columns": {"IC50": str(uuid.uuid4())}}
        resp = await client.post(
            f"/api/v1/runs/{uuid.uuid4()}/import-summary-file",
            files={"file": ("summary.csv", b"Compound,IC50\nX,1\n", "text/csv")},
            data={"mapping": json.dumps(mapping)},
        )
        assert resp.status_code == 404, resp.text

    async def test_resolve_summary_file_forecasts_inserts(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        fake_auth: FakeAuth,
    ) -> None:
        """Dry-run forecasts an insert and writes NOTHING to readout_data."""
        ws = fake_auth.workspace_id
        run_id, ic50_id, reg = await _seed(session_factory, ws)
        csv = f"Compound,IC50\n{reg},5.2\n".encode()
        mapping = {"compound_ref": "Compound", "readout_columns": {"IC50": str(ic50_id)}}

        resp = await client.post(
            f"/api/v1/runs/{run_id}/resolve-summary-file",
            files={"file": ("summary.csv", csv, "text/csv")},
            data={"mapping": json.dumps(mapping)},
        )
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert out["values_to_insert"] >= 1
        assert out["values_to_update"] == 0
        assert out["unmatched_compound_refs"] == []

        # CRITICAL: the dry-run must NOT have persisted any readout_data rows.
        uow = AsyncUnitOfWork(session_factory)
        async with uow:
            count = await uow.session.scalar(
                sa.text("SELECT count(*) FROM readout_data WHERE run_id = :rid"),
                {"rid": run_id},
            )
        assert count == 0

    async def test_resolve_summary_file_reports_unmatched(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        fake_auth: FakeAuth,
    ) -> None:
        """A compound_ref not in the DB lands in unmatched_compound_refs."""
        ws = fake_auth.workspace_id
        run_id, ic50_id, _reg = await _seed(session_factory, ws)
        unknown = f"NOPE-{uuid.uuid4().hex[:8]}"
        csv = f"Compound,IC50\n{unknown},5.2\n".encode()
        mapping = {"compound_ref": "Compound", "readout_columns": {"IC50": str(ic50_id)}}

        resp = await client.post(
            f"/api/v1/runs/{run_id}/resolve-summary-file",
            files={"file": ("summary.csv", csv, "text/csv")},
            data={"mapping": json.dumps(mapping)},
        )
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert unknown in out["unmatched_compound_refs"]

    async def test_resolve_malformed_mapping_returns_422(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        fake_auth: FakeAuth,
    ) -> None:
        """Malformed mapping form field must return 422, never a 500."""
        ws = fake_auth.workspace_id
        run_id, _ic50_id, reg = await _seed(session_factory, ws)
        csv = f"Compound,IC50\n{reg},5.2\n".encode()

        bad_json_resp = await client.post(
            f"/api/v1/runs/{run_id}/resolve-summary-file",
            files={"file": ("summary.csv", csv, "text/csv")},
            data={"mapping": "{not valid json"},
        )
        assert bad_json_resp.status_code == 422, bad_json_resp.text

        bad_uuid_resp = await client.post(
            f"/api/v1/runs/{run_id}/resolve-summary-file",
            files={"file": ("summary.csv", csv, "text/csv")},
            data={"mapping": json.dumps({"readout_columns": {"IC50": "not-a-uuid"}})},
        )
        assert bad_uuid_resp.status_code == 422, bad_uuid_resp.text

    async def test_import_malformed_mapping_returns_422(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        fake_auth: FakeAuth,
    ) -> None:
        """Malformed mapping form field must return 4xx (422), never a 500.

        Covers two bad-input shapes:
          * invalid JSON syntax
          * a readout_columns value that isn't a UUID
        Both should be caught and mapped to a domain ValidationError -> 422.
        """
        ws = fake_auth.workspace_id
        run_id, _ic50_id, reg = await _seed(session_factory, ws)
        csv = f"Compound,IC50\n{reg},5.2\n".encode()

        # --- Invalid JSON syntax ---
        bad_json_resp = await client.post(
            f"/api/v1/runs/{run_id}/import-summary-file",
            files={"file": ("summary.csv", csv, "text/csv")},
            data={"mapping": "{not valid json"},
        )
        assert bad_json_resp.status_code == 422, bad_json_resp.text
        assert bad_json_resp.status_code != 500

        # --- Valid JSON, but readout id is not a UUID ---
        bad_uuid_resp = await client.post(
            f"/api/v1/runs/{run_id}/import-summary-file",
            files={"file": ("summary.csv", csv, "text/csv")},
            data={"mapping": json.dumps({"readout_columns": {"IC50": "not-a-uuid"}})},
        )
        assert bad_uuid_resp.status_code == 422, bad_uuid_resp.text
        assert bad_uuid_resp.status_code != 500
