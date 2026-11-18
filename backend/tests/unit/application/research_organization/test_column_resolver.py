"""ColumnResolver — one bulk, pure resolver from candidate readings to campaign cells.

Readings group by (run, concentration) first (spec §6.4): replicate wells combine
per run, a concentration series never feeds a single-point column, and the
column's rule combines runs only at one concentration.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from cellar.application.research_organization.column_resolution import (
    Candidate,
    ColumnResolver,
    resolution_run_ids,
)
from cellar.application.screening.run_aggregation import ResolvedRun
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    MeasurementBasis,
    QualifierHandling,
    SelectionRule,
    UnresolvedReason,
    ValueQualifier,
)
from cellar.domain.research_organization.measurement_facts import Concentration
from cellar.domain.research_organization.source_ref import SeedRun
from cellar.domain.research_organization.stage_evaluation import _is_tested_nd

MOL = uuid.uuid4()
UM10 = Concentration(10.0, "µM")
UM1 = Concentration(1.0, "µM")
D1, D2, D3 = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)


def _channel(
    rule: SelectionRule = SelectionRule.LATEST_RUN,
    *,
    source_kind: ChannelSourceKind = ChannelSourceKind.READOUT_DATA,
    test_concentration: Concentration | None = None,
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="L",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=source_kind,
        selection_rule=rule,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        test_concentration=test_concentration,
    )


def _reading(
    value: float,
    run_id: uuid.UUID,
    run_date: date = D1,
    *,
    dose: Concentration | None = UM10,
    well: bool = True,
    replicate_count: int | None = None,
    batch_id: uuid.UUID | None = None,
    mol: uuid.UUID = MOL,
    created_at: datetime | None = None,
) -> Candidate:
    """One readout row: a well reading, or (``well=False``) a reported value."""
    return Candidate(
        run=ResolvedRun(
            run_id=run_id,
            run_date=run_date,
            run_approved=True,
            curve_id=None,
            value=value,
            qualifier=ValueQualifier.EQ,
            unit="%",
            z_prime=0.7,
            protocol_name="P",
            protocol_version=1,
            readout_id=uuid.uuid4(),
        ),
        molecule_id=mol,
        batch_id=batch_id,
        well_id=uuid.uuid4() if well else None,
        dose=dose,
        replicate_count=replicate_count,
        run_created_at=created_at,
    )


def _curve(
    value: float,
    run_id: uuid.UUID,
    run_date: date = D1,
    *,
    curve_class: str = "full",
    batch_id: uuid.UUID | None = None,
    approved: bool = True,
    mol: uuid.UUID = MOL,
) -> Candidate:
    return Candidate(
        run=ResolvedRun(
            run_id=run_id,
            run_date=run_date,
            run_approved=approved,
            curve_id=uuid.uuid4(),
            value=value,
            qualifier=ValueQualifier.EQ,
            unit="µM",
            z_prime=0.7,
            protocol_name="P",
            protocol_version=1,
            readout_id=None,
            curve_class=curve_class,
            curve_top=100.0,
            curve_bottom=0.0,
            curve_hill_slope=1.0,
        ),
        molecule_id=mol,
        batch_id=batch_id,
        well_id=None,
        dose=None,
        replicate_count=None,
    )


def _resolve_all(
    channel: CampaignChannel, candidates: list[Candidate], molecules: list[uuid.UUID]
) -> dict[uuid.UUID, CampaignMeasurement]:
    by_mol: dict[uuid.UUID, list[Candidate]] = {}
    for c in candidates:
        by_mol.setdefault(c.molecule_id, []).append(c)
    return ColumnResolver().resolve_column(
        channel=channel,
        molecule_ids=molecules,
        candidates=by_mol,
        result_id_by_molecule={m: uuid.uuid4() for m in molecules},
    )


def _resolve(channel: CampaignChannel, candidates: list[Candidate]) -> CampaignMeasurement:
    return _resolve_all(channel, candidates, [MOL])[MOL]


def _assert_bare(m: CampaignMeasurement) -> None:
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
    assert m.source_run_id is None
    assert m.curve_snapshot is None
    assert not _is_tested_nd(m)


# --- readout columns -----------------------------------------------------------


@pytest.mark.parametrize("newer_first", [True, False])
def test_latest_run_tie_on_date_goes_to_run_created_later(newer_first):
    a, b = uuid.uuid4(), uuid.uuid4()
    older = _reading(10, a, D1, created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC))
    newer = _reading(20, b, D1, created_at=datetime(2026, 1, 1, 9, 6, tzinfo=UTC))
    m = _resolve(
        _channel(SelectionRule.LATEST_RUN), [newer, older] if newer_first else [older, newer]
    )
    assert m.value == 20
    assert m.source_run_id == b


def test_replicate_wells_combine_per_run_then_rule():
    """Latest run no longer picks one well: the latest run's wells average."""
    a, b = uuid.uuid4(), uuid.uuid4()
    m = _resolve(
        _channel(SelectionRule.LATEST_RUN),
        [_reading(10, a, D1), _reading(20, a, D1), _reading(30, b, D2), _reading(50, b, D2)],
    )
    assert m.value == pytest.approx(40.0)
    assert m.value_qualifier == ValueQualifier.EQ
    assert m.source_run_id == b
    assert m.contributing_run_ids == [b]
    assert m.replicate_count == 2
    assert m.basis == MeasurementBasis.MEASURED
    assert (m.test_concentration_value, m.test_concentration_unit) == (10.0, "µM")
    assert m.concentration_series is False


def test_mean_across_runs_averages_runs_not_wells():
    a, b = uuid.uuid4(), uuid.uuid4()
    m = _resolve(
        _channel(SelectionRule.MEAN_ACROSS_RUNS),
        [_reading(10, a, D1), _reading(20, a, D1), _reading(30, a, D1), _reading(50, b, D2)],
    )
    assert m.value == pytest.approx(35.0)  # (20 + 50) / 2, not (10+20+30+50) / 4
    assert m.source_run_id is None
    assert set(m.contributing_run_ids or []) == {a, b}
    assert m.replicate_count == 4


def test_concentration_series_never_feeds_single_point():
    series, single = uuid.uuid4(), uuid.uuid4()
    dose_response_wells = [
        _reading(5, series, D2, dose=UM1),
        _reading(40, series, D2, dose=UM10),
        _reading(90, series, D2, dose=Concentration(100.0, "µM")),
    ]
    _assert_bare(_resolve(_channel(), dose_response_wells))

    m = _resolve(_channel(), [*dose_response_wells, _reading(42, single, D1, dose=UM10)])
    assert m.value == pytest.approx(42.0)
    assert m.contributing_run_ids == [single]


def test_two_concentrations_unresolved_and_flagged():
    a, b = uuid.uuid4(), uuid.uuid4()
    other = uuid.uuid4()
    out = _resolve_all(
        _channel(SelectionRule.MEAN_ACROSS_RUNS),
        [
            _reading(40, a, D1, dose=UM10),
            _reading(20, b, D2, dose=UM1),
            _reading(33, a, D1, dose=UM10, mol=other),
        ],
        [MOL, other],
    )
    _assert_bare(out[MOL])
    assert out[MOL].unresolved_reason == UnresolvedReason.SEVERAL_CONCENTRATIONS
    # A compound measured at one concentration still resolves, carrying it.
    assert out[other].value == pytest.approx(33.0)
    assert out[other].unresolved_reason is None
    assert out[other].test_concentration_value == 10.0


def test_not_recorded_concentration_is_its_own_bucket():
    a, b = uuid.uuid4(), uuid.uuid4()
    m = _resolve(_channel(), [_reading(40, a, D1, dose=UM10), _reading(20, b, D2, dose=None)])
    assert m.unresolved_reason == UnresolvedReason.SEVERAL_CONCENTRATIONS


def test_test_concentration_selects_dose():
    a, b = uuid.uuid4(), uuid.uuid4()
    readings = [_reading(40, a, D1, dose=UM10), _reading(20, b, D2, dose=UM1)]
    m = _resolve(_channel(test_concentration=Concentration(10_000.0, "nM")), readings)
    assert m.value == pytest.approx(40.0)
    assert m.contributing_run_ids == [a]
    assert (m.test_concentration_value, m.test_concentration_unit) == (10.0, "µM")
    assert m.unresolved_reason is None
    # Nothing at the chosen concentration: untested, no reason.
    _assert_bare(_resolve(_channel(test_concentration=Concentration(3.0, "µM")), readings))


UM50 = Concentration(50.0, "µM")


def _two_conc_compounds(n: int = 3):
    a, b = uuid.uuid4(), uuid.uuid4()
    mols = [uuid.uuid4() for _ in range(n)]
    readings = [
        r
        for m in mols
        for r in (_reading(40, a, D1, dose=UM10, mol=m), _reading(20, b, D2, dose=UM50, mol=m))
    ]
    return mols, readings


def test_case_m_all_compounds_two_concentrations_lists_both():
    from cellar.domain.research_organization.measurement_facts import (
        build_column_profile,
        describe_column,
    )

    mols, readings = _two_conc_compounds(3)
    ch = _channel()
    out = _resolve_all(ch, readings, mols)
    assert all(
        m.unresolved_reason == UnresolvedReason.SEVERAL_CONCENTRATIONS for m in out.values()
    )
    assert all(m.concentrations_found == [UM10, UM50] for m in out.values())
    d = describe_column(
        channel=ch,
        stage_name=None,
        readout_label="r",
        profile=build_column_profile(ch, out.values()),
    )
    assert [(c["value"], c["count"]) for c in d.concentrations] == [(10.0, 3), (50.0, 3)]
    assert d.needs_concentration


def test_case_m_choosing_one_resolves_every_cell():
    mols, readings = _two_conc_compounds(3)
    out = _resolve_all(_channel(test_concentration=UM50), readings, mols)
    assert all(
        m.unresolved_reason is None and m.value == pytest.approx(20.0) for m in out.values()
    )
    assert all(m.concentrations_found == [UM10, UM50] for m in out.values())


def test_clearing_choice_restores_list_and_flag():
    from cellar.domain.research_organization.measurement_facts import (
        build_column_profile,
        describe_column,
    )

    mols, readings = _two_conc_compounds(2)

    def needs(ch):
        out = _resolve_all(ch, readings, mols)
        return describe_column(
            channel=ch,
            stage_name=None,
            readout_label="r",
            profile=build_column_profile(ch, out.values()),
        )

    assert not needs(_channel(test_concentration=UM10)).needs_concentration
    restored = needs(_channel())
    assert restored.needs_concentration
    assert len(restored.concentrations) == 2


def test_series_run_doses_not_listed():
    series, single = uuid.uuid4(), uuid.uuid4()
    readings = [
        _reading(5, series, D2, dose=UM1),
        _reading(40, series, D2, dose=UM10),
        _reading(42, single, D1, dose=UM50),
    ]
    m = _resolve(_channel(), readings)
    assert m.concentrations_found == [UM50]


def test_partial_overlap_counts_over_compounds():
    from cellar.domain.research_organization.measurement_facts import build_column_profile

    a, b = uuid.uuid4(), uuid.uuid4()
    m1, m2, m3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    readings = [
        _reading(1, a, D1, dose=UM10, mol=m1),
        _reading(1, b, D2, dose=UM50, mol=m1),
        _reading(1, a, D1, dose=UM10, mol=m2),
        _reading(1, b, D2, dose=UM50, mol=m3),
    ]
    ch = _channel()
    out = _resolve_all(ch, readings, [m1, m2, m3])
    p = build_column_profile(ch, out.values())
    assert [(c.value, n) for c, n in p.concentrations if c] == [(10.0, 2), (50.0, 2)]


def test_concentrations_found_set_on_resolved_and_unresolved_cells():
    a, b = uuid.uuid4(), uuid.uuid4()
    one, two = uuid.uuid4(), uuid.uuid4()
    out = _resolve_all(
        _channel(),
        [
            _reading(1, a, D1, dose=UM10, mol=one),
            _reading(1, a, D1, dose=UM10, mol=two),
            _reading(1, b, D2, dose=UM50, mol=two),
            _reading(1, b, D2, dose=None, mol=two),
        ],
        [one, two],
    )
    assert out[one].unresolved_reason is None
    assert out[one].concentrations_found == [UM10]
    assert out[two].unresolved_reason == UnresolvedReason.SEVERAL_CONCENTRATIONS
    assert out[two].concentrations_found == [UM10, UM50]  # not-recorded never listed
    dr = _resolve(_channel(source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE), [_curve(1, a)])
    assert dr.concentrations_found is None


def test_wellless_reported_uses_recorded_replicates():
    a = uuid.uuid4()
    r = _reading(7.5, a, D1, well=False, replicate_count=3)
    m = _resolve(_channel(), [r])
    assert m.value == pytest.approx(7.5)
    assert m.replicate_count == 3
    assert m.basis == MeasurementBasis.REPORTED
    assert m.source_readout_id == r.run.readout_id
    # None recorded means "not recorded", never 1.
    assert _resolve(_channel(), [_reading(7.5, a, D1, well=False)]).replicate_count is None


def test_replicate_total_null_when_any_group_unrecorded():
    a, b = uuid.uuid4(), uuid.uuid4()
    mean = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    both = [_reading(10, a, D1, well=False, replicate_count=3)]
    m = _resolve(mean, [*both, _reading(20, b, D2, well=False, replicate_count=2)])
    assert m.replicate_count == 5
    m = _resolve(mean, [*both, _reading(20, b, D2, well=False)])
    assert m.value == pytest.approx(15.0)
    assert m.replicate_count is None


def test_mixed_basis_when_rule_combines_wells_and_reported():
    a, b = uuid.uuid4(), uuid.uuid4()
    m = _resolve(
        _channel(SelectionRule.MEAN_ACROSS_RUNS),
        [_reading(10, a, D1), _reading(20, b, D2, well=False, replicate_count=2)],
    )
    assert m.basis == MeasurementBasis.MIXED
    assert m.replicate_count == 3


def test_batch_ids_from_contributors():
    """Case B: the confirmation traces to its new batch."""
    old_run, new_run = uuid.uuid4(), uuid.uuid4()
    b1, b2 = uuid.uuid4(), uuid.uuid4()
    readings = [
        _reading(10, old_run, D1, batch_id=b1),
        _reading(20, new_run, D2, batch_id=b2),
        _reading(22, new_run, D2, batch_id=b2),
        _reading(24, new_run, D2, batch_id=None),
    ]
    assert _resolve(_channel(SelectionRule.LATEST_RUN), readings).batch_ids == [b2]
    mean = _resolve(_channel(SelectionRule.MEAN_ACROSS_RUNS), readings)
    assert mean.batch_ids == sorted([b1, b2])


def test_case_l_empty_run_contributes_nothing():
    """An empty run in scope has no candidates: it changes no value, no run
    count, and makes nothing tested."""
    a = uuid.uuid4()
    untested = uuid.uuid4()
    out = _resolve_all(_channel(), [_reading(40, a, D1)], [MOL, untested])
    assert out[MOL].value == pytest.approx(40.0)
    assert out[MOL].contributing_run_ids == [a]
    _assert_bare(out[untested])
    assert out[untested].unresolved_reason is None


# --- dose-response columns -------------------------------------------------------


def test_dr_column_series_flag_and_endpoint_fallback():
    dr = _channel(SelectionRule.LATEST_RUN, source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE)
    fitted, reported, both = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    run = uuid.uuid4()
    batch = uuid.uuid4()
    out = _resolve_all(
        dr,
        [
            _curve(0.5, run, D2, batch_id=batch, mol=fitted),
            _reading(1.2, run, D2, well=False, replicate_count=2, dose=None, mol=reported),
            _curve(0.8, run, D1, mol=both),
            _reading(9.9, run, D2, well=False, dose=None, mol=both),
        ],
        [fitted, reported, both],
    )
    assert out[fitted].value == pytest.approx(0.5)
    assert out[fitted].concentration_series is True
    assert out[fitted].basis == MeasurementBasis.MEASURED
    assert out[fitted].batch_ids == [batch]
    assert out[fitted].curve_snapshot is not None

    assert out[reported].value == pytest.approx(1.2)
    assert out[reported].concentration_series is True
    assert out[reported].basis == MeasurementBasis.REPORTED
    assert out[reported].replicate_count == 2

    # D1: a QC-passing curve wins over a reported endpoint.
    assert out[both].value == pytest.approx(0.8)


def test_dr_endpoint_fallback_only_when_no_curve_passes_qc():
    dr = _channel(SelectionRule.LATEST_RUN, source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE)
    dr.qc_filter = {"require_approved": True}
    run = uuid.uuid4()
    m = _resolve(
        dr,
        [_curve(0.8, uuid.uuid4(), D1, approved=False), _reading(9.9, run, D2, well=False)],
    )
    assert m.value == pytest.approx(9.9)


def test_tested_nd_still_miss():
    dr = _channel(SelectionRule.LATEST_RUN, source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE)
    c = _curve(0.013, uuid.uuid4(), D1, curve_class="inactive")
    m = _resolve(dr, [c])
    assert m.value_qualifier == ValueQualifier.ND
    assert m.source_curve_id == c.run.curve_id
    assert m.source_run_id == c.run.run_id
    assert m.curve_snapshot is not None
    assert _is_tested_nd(m)
    assert m.concentration_series is True


def test_manual_pick_stays_untested():
    dr = _channel(SelectionRule.MANUAL_PICK, source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE)
    m = _resolve(dr, [_curve(5.0, uuid.uuid4(), D1)])
    assert m.value_qualifier == ValueQualifier.ND
    assert m.source_curve_id is None
    assert m.curve_snapshot is None
    assert not _is_tested_nd(m)


# --- resolution scope (§6.3) -------------------------------------------------------


def _campaign(*seed_runs: SeedRun) -> Campaign:
    c = Campaign.create(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="C",
        description=None,
        created_by=uuid.uuid4(),
    )
    c.seed_runs = list(seed_runs)
    return c


def test_resolution_run_ids_scope():
    stage, other_stage = uuid.uuid4(), uuid.uuid4()
    ch = _channel()
    p = ch.protocol_id
    r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    campaign = _campaign(
        SeedRun(r1, p, (stage,)), SeedRun(r2, p, (other_stage,)), SeedRun(r3, p, ())
    )

    ch.stage_id = stage
    assert resolution_run_ids(campaign, ch) == [r1]
    ch.stage_id = uuid.uuid4()  # a stage with no runs never falls back
    assert resolution_run_ids(campaign, ch) == "none"
    ch.resolve_from_all_runs = True
    assert resolution_run_ids(campaign, ch) is None

    ch.resolve_from_all_runs = False
    ch.stage_id = None  # a campaign column reads every campaign run of its protocol
    assert resolution_run_ids(campaign, ch) == [r1, r2, r3]
    ch.protocol_id = uuid.uuid4()  # ... or protocol-wide when there are none
    assert resolution_run_ids(campaign, ch) is None


def test_qc_pass_every_contributor_approved_with_z_prime_at_least_half():
    """The default QC heuristic (run approved, z′ ≥ 0.5 when present) over the readings
    behind the value only; a cell with no readings has no QC flag."""
    a, b = uuid.uuid4(), uuid.uuid4()
    old, new = _reading(10, a, D1), _reading(20, b, D2)

    def with_run(c: Candidate, **kw: object) -> Candidate:
        return replace(c, run=replace(c.run, **kw))

    mean = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    assert _resolve(mean, [old, new]).qc_pass is True
    assert _resolve(mean, [with_run(old, z_prime=0.49), new]).qc_pass is False
    assert _resolve(mean, [with_run(old, run_approved=False), new]).qc_pass is False
    assert _resolve(mean, [with_run(old, z_prime=None), new]).qc_pass is True
    # Latest run: the older, failing run does not contribute.
    assert _resolve(_channel(), [with_run(old, z_prime=0.1), new]).qc_pass is True
    assert _resolve(_channel(), []).qc_pass is None
