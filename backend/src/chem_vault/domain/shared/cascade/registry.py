"""Process-global registry of CascadeRules.

Modules call `register_rules(*rules)` at import time. Lookup by parent_table.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from chem_vault.domain.shared.cascade.rules import CascadeRule


_BY_PARENT: dict[str, list[CascadeRule]] = defaultdict(list)


def register_rules(*rules: CascadeRule) -> None:
    for r in rules:
        _BY_PARENT[r.parent_table].append(r)


def get_rules_for_parent(parent_table: str) -> list[CascadeRule]:
    return list(_BY_PARENT.get(parent_table, []))


def all_rules() -> list[CascadeRule]:
    return [r for rules in _BY_PARENT.values() for r in rules]


def _clear_for_test() -> None:
    """Test-only: reset the registry."""
    _BY_PARENT.clear()
