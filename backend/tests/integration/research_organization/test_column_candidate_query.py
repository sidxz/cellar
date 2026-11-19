"""SQL ColumnCandidateQuery: one round trip per column, with the facts the
resolver groups on (well dose or the run's Test concentration, batch, replicates)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from cellar.application.screening.run_aggregation import ResolvedRun
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.research_organization.measurement_facts import (
    TEST_CONCENTRATION,
    Concentration,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.column_candidate_query import (  # noqa: E501
    SQLAlchemyColumnCandidateQuery,
)
from tests.integration import _screening_seed as seed


def _channel(
    protocol_id: uuid.UUID, rd_id: uuid.UUID, kind: ChannelSourceKind, norm: str | None = None
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="L",
        protocol_id=protocol_id,
        readout_definition_id=rd_id,
        source_kind=kind,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        normalization_applied=norm,
    )


@pytest.mark.asyncio
async def test_fetch_joins_well_dose_and_condition(uow, session_factory, workspace_id):
    ws = workspace_id
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m")
        b1, b2 = await seed.batch(s, ws, mol, "B1"), await seed.batch(s, ws, mol, "B2")
        p = await seed.protocol(
            s, ws, dose_unit="nM", conditions=[(TEST_CONCENTRATION, "numeric", "uM")]
        )
        rd = await seed.readout_def(s, p, name="Signal", aggregation="median")
        plate_run = await seed.run(s, ws, p, date(2026, 1, 1), conditions={TEST_CONCENTRATION: 10})
        plate = await seed.plate(s, plate_run, 1)
        dosed = await seed.well(s, plate, "A", 1, dose=500.0, batch_id=b1)
        undosed = await seed.well(s, plate, "A", 2)
        control = await seed.well(s, plate, "A", 3, well_type="positive_control")
        await seed.readout(s, ws, plate_run, rd, mol, 40.0, well_id=dosed)
        await seed.readout(s, ws, plate_run, rd, mol, 41.0, well_id=undosed, batch_id=b2)
        await seed.readout(s, ws, plate_run, rd, mol, 99.0, well_id=control)
        await seed.readout(s, ws, plate_run, rd, mol, 1.0, well_id=dosed, outlier=True)
        summary = await seed.run(
            s, ws, p, date(2026, 2, 1), conditions={TEST_CONCENTRATION: "500 nM"}
        )
        await seed.readout(
            s, ws, summary, rd, mol, 7.5, wellless=True, batch_id=b2, replicate_count=3
        )
        bare = await seed.run(s, ws, p, date(2026, 3, 1))
        await seed.readout(s, ws, bare, rd, mol, 9.0, wellless=True)
        await uow.commit()

    out = await SQLAlchemyColumnCandidateQuery(session_factory).fetch(
        workspace_id=ws,
        channel=_channel(p, rd, ChannelSourceKind.READOUT_DATA),
        run_ids=None,
        molecule_ids=None,
    )

    facts = {
        c.run.value: (c.run.run_id, c.dose, c.batch_id, c.well_id is None, c.replicate_count)
        for c in out[mol]
    }
    assert facts == {
        # The well's dose wins over the run's condition, in the protocol's dose unit.
        40.0: (plate_run, Concentration(500.0, "nM"), b1, False, None),
        # No well dose: the run's bare-number condition, in the definition's unit.
        41.0: (plate_run, Concentration(10.0, "µM"), b2, False, None),
        7.5: (summary, Concentration(500.0, "nM"), b2, True, 3),
        9.0: (bare, None, None, True, None),
    }
    assert {c.aggregation for c in out[mol]} == {"median"}
    assert all(c.run_created_at is not None for c in out[mol])


@pytest.mark.asyncio
async def test_fetch_run_and_molecule_filters(uow, session_factory, workspace_id):
    ws = workspace_id
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        m1, m2 = await seed.molecule(s, ws, org, "m1"), await seed.molecule(s, ws, org, "m2")
        p = await seed.protocol(s, ws)
        signal = await seed.readout_def(s, p, name="Signal")
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        ra = await seed.run(s, ws, p, date(2026, 1, 1))
        rb = await seed.run(s, ws, p, date(2026, 2, 1))
        curves = {}
        for run in (ra, rb):
            for mol in (m1, m2):
                await seed.readout(s, ws, run, signal, mol, 10.0)
                # with_well: a per-well response on the IC50 definition, never an endpoint.
                curves[run, mol] = await seed.curve(s, ws, p, run, mol, ic50)
        await seed.readout(s, ws, rb, ic50, m2, 3.3, wellless=True)
        await uow.commit()

    query = SQLAlchemyColumnCandidateQuery(session_factory)
    readout = _channel(p, signal, ChannelSourceKind.READOUT_DATA)

    scoped = await query.fetch(workspace_id=ws, channel=readout, run_ids=[ra], molecule_ids=[m1])
    assert {m: [c.run.run_id for c in cs] for m, cs in scoped.items()} == {m1: [ra]}

    every = await query.fetch(workspace_id=ws, channel=readout, run_ids=None, molecule_ids=None)
    assert {m: sorted(c.run.run_id for c in cs) for m, cs in every.items()} == {
        m1: sorted([ra, rb]),
        m2: sorted([ra, rb]),
    }

    assert await query.fetch(workspace_id=ws, channel=readout, run_ids=[], molecule_ids=None) == {}
    assert (
        await query.fetch(
            workspace_id=uuid.uuid4(), channel=readout, run_ids=None, molecule_ids=None
        )
        == {}
    )

    dr = _channel(p, ic50, ChannelSourceKind.DOSE_RESPONSE_CURVE)
    out = await query.fetch(workspace_id=ws, channel=dr, run_ids=[rb], molecule_ids=[m2])
    assert list(out) == [m2]
    by_kind = {c.run.curve_id is not None: c for c in out[m2]}
    assert len(out[m2]) == 2  # the curve, plus the well-less endpoint (D1)
    assert by_kind[True].run.curve_id == curves[rb, m2]
    assert by_kind[True].batch_id is not None
    assert by_kind[True].dose is None
    assert by_kind[False].run.value == 3.3
    assert by_kind[False].well_id is None


@pytest.mark.asyncio
async def test_dr_endpoint_is_the_raw_row_with_its_qualifier_and_primary_tag(
    uow, session_factory, workspace_id
):
    """D1 — a dose-response column's reported endpoint is the raw well-less row:
    its computed (% inhibition) sibling never surfaces, its censored qualifier is
    kept, and it is tagged as the readout's primary intercept so only that
    intercept's column takes it."""
    from cellar.domain.research_organization.enums import ValueQualifier

    ws = workspace_id
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m")
        p = await seed.protocol(s, ws)
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        run = await seed.run(s, ws, p, date(2026, 1, 1))
        await seed.readout(s, ws, run, ic50, mol, 32.0, qualifier=">", wellless=True)
        await seed.readout(
            s,
            ws,
            run,
            ic50,
            mol,
            91.0,
            wellless=True,
            normalization="percent_inhibition",
            batch_id=await seed.batch(s, ws, mol, "B1"),  # the well-less key ignores the layer
        )
        await uow.commit()

    out = await SQLAlchemyColumnCandidateQuery(session_factory).fetch(
        workspace_id=ws,
        channel=_channel(p, ic50, ChannelSourceKind.DOSE_RESPONSE_CURVE),
        run_ids=[run],
        molecule_ids=None,
    )

    [endpoint] = out[mol]
    assert (endpoint.run.value, endpoint.run.qualifier, endpoint.run.unit) == (
        32.0,
        ValueQualifier.GT,
        "uM",
    )
    assert endpoint.run.curve_id is None
    assert endpoint.run.intercept_values == [
        {"spec": seed.DR_CONFIG["intercepts"][0], "value": 32.0}
    ]


async def _runs(
    query: SQLAlchemyColumnCandidateQuery,
    ws: uuid.UUID,
    channel: CampaignChannel,
    mol: uuid.UUID,
    run_ids: list[uuid.UUID] | None = None,
) -> list[ResolvedRun]:
    """One molecule's candidates, as the resolver reads them."""
    out = await query.fetch(workspace_id=ws, channel=channel, run_ids=run_ids, molecule_ids=[mol])
    return [c.run for c in out.get(mol, [])]


@pytest.mark.asyncio
async def test_multi_dr_protocol_disambiguates_by_readout_def(session_factory):
    """A protocol with two DR readouts sharing the same curve_type must
    surface only the curve fitted from each channel's own readout-def.

    Regression for the pre-033 bug where the query filtered by
    (workspace, molecule, protocol) only — two curves of curve_type=ic50
    on the same protocol would both come back and the selection rule
    would silently pick one. Post-033 the readout-def FK pins identity.
    """
    from cellar.domain.research_organization.campaign_channel import CampaignChannel
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )

    ws_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    molecule_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    rd_target_id = uuid.uuid4()
    rd_counter_id = uuid.uuid4()
    curve_target_id = uuid.uuid4()
    curve_counter_id = uuid.uuid4()

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
                "VALUES (:id, :ws, 'Multi-DR', 'Multi-DR', 'biochemical', 'active', "
                "false, 'uM', 'high', 1, 1, :user)"
            ),
            {"id": protocol_id, "ws": ws_id, "user": user_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, "
                "is_calculated) "
                "VALUES (:id, :proto, :name, 'numeric', 0, false)"
            ),
            {"id": rd_target_id, "proto": protocol_id, "name": "Target IC50"},
        )
        await session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, "
                "is_calculated) "
                "VALUES (:id, :proto, :name, 'numeric', 1, false)"
            ),
            {"id": rd_counter_id, "proto": protocol_id, "name": "Counter IC50"},
        )
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
                "run_date": date.today(),
                "user": user_id,
            },
        )
        # Two curves, same curve_type, different readout-defs, same
        # (run, molecule, batch). Pre-033 unique key (run, curve_type)
        # would have rejected this; post-033 the unique key includes
        # readout_definition_id so both rows coexist.
        for cid, rd_id, fitted in [
            (curve_target_id, rd_target_id, 0.50),
            (curve_counter_id, rd_counter_id, 12.5),
        ]:
            await session.execute(
                sa.text(
                    "INSERT INTO dose_response_curves "
                    "(id, workspace_id, molecule_id, batch_id, protocol_id, "
                    "run_id, readout_definition_id, curve_type, fitted_value, "
                    "hill_slope, top, bottom, r_squared, num_points) "
                    "VALUES (:id, :ws, :mol, :batch, :proto, :run, :rd, "
                    "'ic50', :fitted, 1.0, 100.0, 0.0, 0.95, 8)"
                ),
                {
                    "id": cid,
                    "ws": ws_id,
                    "mol": molecule_id,
                    "batch": batch_id,
                    "proto": protocol_id,
                    "run": run_id,
                    "rd": rd_id,
                    "fitted": fitted,
                },
            )

    query = SQLAlchemyColumnCandidateQuery(session_factory)

    target_channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="Target IC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_target_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    counter_channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="Counter IC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_counter_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=1,
    )

    target_candidates = await _runs(query, ws_id, target_channel, molecule_id)
    counter_candidates = await _runs(query, ws_id, counter_channel, molecule_id)

    assert len(target_candidates) == 1, (
        "Target channel must see exactly its own curve, not the sibling DR."
    )
    assert target_candidates[0].curve_id == curve_target_id
    assert target_candidates[0].value == pytest.approx(0.50)

    assert len(counter_candidates) == 1
    assert counter_candidates[0].curve_id == curve_counter_id
    assert counter_candidates[0].value == pytest.approx(12.5)


@pytest.mark.asyncio
async def test_curve_candidate_carries_chart_fields_into_snapshot(session_factory):
    """The curve_snapshot frozen on a CampaignMeasurement must carry the
    fields <DoseResponseChart> needs (curve_type, intercept_values, CI,
    fit warnings) — without them the campaign expand-dialog can't render
    via the same component as protocol-runs and search.
    """
    import json

    from cellar.application.screening.curve_snapshot import build_curve_snapshot
    from cellar.domain.research_organization.campaign_channel import CampaignChannel
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )

    ws_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.UUID("eeeeeeee-0000-0000-0000-000000000002")
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    molecule_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    rd_id = uuid.uuid4()
    curve_id = uuid.uuid4()

    intercept_values = [
        {
            "spec": {"kind": "ec", "level": 50.0, "basis": "absolute"},
            "value": 4.5,
            "at_bound": False,
            "confidence_interval_low": 3.8,
            "confidence_interval_high": 5.3,
        },
        {
            "spec": {"kind": "ec", "level": 90.0, "basis": "absolute"},
            "value": 41.2,
            "at_bound": False,
        },
    ]
    fit_warnings = ["wide_confidence_interval"]

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
                "VALUES (:id, :ws, 'Resz', 'Resz', 'cell_based', 'active', "
                "false, 'uM', 'high', 1, 1, :user)"
            ),
            {"id": protocol_id, "ws": ws_id, "user": user_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, "
                "is_calculated) "
                "VALUES (:id, :proto, 'Resazurin', 'dose_response', 0, false)"
            ),
            {"id": rd_id, "proto": protocol_id},
        )
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
                "run_date": date.today(),
                "user": user_id,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO dose_response_curves "
                "(id, workspace_id, molecule_id, batch_id, protocol_id, "
                "run_id, readout_definition_id, curve_type, fitted_value, "
                "hill_slope, top, bottom, r_squared, num_points, "
                "confidence_interval_low, confidence_interval_high, "
                "fit_quality_warnings, intercept_values) "
                "VALUES (:id, :ws, :mol, :batch, :proto, :run, :rd, "
                "'ec50', 4.5, 1.2, 95.0, -1.0, 0.92, 8, "
                ":ci_lo, :ci_hi, :warns, :ivs)"
            ),
            {
                "id": curve_id,
                "ws": ws_id,
                "mol": molecule_id,
                "batch": batch_id,
                "proto": protocol_id,
                "run": run_id,
                "rd": rd_id,
                "ci_lo": 3.8,
                "ci_hi": 5.3,
                "warns": json.dumps(fit_warnings),
                "ivs": json.dumps(intercept_values),
            },
        )

    query = SQLAlchemyColumnCandidateQuery(session_factory)
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="Resazurin EC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )

    candidates = await _runs(query, ws_id, channel, molecule_id)
    assert len(candidates) == 1
    cand = candidates[0]

    assert cand.curve_type == "ec50"
    assert cand.curve_confidence_interval_low == pytest.approx(3.8)
    assert cand.curve_confidence_interval_high == pytest.approx(5.3)
    assert cand.curve_fit_quality_warnings == fit_warnings
    assert cand.intercept_values == intercept_values

    snap = build_curve_snapshot(cand)
    assert snap is not None
    assert snap["curve_type"] == "ec50"
    assert snap["confidence_interval_low"] == pytest.approx(3.8)
    assert snap["confidence_interval_high"] == pytest.approx(5.3)
    assert snap["intercept_values"] == intercept_values
    assert snap["fit_quality_warnings"] == fit_warnings


@pytest.mark.asyncio
async def test_run_scope_excludes_other_runs_on_both_branches(session_factory):
    """Spec D4 — ``run_ids`` narrows the sweep to the campaign's own runs, on
    the dose-response branch (curves and their well-less endpoints) and the
    readout branch alike. ``None`` keeps the protocol-wide behaviour.
    """
    from cellar.domain.research_organization.campaign_channel import CampaignChannel
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )

    ws_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.UUID("eeeeeeee-0000-0000-0000-000000000004")
    protocol_id = uuid.uuid4()
    run_a_id = uuid.uuid4()
    run_b_id = uuid.uuid4()
    molecule_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    rd_id = uuid.uuid4()
    curve_a_id = uuid.uuid4()
    curve_b_id = uuid.uuid4()
    row_a_id = uuid.uuid4()
    row_b_id = uuid.uuid4()

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
                "VALUES (:id, :ws, 'Run Scope', 'Run Scope', 'biochemical', 'active', "
                "false, 'uM', 'high', 1, 1, :user)"
            ),
            {"id": protocol_id, "ws": ws_id, "user": user_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO readout_definitions "
                "(id, protocol_id, name, data_type, display_order, "
                "is_calculated, unit) "
                "VALUES (:id, :proto, 'IC50', 'dose_response', 0, false, 'uM')"
            ),
            {"id": rd_id, "proto": protocol_id},
        )
        for run_id, run_date in ((run_a_id, date(2026, 1, 1)), (run_b_id, date(2026, 6, 1))):
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
                    "run_date": run_date,
                    "user": user_id,
                },
            )
        # One curve and one well-less readout row per run, same molecule.
        for curve_id, run_id, fitted in ((curve_a_id, run_a_id, 1.0), (curve_b_id, run_b_id, 9.0)):
            await session.execute(
                sa.text(
                    "INSERT INTO dose_response_curves "
                    "(id, workspace_id, molecule_id, batch_id, protocol_id, "
                    "run_id, readout_definition_id, curve_type, fitted_value, "
                    "hill_slope, top, bottom, r_squared, num_points) "
                    "VALUES (:id, :ws, :mol, :batch, :proto, :run, :rd, "
                    "'ic50', :fitted, 1.0, 100.0, 0.0, 0.97, 8)"
                ),
                {
                    "id": curve_id,
                    "ws": ws_id,
                    "mol": molecule_id,
                    "batch": batch_id,
                    "proto": protocol_id,
                    "run": run_id,
                    "rd": rd_id,
                    "fitted": fitted,
                },
            )
        for row_id, run_id, value in ((row_a_id, run_a_id, 1.0), (row_b_id, run_b_id, 9.0)):
            await session.execute(
                sa.text(
                    "INSERT INTO readout_data "
                    "(id, workspace_id, run_id, well_id, molecule_id, "
                    "batch_id, readout_definition_id, value_numeric, "
                    "value_qualifier, is_outlier, is_computed, "
                    "normalization_applied) "
                    "VALUES (:id, :ws, :run, NULL, :mol, :batch, :rd, "
                    ":value, '=', false, false, NULL)"
                ),
                {
                    "id": row_id,
                    "ws": ws_id,
                    "run": run_id,
                    "mol": molecule_id,
                    "batch": batch_id,
                    "rd": rd_id,
                    "value": value,
                },
            )

    query = SQLAlchemyColumnCandidateQuery(session_factory)

    def _channel(source_kind: ChannelSourceKind) -> CampaignChannel:
        return CampaignChannel(
            campaign_id=uuid.uuid4(),
            label="IC50",
            protocol_id=protocol_id,
            readout_definition_id=rd_id,
            source_kind=source_kind,
            selection_rule=SelectionRule.LATEST_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=0,
        )

    dr_channel = _channel(ChannelSourceKind.DOSE_RESPONSE_CURVE)
    readout_channel = _channel(ChannelSourceKind.READOUT_DATA)

    # Dose-response column: its curves and its well-less endpoints (D1) alike.
    scoped = await _runs(query, ws_id, dr_channel, molecule_id, [run_a_id])
    assert [c.curve_id for c in scoped if c.curve_id] == [curve_a_id]
    assert [c.readout_id for c in scoped if c.readout_id] == [row_a_id]
    unscoped = await _runs(query, ws_id, dr_channel, molecule_id)
    assert sorted(c.curve_id for c in unscoped if c.curve_id) == sorted([curve_a_id, curve_b_id])
    assert sorted(c.readout_id for c in unscoped if c.readout_id) == sorted([row_a_id, row_b_id])

    # Readout column.
    scoped = await _runs(query, ws_id, readout_channel, molecule_id, [run_a_id])
    assert [c.readout_id for c in scoped] == [row_a_id]
    unscoped = await _runs(query, ws_id, readout_channel, molecule_id)
    assert sorted(c.readout_id for c in unscoped) == sorted([row_a_id, row_b_id])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("layers", "fitted"), [(["percent_inhibition"], "percent_inhibition"), ([], None)]
)
async def test_a_refreshed_curve_snapshot_names_the_layer_the_curve_fits(
    uow, session_factory, workspace_id, layers, fitted
):
    """Resolved from the channel's protocol by the fit's rule (the seed's DR config fits
    Signal's percent_inhibition), so a curve stored before the key existed has it too."""
    from cellar.application.screening.curve_snapshot import build_curve_snapshot

    ws = workspace_id
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        await seed.readout_def(s, p, name="Signal", normalizations=layers)
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response")
        run = await seed.run(s, ws, p, date(2026, 11, 19))
        await seed.curve(s, ws, p, run, mol, ic50)
        await uow.commit()

    out = await SQLAlchemyColumnCandidateQuery(session_factory).fetch(
        workspace_id=ws,
        channel=_channel(p, ic50, ChannelSourceKind.DOSE_RESPONSE_CURVE),
        run_ids=None,
        molecule_ids=None,
    )

    [candidate] = out[mol]
    assert candidate.run.curve_fitted_layer == fitted
    snapshot = build_curve_snapshot(candidate.run)
    assert snapshot is not None and snapshot["fitted_layer"] == fitted
