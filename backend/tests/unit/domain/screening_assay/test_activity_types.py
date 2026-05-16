"""ActivityValue carries multi-run aggregation context for cell rendering."""

import uuid
from datetime import date

from cellar.domain.screening_assay.activity_types import (
    ActivityValue,
    InterceptAggregate,
    RunSummary,
)
from cellar.domain.screening_assay.aggregation_types import AggregateStats


def test_activity_value_default_run_count_is_one():
    av = ActivityValue(value=0.5, qualifier="=", unit="uM", source="dose_response")
    assert av.run_count == 1
    assert av.runs is None
    assert av.intercept_aggregates is None
    assert av.disagreement_flag is False
    assert av.selection_rule is None


def test_activity_value_carries_multi_run_context():
    rid = uuid.uuid4()
    cid = uuid.uuid4()
    av = ActivityValue(
        value=0.18,
        qualifier="=",
        unit="uM",
        source="dose_response",
        run_count=3,
        selection_rule="latest_approved_run",
        runs=[
            RunSummary(
                run_id=rid,
                run_date=date(2026, 4, 12),
                curve_id=cid,
                curve_class="active",
                r_squared=0.99,
                intercept_values=[
                    {"spec": {"kind": "ic", "level": 50.0}, "value": 0.10}
                ],
            )
        ],
        intercept_aggregates=[
            InterceptAggregate(
                spec={"kind": "ic", "level": 50.0},
                selected_value=0.18,
                selected_qualifier="=",
                aggregate_stats=AggregateStats(
                    geometric_mean=0.18,
                    fold_range=4.2,
                    log_value_mean=-0.74,
                    log_value_sd=0.30,
                ),
                disagreement_flag=False,
            )
        ],
    )
    assert av.run_count == 3
    assert av.runs[0].r_squared == 0.99
    agg = av.intercept_aggregates[0]
    assert agg.aggregate_stats.fold_range == 4.2
    assert agg.disagreement_flag is False


def test_intercept_aggregate_disagreement_only_when_set():
    agg = InterceptAggregate(
        spec={"kind": "ic", "level": 50.0},
        selected_value=None,
        selected_qualifier="nd",
        aggregate_stats=None,
        disagreement_flag=True,
    )
    assert agg.disagreement_flag is True
