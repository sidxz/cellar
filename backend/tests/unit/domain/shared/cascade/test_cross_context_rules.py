"""Tests for Tier-2 cascade rules across chemical_registration, inventory,
and research_organization contexts.

These tests import the cascade modules directly (bypassing the DI container)
to keep the tests fast and DB-free.
"""


def test_batches_cascade_under_molecule():
    """rules_inventory.py must register a CASCADE rule for batches → molecules."""
    import cellar.infrastructure.cascade.rules_inventory  # noqa: F401
    from cellar.infrastructure.cascade.registry import get_rules_for_parent

    rules = get_rules_for_parent("molecules")
    assert any(
        r.child_table == "batches" and r.action.value == "cascade"
        for r in rules
    )


def test_saved_searches_set_null_under_project():
    """rules_research_organization.py must register a SET_NULL rule for
    saved_searches.project_id → projects.

    Note: the spec originally referenced protocols; the actual FK is to projects.
    """
    import cellar.infrastructure.cascade.rules_research_organization  # noqa: F401
    from cellar.infrastructure.cascade.registry import get_rules_for_parent

    rules = get_rules_for_parent("projects")
    assert any(
        r.child_table == "saved_searches" and r.action.value == "set_null"
        for r in rules
    )
