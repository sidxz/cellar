"""Tests for screening_assay cascade rules.

These tests deliberately do NOT use the _clear_for_test() fixture —
the registered rules must be present for the assertions to hold.
"""


def test_protocol_runs_rule_exists():
    import cellar.infrastructure.cascade.rules_screening_assay  # noqa: F401
    from cellar.infrastructure.cascade.registry import get_rules_for_parent

    rules = get_rules_for_parent("protocols")
    assert any(
        r.child_table == "runs" and r.action.value == "cascade"
        for r in rules
    )


def test_run_to_readout_data_cascades():
    """readout_data.well_id carries no FK constraint; the declared FK is
    readout_data.run_id → runs.  This is the correct owned-by relationship."""
    import cellar.infrastructure.cascade.rules_screening_assay  # noqa: F401
    from cellar.infrastructure.cascade.registry import get_rules_for_parent

    rules = get_rules_for_parent("runs")
    rd = next(r for r in rules if r.child_table == "readout_data")
    assert rd.action.value == "cascade"
