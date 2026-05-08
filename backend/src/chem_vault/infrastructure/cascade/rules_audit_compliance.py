"""Audit context cascade rules — intentionally empty.

The audit context (audit_entries, audit_operations) uses entity_id as a plain
UUID with no FK constraint back to any domain table. This is by design:
audit records must survive deletion of the entities they describe (21 CFR Part 11
alignment, append-only guarantee).

If the schema ever adds a real FK from an audit table to a domain table, add a
WARN rule here so the cascade preview surfaces the orphan-by-design behavior to
the admin.
"""
from chem_vault.infrastructure.cascade.registry import register_rules  # noqa: F401

# No rules registered — audit rows are intentionally FK-free.
