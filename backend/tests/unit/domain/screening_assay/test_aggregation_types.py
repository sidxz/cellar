"""Aggregation type membership + back-compat re-export tests."""

from cellar.domain.screening_assay.aggregation_types import (
    SelectionRule,
)



def test_research_org_reexport_is_same_object():
    """Back-compat: existing imports from research_organization.enums still work."""
    from cellar.domain.research_organization.enums import (
        SelectionRule as RoSelectionRule,
    )

    assert RoSelectionRule is SelectionRule

