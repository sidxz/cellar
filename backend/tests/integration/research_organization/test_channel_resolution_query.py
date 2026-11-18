"""Integration tests for the SQL ChannelResolutionQuery: the run-scoped reads
of add-from-runs and its preview (reported endpoints, the wellless guard, and
sample wells only)."""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
import sqlalchemy as sa


@pytest.mark.asyncio
async def test_endpoint_candidates_on_a_dr_channel(session_factory):
    """D1 — a dose-response channel can read the raw readout_data rows for its
    own readout definition (the summary-imported "reported endpoint").

    Pins three things at once on one fixture: the raw well-less row comes
    back while its computed sibling does not, ``run_ids`` is honoured, and the
    DR branch of ``fetch_candidates_for_runs`` still returns only curves.
    """
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        ValueQualifier,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
    )

    ws_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.UUID("eeeeeeee-0000-0000-0000-000000000003")
    protocol_id = uuid.uuid4()
    run_curve_id = uuid.uuid4()
    run_summary_id = uuid.uuid4()
    mol_curve_id = uuid.uuid4()
    mol_endpoint_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    rd_id = uuid.uuid4()
    curve_id = uuid.uuid4()
    raw_endpoint_id = uuid.uuid4()
    computed_endpoint_id = uuid.uuid4()
    other_run_endpoint_id = uuid.uuid4()
    mol_welled_id = uuid.uuid4()
    welled_row_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO organizations "
                "(id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": org_id, "ws": ws_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO protocols "
                "(id, workspace_id, name, name_base, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, "
                "protocol_version, created_by) "
                "VALUES (:id, :ws, 'Reported IC50', 'Reported IC50', 'biochemical', 'active', "
                "false, 'uM', 'high', 1, 1, :user)"
            ),
            {"id": protocol_id, "ws": ws_id, "user": user_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, "
                "is_calculated, unit, dose_response_config) "
                "VALUES (:id, :proto, 'IC50', 'dose_response', 0, false, 'uM', "
                "CAST(:cfg AS jsonb))"
            ),
            {
                "id": rd_id,
                "proto": protocol_id,
                "cfg": json.dumps(
                    {
                        "curve_type": "ic50",
                        "y_readout_name": "Response",
                        "intercepts": [
                            {"kind": "ic", "level": 50.0},
                            {"kind": "ic", "level": 90.0},
                        ],
                    }
                ),
            },
        )
        for run_id in (run_curve_id, run_summary_id):
            await session.execute(
                sa.text(
                    "INSERT INTO runs "
                    "(id, workspace_id, protocol_id, run_date, operator, "
                    "status, is_locked, version, notes) "
                    "VALUES (:id, :ws, :proto, :run_date, :user, 'approved', "
                    "false, 1, NULL)"
                ),
                {
                    "id": run_id,
                    "ws": ws_id,
                    "proto": protocol_id,
                    "run_date": date(2026, 1, 1),
                    "user": user_id,
                },
            )
        await session.execute(
            sa.text(
                "INSERT INTO dose_response_curves "
                "(id, workspace_id, molecule_id, batch_id, protocol_id, "
                "run_id, readout_definition_id, curve_type, fitted_value, "
                "hill_slope, top, bottom, r_squared, num_points) "
                "VALUES (:id, :ws, :mol, :batch, :proto, :run, :rd, "
                "'ic50', 1.25, 1.0, 100.0, 0.0, 0.98, 8)"
            ),
            {
                "id": curve_id,
                "ws": ws_id,
                "mol": mol_curve_id,
                "batch": batch_id,
                "proto": protocol_id,
                "run": run_curve_id,
                "rd": rd_id,
            },
        )
        # Reported endpoint: a well-less raw row on the SAME readout def.
        for row_id, run_id, value, norm in (
            (raw_endpoint_id, run_curve_id, 32.0, None),
            (computed_endpoint_id, run_curve_id, 91.0, "percent_inhibition"),
            (other_run_endpoint_id, run_summary_id, 8.0, None),
        ):
            await session.execute(
                sa.text(
                    "INSERT INTO readout_data "
                    "(id, workspace_id, run_id, well_id, molecule_id, "
                    "batch_id, readout_definition_id, value_numeric, "
                    "value_qualifier, is_outlier, is_computed, "
                    "normalization_applied) "
                    "VALUES (:id, :ws, :run, NULL, :mol, :batch, :rd, "
                    ":value, '>', false, :computed, :norm)"
                ),
                {
                    "id": row_id,
                    "ws": ws_id,
                    "run": run_id,
                    "mol": mol_endpoint_id,
                    "batch": batch_id,
                    "rd": rd_id,
                    "value": value,
                    "computed": norm is not None,
                    "norm": norm,
                },
            )
        # A per-well response reading on the SAME dose-response definition —
        # a plate column mapped onto it. Never a reported endpoint.
        await session.execute(
            sa.text(
                "INSERT INTO readout_data "
                "(id, workspace_id, run_id, well_id, molecule_id, "
                "batch_id, readout_definition_id, value_numeric, "
                "value_qualifier, is_outlier, is_computed, "
                "normalization_applied) "
                "VALUES (:id, :ws, :run, :well, :mol, :batch, :rd, "
                "77.0, '=', false, false, NULL)"
            ),
            {
                "id": welled_row_id,
                "ws": ws_id,
                "run": run_curve_id,
                "well": uuid.uuid4(),
                "mol": mol_welled_id,
                "batch": batch_id,
                "rd": rd_id,
            },
        )

    query = SQLAlchemyChannelResolutionQuery(session_factory)

    endpoints = (
        await query.fetch_endpoint_candidates_for_runs(
            workspace_id=ws_id,
            run_ids=[run_curve_id, run_summary_id],
            readout_definition_id=rd_id,
        )
    )[mol_endpoint_id]
    assert sorted(c.readout_id for c in endpoints) == sorted(
        [raw_endpoint_id, other_run_endpoint_id]
    ), "The computed (%inhibition) sibling must not surface on a raw-layer channel."
    raw = next(c for c in endpoints if c.readout_id == raw_endpoint_id)
    assert raw.value == pytest.approx(32.0)
    assert raw.qualifier is ValueQualifier.GT
    assert raw.unit == "uM"
    assert raw.curve_id is None
    # Tagged as the readout's primary intercept, so only an IC50 channel takes it.
    assert raw.intercept_values == [{"spec": {"kind": "ic", "level": 50.0}, "value": 32.0}]

    scoped = await query.fetch_endpoint_candidates_for_runs(
        workspace_id=ws_id,
        run_ids=[run_curve_id],
        readout_definition_id=rd_id,
    )
    assert [c.readout_id for c in scoped[mol_endpoint_id]] == [raw_endpoint_id]

    # The DR branch of fetch_candidates_for_runs is unchanged — curves only.
    curves = await query.fetch_candidates_for_runs(
        workspace_id=ws_id,
        run_ids=[run_curve_id, run_summary_id],
        protocol_id=protocol_id,
        readout_definition_id=rd_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
    )
    assert list(curves) == [mol_curve_id]
    assert [c.curve_id for c in curves[mol_curve_id]] == [curve_id]

    # ``wellless_only`` — the DR fallback's guard. A molecule whose only raw
    # row on this definition is a per-well response reading yields nothing, so
    # it can't be averaged into a fake reported endpoint.
    scoped_wellless = await query.fetch_endpoint_candidates_for_runs(
        workspace_id=ws_id,
        run_ids=[run_curve_id],
        readout_definition_id=rd_id,
        wellless_only=True,
    )
    assert mol_welled_id not in scoped_wellless
    assert [c.readout_id for c in scoped_wellless[mol_endpoint_id]] == [raw_endpoint_id]

    # Default (numeric readout channels) still reads per-well rows.
    welled = await query.fetch_endpoint_candidates_for_runs(
        workspace_id=ws_id, run_ids=[run_curve_id], readout_definition_id=rd_id
    )
    assert [c.readout_id for c in welled[mol_welled_id]] == [welled_row_id]


@pytest.mark.asyncio
async def test_readout_candidates_are_a_compounds_sample_wells_and_wellless_rows(
    uow, session_factory, workspace_id
):
    """Rifampicin's positive-control and reference wells are plate QC: no campaign pick
    (run-scoped) reads them — a LATEST_RUN pick could otherwise land on
    a ~100 % control well instead of the sample."""
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization import (
        channel_resolution_query as crq,
    )
    from tests.integration import _screening_seed as seed

    ws = workspace_id
    norm = "percent_inhibition"
    async with uow:
        s = uow.session
        rif = await seed.molecule(s, ws, await seed.org(s, ws), "rifampicin")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal", normalizations=[norm])
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="completed")
        plate = await seed.plate(s, run, 1)
        for col, (role, value) in enumerate(
            [("sample", 40.0), ("positive_control", 100.0), ("reference", 95.0)], start=1
        ):
            w = await seed.well(s, plate, "A", col, well_type=role)
            await seed.readout(s, ws, run, rd, rif, value, well_id=w, normalization=norm)
        await seed.readout(s, ws, run, rd, rif, 60.0, wellless=True, normalization=norm)
        await uow.commit()

    query = crq.SQLAlchemyChannelResolutionQuery(session_factory)
    by_runs = await query.fetch_candidates_for_runs(
        workspace_id=ws,
        run_ids=[run],
        protocol_id=p,
        readout_definition_id=rd,
        source_kind=ChannelSourceKind.READOUT_DATA,
        normalization_applied=norm,
    )

    assert {m: sorted(c.value for c in cs) for m, cs in by_runs.items()} == {rif: [40.0, 60.0]}
