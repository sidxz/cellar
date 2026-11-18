import uuid

import pytest

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
from cellar.domain.research_organization.measurement_facts import (
    TEST_CONCENTRATION,
    Concentration,
    build_column_profile,
    describe_column,
    parse_concentration,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("10 µM", Concentration(10, "µM")),
        ("10 uM", Concentration(10, "µM")),
        ("500 nM", Concentration(500, "nM")),
        ("0.01 mM", Concentration(0.01, "mM")),
        (10, Concentration(10, "µM")),
        ("10", Concentration(10, "µM")),
        ({"value": 5, "unit": "nM"}, Concentration(5, "nM")),
    ],
)
def test_parse_accepted_forms(raw, expected):
    assert parse_concentration(raw) == expected


@pytest.mark.parametrize("raw", ["10 um", "ATP", "10 mg", None, True, {"value": "x"}, ""])
def test_parse_rejects(raw):
    assert parse_concentration(raw) is None


def test_bare_number_uses_default_unit():
    assert parse_concentration(3, "nM") == Concentration(3, "nM")


def test_same_as_across_units():
    assert Concentration(1, "µM").same_as(Concentration(1000, "nM"))
    assert not Concentration(1, "µM").same_as(Concentration(2, "µM"))


def test_label_constant():
    assert TEST_CONCENTRATION == "Test concentration"


def _channel(rule=SelectionRule.LATEST_RUN, conc=None):
    return CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="x",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=rule,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        test_concentration=conc,
    )


def _m(
    *, conc=None, reps=None, runs=1, series=False, basis=MeasurementBasis.MEASURED, reason=None
):
    return CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        value=None if reason else 1.0,
        value_qualifier=ValueQualifier.ND if reason else ValueQualifier.EQ,
        unit="%",
        protocol_name_snapshot="p",
        protocol_version_snapshot=1,
        test_concentration_value=conc,
        test_concentration_unit="µM" if conc is not None else None,
        replicate_count=reps,
        contributing_run_ids=[uuid.uuid4() for _ in range(runs)] if runs else None,
        basis=basis,
        concentration_series=series,
        unresolved_reason=reason,
    )


def _label(ch, ms, stage="Primary", readout="% inhibition"):
    return describe_column(
        channel=ch,
        rule=ch.selection_rule,
        stage_name=stage,
        readout_label=readout,
        profile=build_column_profile(ch, ms),
    ).label


def test_empty_column_reads_no_values_yet():
    ch = _channel()
    d = describe_column(
        channel=ch,
        rule=ch.selection_rule,
        stage_name="Primary",
        readout_label="% inhibition",
        profile=build_column_profile(ch, []),
    )
    assert d.short_label == "no values yet"
    assert d.label == "Primary · % inhibition · no values yet"


def test_label_case_k_primary():
    assert _label(_channel(), [_m(conc=10, reps=1)]) == (
        "Primary · % inhibition · single concentration 10 µM · 1 replicate · 1 run · latest run"
    )


def test_label_case_k_retest():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    ms = [_m(conc=10, reps=3, runs=3)]
    assert _label(ch, ms, "Retest") == (
        "Retest · % inhibition · single concentration 10 µM · mean of 3 replicates · 3 runs"
        " · mean across runs"
    )


def test_label_case_k_dose_response():
    ch = _channel(SelectionRule.GEOMETRIC_MEAN)
    ms = [_m(series=True, runs=2)]
    assert _label(ch, ms, "Confirmation", "IC50") == (
        "Confirmation · IC50 · dose-response · 2 runs · geometric mean"
    )


def test_label_mixed_replicates():
    ms = [_m(conc=10, reps=2), _m(conc=10, reps=3), *[_m(conc=10, reps=None) for _ in range(5)]]
    assert "2–3 replicates (5 not recorded)" in _label(_channel(), ms)  # noqa: RUF001


def test_label_reported_no_facts():
    ms = [_m(basis=MeasurementBasis.REPORTED)]
    assert " · reported value · replicates not recorded · " in _label(_channel(), ms)


def test_no_stage_drops_stage_part():
    assert _label(_channel(), [_m(conc=10, reps=1)], stage=None).startswith("% inhibition · ")


def test_short_label_drops_stage_and_readout():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    ms = [_m(conc=10, reps=3, runs=3)]
    d = describe_column(
        channel=ch,
        rule=ch.selection_rule,
        stage_name="Retest",
        readout_label="% inhibition",
        profile=build_column_profile(ch, ms),
    )
    assert d.short_label == (
        "single concentration 10 µM · mean of 3 replicates · 3 runs · mean across runs"
    )
    assert d.label == f"Retest · % inhibition · {d.short_label}"
    dr = _channel(SelectionRule.GEOMETRIC_MEAN)
    d = describe_column(
        channel=dr,
        rule=dr.selection_rule,
        stage_name=None,
        readout_label="IC50",
        profile=build_column_profile(dr, [_m(series=True, runs=2)]),
    )
    assert d.short_label == "dose-response · 2 runs · geometric mean"
    assert d.label == f"IC50 · {d.short_label}"


def test_needs_concentration_true_when_two_concentrations():
    ch = _channel()
    d = describe_column(
        channel=ch,
        rule=ch.selection_rule,
        stage_name=None,
        readout_label="r",
        profile=build_column_profile(ch, [_m(conc=10), _m(conc=5)]),
    )
    assert d.needs_concentration and d.design == "single_concentration_mixed"


def test_needs_concentration_true_for_several_concentrations_cell():
    ch = _channel()
    ms = [_m(conc=10), _m(reason=UnresolvedReason.SEVERAL_CONCENTRATIONS, runs=0, basis=None)]
    p = build_column_profile(ch, ms)
    assert p.several_concentrations == 1
    assert describe_column(
        channel=ch, rule=ch.selection_rule, stage_name=None, readout_label="r", profile=p
    ).needs_concentration


def test_needs_concentration_false_once_chosen():
    ch = _channel(conc=Concentration(10, "µM"))
    d = describe_column(
        channel=ch,
        rule=ch.selection_rule,
        stage_name=None,
        readout_label="r",
        profile=build_column_profile(ch, [_m(conc=10), _m(conc=5)]),
    )
    assert not d.needs_concentration


def test_chosen_concentration_reads_as_single_concentration():
    ch = _channel(conc=Concentration(10, "µM"))
    d = describe_column(
        channel=ch,
        rule=ch.selection_rule,
        stage_name=None,
        readout_label="r",
        profile=build_column_profile(ch, [_m(conc=10), _m(conc=5)]),
    )
    assert d.design == "single_concentration"
    assert d.short_label.startswith("single concentration 10 µM")
    assert len(d.concentrations) == 2
    assert not d.needs_concentration


def test_profile_ignores_no_fact_cells_and_counts_runs():
    ch = _channel()
    shared = uuid.uuid4()
    a, b = _m(conc=10, reps=2, runs=0), _m(conc=10, reps=2, runs=0)
    a.contributing_run_ids = [shared]
    b.source_run_id = shared
    nd = _m(runs=0, basis=None, reason=UnresolvedReason.NO_RUNS_AT_STAGE)
    p = build_column_profile(ch, [a, b, nd])
    assert p.run_count == 1 and p.replicate_not_recorded == 0
    assert p.concentrations == ((Concentration(10, "µM"), 2),)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("10 ug/mL", Concentration(10, "µg/mL")),
        ("10 µg/mL", Concentration(10, "µg/mL")),
        ("500 ng/mL", Concentration(500, "ng/mL")),
    ],
)
def test_parse_mass_concentration(raw, expected):
    assert parse_concentration(raw) == expected


def test_same_as_never_crosses_families():
    assert not Concentration(10, "µg/mL").same_as(Concentration(10, "µM"))
    assert Concentration(1, "mg/mL").same_as(Concentration(1000, "µg/mL"))


def test_mic_multiple_rejected():
    assert parse_concentration("4 xMIC") is None
    assert parse_concentration("4 ×MIC") is None


def test_mass_concentration_label_text():
    ch = _channel()
    m = _m(reps=1)
    m.test_concentration_value, m.test_concentration_unit = 10, "ug/mL"
    assert "single concentration 10 µg/mL" in _label(ch, [m])


def test_all_runs_column_says_so():
    ch = _channel()
    ch.resolve_from_all_runs = True
    d = describe_column(
        channel=ch,
        rule=ch.selection_rule,
        stage_name="Primary",
        readout_label="% inhibition",
        profile=build_column_profile(ch, [_m(conc=10, reps=1, runs=4)]),
    )
    assert d.short_label == (
        "single concentration 10 µM · 1 replicate · 4 runs · all runs of the protocol · latest run"
    )
    assert d.label == f"Primary · % inhibition · {d.short_label}"


def test_pinned_concentration_is_named_when_no_value_is_at_it():
    """Pinned to 10 µM, but the only dose left at the stage is 20 µM: every cell is
    untested, and the description names the pinned dose, not the one found."""
    ch = _channel(conc=Concentration(10, "µM"))
    untested = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=ch.id,
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit="-",
        protocol_name_snapshot="-",
        protocol_version_snapshot=0,
        concentrations_found=[Concentration(20, "µM")],
    )
    d = describe_column(
        channel=ch,
        rule=ch.selection_rule,
        stage_name=None,
        readout_label="r",
        profile=build_column_profile(ch, [untested]),
    )
    assert d.design == "single_concentration"
    assert d.short_label == "single concentration 10 µM · no values yet"
    assert d.concentrations == [{"value": 20.0, "unit": "µM", "count": 1}]


def test_value_count_counts_only_cells_with_a_numeric_value():
    """A column whose runs measured but every cell is ND (or excluded, or left
    unresolved) has run_count > 0 and value_count 0 — the stage-wide answer a
    paged reader needs to hide an all-ND column."""
    ch = _channel()
    tested_nd = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=ch.id,
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit="%",
        protocol_name_snapshot="p",
        protocol_version_snapshot=1,
        contributing_run_ids=[uuid.uuid4()],
        basis=MeasurementBasis.MEASURED,
    )
    excluded = CampaignMeasurement(
        result_id=uuid.uuid4(),
        channel_id=ch.id,
        value=None,
        value_qualifier=ValueQualifier.EXCLUDED,
        unit="%",
        protocol_name_snapshot="p",
        protocol_version_snapshot=1,
    )
    unresolved = _m(reason=UnresolvedReason.SEVERAL_CONCENTRATIONS)
    all_nd = build_column_profile(ch, [tested_nd, excluded, unresolved])
    assert all_nd.run_count == 1
    assert all_nd.value_count == 0

    censored = _m()
    censored.value_qualifier = ValueQualifier.GT
    override = _m()
    override.mark_manual_override("retyped from the notebook")
    profile = build_column_profile(ch, [tested_nd, _m(), censored, override])
    assert profile.value_count == 3
    d = describe_column(
        channel=ch, rule=ch.selection_rule, stage_name="P", readout_label="r", profile=profile
    )
    assert d.value_count == 3
