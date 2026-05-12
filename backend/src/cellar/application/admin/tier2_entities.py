"""Entity types supported by Tier-2 admin force-cascade-delete.

Tier 1 (RESTRICT-by-default) applies to all registered admin-deletable
entities. Tier 2 is the opt-in destructive force-cascade path; it's
intentionally limited to a small set of entities where deep cascade is
a legitimate workflow.
"""

TIER2_ENTITY_TYPES: frozenset[str] = frozenset({"protocol", "run", "molecule"})
