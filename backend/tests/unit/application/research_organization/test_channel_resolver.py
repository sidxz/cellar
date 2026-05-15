"""Unit tests for ChannelResolver — pure-domain selection/QC/hit logic."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
    ResolvedCandidate,
    _max_dose_from_raw,
    _resolve_intercept,
)
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey


class _FakeQuery:
    def __init__(self, candidates: list[ResolvedCandidate]) -> None:
        self._c = candidates

    async def fetch_candidates(self, *, workspace_id, channel, molecule_id):
        return list(self._c)


def _channel(
    rule: SelectionRule,
    *,
    threshold: HitCriterion | None = None,
    qc: dict | None = None,
    qualifier_handling: QualifierHandling | None = None,
    intercept_key: InterceptKey | None = None,
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="L",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=rule,
        qualifier_handling=qualifier_handling or QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        qc_filter=qc,
        hit_threshold=threshold,
        intercept_key=intercept_key,
    )


def _candidate(
    value: float,
    run_date: date | None = None,
    *,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    approved: bool = True,
    z_prime: float | None = 0.7,
    intercept_values: list[dict] | None = None,
) -> ResolvedCandidate:
    return ResolvedCandidate(
        value=value,
        qualifier=qualifier,
        unit="nM",
        run_id=uuid.uuid4(),
        run_date=run_date,
        run_approved=approved,
        z_prime=z_prime,
        protocol_name="X",
        protocol_version=1,
        curve_id=uuid.uuid4(),
        readout_id=None,
        intercept_values=intercept_values,
    )


def _iv(kind: str, level: float, value: float) -> dict:
    """JSONB-shaped intercept_values row, mirroring the persisted shape."""
    return {"spec": {"kind": kind, "level": level}, "value": value}


@pytest.mark.asyncio
async def test_latest_approved_run_picks_highest_run_date():
    ch = _channel(SelectionRule.LATEST_APPROVED_RUN)
    candidates = [
        _candidate(10.0, run_date=date(2026, 5, 1)),
        _candidate(20.0, run_date=date(2026, 4, 1)),
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 10.0  # the May date


@pytest.mark.asyncio
async def test_mean_across_runs_averages():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [_candidate(10.0), _candidate(20.0)]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 15.0


@pytest.mark.asyncio
async def test_geometric_mean_logspace():
    ch = _channel(SelectionRule.GEOMETRIC_MEAN)
    candidates = [_candidate(10.0), _candidate(1000.0)]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == pytest.approx(100.0)  # sqrt(10 * 1000)


@pytest.mark.asyncio
async def test_no_candidates_yields_nd():
    ch = _channel(SelectionRule.LATEST_APPROVED_RUN)
    resolver = ChannelResolver(_FakeQuery([]))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
    assert m.hit_call is None


@pytest.mark.asyncio
async def test_hit_threshold_computes_hit():
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        threshold=HitCriterion(readout_name="IC50", operator="lt", value=1000.0),
    )
    candidates = [_candidate(42.0, run_date=date(2026, 5, 1))]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.hit_call == HitCall.HIT


@pytest.mark.asyncio
async def test_qc_filter_drops_low_z_prime():
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        qc={"min_z_prime": 0.5, "require_approved": True},
    )
    candidates = [_candidate(99.0, run_date=date(2026, 5, 1), z_prime=0.3)]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value_qualifier == ValueQualifier.ND


@pytest.mark.asyncio
async def test_intercept_key_resolves_secondary_intercept_for_hit_call():
    """A channel that surfaces EC90 yields EC90's value as the cell value,
    and the threshold (`< 50`) compares against EC90 (80) → MISS."""
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        intercept_key=InterceptKey(kind="ec", level=90.0),
        threshold=HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
    )
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)],
        )
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.hit_call == HitCall.MISS
    assert m.value == 80.0  # the channel IS for EC90 — its value IS EC90


@pytest.mark.asyncio
async def test_intercept_key_none_keeps_legacy_primary_behavior():
    """No channel-level intercept_key → cell value is the primary fitted value."""
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        threshold=HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
    )
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)],
        )
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 2.0
    assert m.hit_call == HitCall.HIT


@pytest.mark.asyncio
async def test_intercept_key_missing_match_yields_no_hit_call():
    """Channel targets EC90 but the curve only has EC50 → cell value None, hit_call None."""
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        intercept_key=InterceptKey(kind="ec", level=90.0),
        threshold=HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
    )
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0)],  # no EC90 row
        )
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value is None
    assert m.hit_call is None


@pytest.mark.asyncio
async def test_intercept_key_aggregates_under_mean_selection():
    """MEAN_ACROSS_RUNS on a channel keyed to EC90 averages the EC90 values."""
    ch = _channel(
        SelectionRule.MEAN_ACROSS_RUNS,
        intercept_key=InterceptKey(kind="ec", level=90.0),
        threshold=HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
    )
    # EC90 values 80 and 100 average to 90 → MISS under lt 50.
    candidates = [
        _candidate(2.0, intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)]),
        _candidate(4.0, intercept_values=[_iv("ec", 50.0, 4.0), _iv("ec", 90.0, 100.0)]),
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 90.0  # mean of the EC90 values
    assert m.hit_call == HitCall.MISS


@pytest.mark.asyncio
async def test_qualifier_handling_excludes_qualified():
    ch = _channel(
        SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    )
    candidates = [
        _candidate(10.0, qualifier=ValueQualifier.EQ),
        _candidate(99.0, qualifier=ValueQualifier.GT),  # excluded
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 10.0  # GT 99.0 was excluded before averaging


# ---------------------------------------------------------------------------
# DR display honesty — Inactive curves emit ND, at_bound emits "> max_dose"
# ---------------------------------------------------------------------------


def _dr_candidate(
    value: float,
    *,
    run_date: date | None = None,
    curve_class: str | None = "full",
    intercept_values: list[dict] | None = None,
    raw_data: list[dict] | None = None,
) -> ResolvedCandidate:
    """ResolvedCandidate with the curve-shape fields the new resolver reads."""
    return ResolvedCandidate(
        value=value,
        qualifier=ValueQualifier.EQ,
        unit="uM",
        run_id=uuid.uuid4(),
        run_date=run_date,
        run_approved=True,
        z_prime=0.7,
        protocol_name="X",
        protocol_version=1,
        curve_id=uuid.uuid4(),
        readout_id=None,
        curve_class=curve_class,
        curve_top=100.0,
        curve_bottom=0.0,
        curve_hill_slope=-1.0,
        curve_r_squared=0.9,
        curve_raw_data=raw_data,
        intercept_values=intercept_values,
    )


class TestMaxDoseFromRaw:
    def test_picks_largest_positive_concentration(self):
        assert (
            _max_dose_from_raw(
                [
                    {"concentration": 0.1, "response": 5},
                    {"concentration": 50.0, "response": 90},
                    {"concentration": 1.0, "response": 40},
                ]
            )
            == 50.0
        )

    def test_accepts_x_y_shape_too(self):
        assert _max_dose_from_raw([{"x": 0.5, "y": 10}, {"x": 25, "y": 80}]) == 25.0

    def test_ignores_non_positive_and_non_finite(self):
        import math as _math

        assert (
            _max_dose_from_raw(
                [
                    {"concentration": -1, "response": 5},
                    {"concentration": 0, "response": 5},
                    {"concentration": _math.nan, "response": 5},
                    {"concentration": 7, "response": 5},
                ]
            )
            == 7.0
        )

    def test_returns_none_on_empty(self):
        assert _max_dose_from_raw(None) is None
        assert _max_dose_from_raw([]) is None


class TestResolveIntercept:
    def test_inactive_class_yields_nd_regardless_of_value(self):
        c = _dr_candidate(0.013, curve_class="inactive")
        value, qualifier = _resolve_intercept(c, None)
        assert value is None
        assert qualifier == ValueQualifier.ND

    def test_inactive_class_yields_nd_even_with_keyed_intercept(self):
        c = _dr_candidate(
            0.013,
            curve_class="inactive",
            intercept_values=[_iv("ec", 90, 0.005)],
        )
        value, qualifier = _resolve_intercept(c, InterceptKey(kind="ec", level=90.0))
        assert value is None
        assert qualifier == ValueQualifier.ND

    def test_keyed_intercept_at_bound_with_max_dose(self):
        c = _dr_candidate(
            5.0,
            curve_class="partial",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 50}, "value": 5.0, "at_bound": False},
                {"spec": {"kind": "ec", "level": 90}, "value": 1e-9, "at_bound": True},
            ],
            raw_data=[
                {"concentration": 0.1, "response": 10},
                {"concentration": 50.0, "response": 35},
            ],
        )
        value, qualifier = _resolve_intercept(c, InterceptKey(kind="ec", level=90.0))
        assert value == 50.0  # >max_dose
        assert qualifier == ValueQualifier.GT

    def test_keyed_intercept_at_bound_with_no_raw_data_yields_nd(self):
        c = _dr_candidate(
            5.0,
            curve_class="partial",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 90}, "value": 1e-9, "at_bound": True},
            ],
            raw_data=None,
        )
        value, qualifier = _resolve_intercept(c, InterceptKey(kind="ec", level=90.0))
        assert value is None
        assert qualifier == ValueQualifier.ND

    def test_keyed_intercept_healthy_returns_value_eq(self):
        c = _dr_candidate(
            5.0,
            curve_class="full",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 50}, "value": 5.0, "at_bound": False},
            ],
        )
        value, qualifier = _resolve_intercept(c, InterceptKey(kind="ec", level=50.0))
        assert value == 5.0
        assert qualifier == ValueQualifier.EQ

    def test_keyed_intercept_missing_match_yields_nd(self):
        c = _dr_candidate(
            5.0,
            curve_class="full",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 50}, "value": 5.0, "at_bound": False},
            ],
        )
        # Legacy curve without an EC90 intercept; protocol added it later.
        value, qualifier = _resolve_intercept(c, InterceptKey(kind="ec", level=90.0))
        assert value is None
        assert qualifier == ValueQualifier.ND

    def test_primary_intercept_at_bound_uses_intercept_values_zero(self):
        c = _dr_candidate(
            1e-9,
            curve_class="partial",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 50}, "value": 1e-9, "at_bound": True},
            ],
            raw_data=[{"concentration": 100.0, "response": 30}],
        )
        value, qualifier = _resolve_intercept(c, None)
        assert value == 100.0
        assert qualifier == ValueQualifier.GT

    def test_primary_legacy_no_intercept_values_returns_c_value(self):
        # Pre-033 curves that never had intercept_values persisted.
        c = _dr_candidate(7.5, curve_class="full", intercept_values=None)
        value, qualifier = _resolve_intercept(c, None)
        assert value == 7.5
        assert qualifier == ValueQualifier.EQ


@pytest.mark.asyncio
async def test_latest_approved_run_inactive_pick_emits_nd():
    ch = _channel(SelectionRule.LATEST_APPROVED_RUN)
    candidates = [
        _dr_candidate(
            0.013,
            run_date=date(2026, 5, 1),
            curve_class="inactive",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 0.013}],
        ),
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
    assert m.hit_call is None


@pytest.mark.asyncio
async def test_latest_approved_run_at_bound_pick_emits_gt_max_dose():
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        intercept_key=InterceptKey(kind="ec", level=90.0),
    )
    candidates = [
        _dr_candidate(
            5.0,
            run_date=date(2026, 5, 1),
            curve_class="partial",
            intercept_values=[
                {"spec": {"kind": "ec", "level": 90}, "value": 1e-9, "at_bound": True},
            ],
            raw_data=[
                {"concentration": 0.1, "response": 10},
                {"concentration": 50.0, "response": 35},
            ],
        ),
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 50.0
    assert m.value_qualifier == ValueQualifier.GT


@pytest.mark.asyncio
async def test_mean_across_runs_drops_inactive_from_aggregate():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [
        _dr_candidate(
            10.0,
            curve_class="full",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 10.0}],
        ),
        _dr_candidate(
            20.0,
            curve_class="full",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 20.0}],
        ),
        # Inactive scalar must NOT pollute the mean.
        _dr_candidate(
            0.5,
            curve_class="inactive",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 0.5}],
        ),
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 15.0  # mean of the healthy pair only


@pytest.mark.asyncio
async def test_mean_across_runs_all_inactive_emits_nd():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [
        _dr_candidate(
            10.0,
            curve_class="inactive",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 10.0}],
        ),
        _dr_candidate(
            20.0,
            curve_class="inactive",
            intercept_values=[{"spec": {"kind": "ec", "level": 50}, "value": 20.0}],
        ),
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
