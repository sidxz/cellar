"""CascadeRule — a single inbound-FK edge in the cascade graph."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CascadeAction(StrEnum):
    CASCADE = "cascade"
    SET_NULL = "set_null"
    BLOCK = "block"
    WARN = "warn"


@dataclass(frozen=True)
class CascadeRule:
    """Declares: 'rows in `child_table.fk_column` referencing `parent_table.id`
    should be handled with `action` when the parent is deleted.'

    Owned by the module that adds the FK. A new module that adds an FK to an
    existing entity declares its own rule here — no edits to the existing
    module's cascade.py.
    """
    child_table: str
    fk_column: str
    parent_table: str
    action: CascadeAction
    label_field: str | None = None  # column on child_table used for named heads
    display_label: str = ""         # group label in preview, e.g., "Runs"
    recurse_into_entity: str | None = None  # parent_table for recursive walking
