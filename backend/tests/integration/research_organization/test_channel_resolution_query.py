"""Integration smoke for the SQL ChannelResolutionQuery.

Deep verification of the join is exercised indirectly by the
close-campaign integration tests in Phase 5 (which seed real
curves/runs/protocols and round-trip through this query). This module
only confirms the class is wireable and returns an empty list when no
data matches, plus a multi-DR regression that pins the readout-def
disambiguation behavior.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa


@pytest.mark.asyncio
async def test_empty_candidates_for_unknown_molecule(session_factory):
    from cellar.domain.research_organization.campaign_channel import (
        CampaignChannel,
    )
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
    )

    query = SQLAlchemyChannelResolutionQuery(session_factory)
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    candidates = await query.fetch_candidates(
        workspace_id=uuid.uuid4(),
        channel=channel,
        molecule_id=uuid.uuid4(),
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_multi_dr_protocol_disambiguates_by_readout_def(session_factory):
    """A protocol with two DR readouts sharing the same curve_type must
    surface only the curve fitted from each channel's own readout-def.

    Regression for the pre-033 bug where the resolver filtered by
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
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
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
                "(id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, "
                "protocol_version, created_by) "
                "VALUES (:id, :ws, 'Multi-DR', 'biochemical', 'active', "
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

    query = SQLAlchemyChannelResolutionQuery(session_factory)

    target_channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="Target IC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_target_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    counter_channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="Counter IC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_counter_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=1,
    )

    target_candidates = await query.fetch_candidates(
        workspace_id=ws_id, channel=target_channel, molecule_id=molecule_id
    )
    counter_candidates = await query.fetch_candidates(
        workspace_id=ws_id, channel=counter_channel, molecule_id=molecule_id
    )

    assert len(target_candidates) == 1, (
        "Target channel must see exactly its own curve, not the sibling DR."
    )
    assert target_candidates[0].curve_id == curve_target_id
    assert target_candidates[0].value == pytest.approx(0.50)

    assert len(counter_candidates) == 1
    assert counter_candidates[0].curve_id == curve_counter_id
    assert counter_candidates[0].value == pytest.approx(12.5)


@pytest.mark.asyncio
async def test_empty_candidates_for_readout_source(session_factory):
    """Same smoke for the READOUT_DATA branch of the query."""
    from cellar.domain.research_organization.campaign_channel import (
        CampaignChannel,
    )
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
    )

    query = SQLAlchemyChannelResolutionQuery(session_factory)
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="% inhibition",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    candidates = await query.fetch_candidates(
        workspace_id=uuid.uuid4(),
        channel=channel,
        molecule_id=uuid.uuid4(),
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_curve_candidate_carries_chart_fields_into_snapshot(session_factory):
    """The curve_snapshot frozen on a CampaignMeasurement must carry the
    fields <DoseResponseChart> needs (curve_type, intercept_values, CI,
    fit warnings) — without them the campaign expand-dialog can't render
    via the same component as protocol-runs and search.
    """
    import json

    from cellar.application.research_organization.channel_resolution import (
        _build_curve_snapshot,
    )
    from cellar.domain.research_organization.campaign_channel import CampaignChannel
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
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
                "(id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, "
                "protocol_version, created_by) "
                "VALUES (:id, :ws, 'Resz', 'cell_based', 'active', "
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

    query = SQLAlchemyChannelResolutionQuery(session_factory)
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="Resazurin EC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )

    candidates = await query.fetch_candidates(
        workspace_id=ws_id, channel=channel, molecule_id=molecule_id
    )
    assert len(candidates) == 1
    cand = candidates[0]

    assert cand.curve_type == "ec50"
    assert cand.curve_confidence_interval_low == pytest.approx(3.8)
    assert cand.curve_confidence_interval_high == pytest.approx(5.3)
    assert cand.curve_fit_quality_warnings == fit_warnings
    assert cand.intercept_values == intercept_values

    snap = _build_curve_snapshot(cand)
    assert snap is not None
    assert snap["curve_type"] == "ec50"
    assert snap["confidence_interval_low"] == pytest.approx(3.8)
    assert snap["confidence_interval_high"] == pytest.approx(5.3)
    assert snap["intercept_values"] == intercept_values
    assert snap["fit_quality_warnings"] == fit_warnings


@pytest.mark.asyncio
async def test_endpoint_candidates_on_a_dr_channel(session_factory):
    """D1 — a dose-response channel can read the raw readout_data rows for its
    own readout definition (the summary-imported "reported endpoint").

    Pins three things at once on one fixture: the raw well-less row comes
    back while its computed sibling does not, the run-scoped variant honours
    ``run_ids``, and the DR branch of ``fetch_candidates_for_runs`` still
    returns only curves.
    """
    from cellar.domain.research_organization.campaign_channel import CampaignChannel
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
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
                "(id, workspace_id, name, protocol_type, status, "
                "is_locked, dose_unit, pos_control_signal, version, "
                "protocol_version, created_by) "
                "VALUES (:id, :ws, 'Reported IC50', 'biochemical', 'active', "
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
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="IC50",
        protocol_id=protocol_id,
        readout_definition_id=rd_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )

    endpoints = await query.fetch_endpoint_candidates(
        workspace_id=ws_id, channel=channel, molecule_id=mol_endpoint_id
    )
    assert sorted(c.readout_id for c in endpoints) == sorted(
        [raw_endpoint_id, other_run_endpoint_id]
    ), "The computed (%inhibition) sibling must not surface on a raw-layer channel."
    raw = next(c for c in endpoints if c.readout_id == raw_endpoint_id)
    assert raw.value == pytest.approx(32.0)
    assert raw.qualifier is ValueQualifier.GT
    assert raw.unit == "uM"
    assert raw.curve_id is None

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
    assert (
        await query.fetch_endpoint_candidates(
            workspace_id=ws_id,
            channel=channel,
            molecule_id=mol_welled_id,
            wellless_only=True,
        )
        == []
    )
    scoped_wellless = await query.fetch_endpoint_candidates_for_runs(
        workspace_id=ws_id,
        run_ids=[run_curve_id],
        readout_definition_id=rd_id,
        wellless_only=True,
    )
    assert mol_welled_id not in scoped_wellless
    assert [c.readout_id for c in scoped_wellless[mol_endpoint_id]] == [raw_endpoint_id]

    # Default (numeric readout channels) still reads per-well rows.
    welled = await query.fetch_endpoint_candidates(
        workspace_id=ws_id, channel=channel, molecule_id=mol_welled_id
    )
    assert [c.readout_id for c in welled] == [welled_row_id]
