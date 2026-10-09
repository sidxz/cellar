"""Rewrite of stored unit spellings (migrations 088, 090). Idempotent. Sync: Alembic runs sync."""

from __future__ import annotations

import json

from sqlalchemy import Connection, text

from cellar.domain.research_organization.criteria_walker import walk_criteria
from cellar.domain.shared.units import canonical_unit

# Free-text display units on live definitions only. Never rewritten:
# - ``campaign_measurement.unit``: a frozen snapshot (closed campaigns are records, guarded by a
#   lock trigger); the campaign results filter compares units by canonical spelling instead.
# - ``test_concentration_unit`` / ``dose_unit`` and the inventory concentration columns: they hold
#   ConcentrationUnit enum values ("uM") that code parses back.
_DISPLAY_UNIT_COLUMNS = (
    ("readout_definitions", "unit"),
    ("condition_definitions", "unit"),
)


def _template_units(items: list | None) -> tuple[list | None, bool]:
    if not items:
        return items, False
    out, changed = [], False
    for item in items:
        new = canonical_unit(item.get("unit"))
        if new != item.get("unit"):
            item, changed = {**item, "unit": new}, True
        out.append(item)
    return out, changed


def rewrite_stored_units(conn: Connection) -> None:
    for table, column in _DISPLAY_UNIT_COLUMNS:
        for (old,) in conn.execute(
            text(f"select distinct {column} from {table} where {column} is not null")
        ).all():
            new = canonical_unit(old)
            if new != old:  # a blank string becomes NULL, like the domain now stores it
                conn.execute(
                    text(f"update {table} set {column}=:new where {column}=:old"),
                    {"new": new, "old": old},
                )
    rows = conn.execute(
        text("select id, readout_templates, condition_templates from protocol_forms")
    ).all()
    for form_id, readouts, conditions in rows:
        new_r, changed_r = _template_units(readouts)
        new_c, changed_c = _template_units(conditions)
        if changed_r or changed_c:
            conn.execute(
                text(
                    "update protocol_forms set readout_templates=cast(:r as jsonb), "
                    "condition_templates=cast(:c as jsonb) where id=:id"
                ),
                {
                    "r": json.dumps(new_r, ensure_ascii=False),
                    "c": json.dumps(new_c, ensure_ascii=False) if new_c is not None else None,
                    "id": form_id,
                },
            )


def _criterion_units(query: dict) -> bool:
    """Canonicalize the unit of every activity where-condition in place; True when one changed.
    Only any-protocol readout conditions carry a unit; the search page derives the reopened
    option (``any:rd:<name>|<unit>``) from it, so nothing else stores one."""
    changed = False

    def visit(criterion: dict) -> None:
        nonlocal changed
        where = criterion.get("where") if criterion.get("type") == "activity" else None
        for cond in where if isinstance(where, list) else ():
            if isinstance(cond, dict) and isinstance(cond.get("unit"), str):
                new = canonical_unit(cond["unit"])
                if new != cond["unit"]:
                    cond["unit"], changed = new, True

    walk_criteria(query.get("criteria"), visit)
    return changed


def rewrite_saved_search_units(conn: Connection) -> None:
    """Saved searches are live queries (not frozen records): their units follow the readouts'."""
    for search_id, query in conn.execute(text("select id, query from saved_searches")).all():
        if isinstance(query, dict) and _criterion_units(query):
            conn.execute(
                text("update saved_searches set query=cast(:q as jsonb) where id=:id"),
                {"q": json.dumps(query, ensure_ascii=False), "id": search_id},
            )
