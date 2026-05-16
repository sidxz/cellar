"""Aggregation type membership + back-compat re-export tests."""

from cellar.domain.screening_assay.aggregation_types import (
    AggregateStats,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)


def test_selection_rule_includes_best_r_squared():
    assert SelectionRule.BEST_R_SQUARED.value == "best_r_squared"


def test_selection_rule_carries_legacy_members():
    for name in (
        "LATEST_APPROVED_RUN",
        "MEAN_ACROSS_RUNS",
        "GEOMETRIC_MEAN",
        "MANUAL_PICK",
        "BEST_R_SQUARED",
    ):
        assert hasattr(SelectionRule, name), name


def test_research_org_reexport_is_same_object():
    """Back-compat: existing imports from research_organization.enums still work."""
    from cellar.domain.research_organization.enums import (
        SelectionRule as RoSelectionRule,
    )

    assert RoSelectionRule is SelectionRule


def test_qualifier_handling_members():
    """Preserves the existing 3-member set; campaign code uses TREAT_AS_LIMIT."""
    assert QualifierHandling.EXCLUDE_QUALIFIED.value == "exclude_qualified"
    assert QualifierHandling.INCLUDE_QUALIFIED.value == "include_qualified"
    assert QualifierHandling.TREAT_AS_LIMIT.value == "treat_as_limit"


def test_value_qualifier_members():
    """Existing string values are chemistry-symbol style; persisted to DB."""
    assert ValueQualifier.EQ.value == "="
    assert ValueQualifier.LT.value == "<"
    assert ValueQualifier.GT.value == ">"
    assert ValueQualifier.ND.value == "nd"
    assert ValueQualifier.EXCLUDED.value == "excluded"


def test_aggregate_stats_is_frozen_dataclass_with_four_fields():
    s = AggregateStats(
        geometric_mean=0.18,
        fold_range=4.2,
        log_value_mean=-0.74,
        log_value_sd=0.30,
    )
    assert s.geometric_mean == 0.18
    assert s.fold_range == 4.2
    assert s.log_value_mean == -0.74
    assert s.log_value_sd == 0.30


def test_aggregate_stats_all_none_is_valid():
    """When no EQ runs exist, all stats are None — valid construction."""
    s = AggregateStats(
        geometric_mean=None, fold_range=None, log_value_mean=None, log_value_sd=None
    )
    assert s.geometric_mean is None
