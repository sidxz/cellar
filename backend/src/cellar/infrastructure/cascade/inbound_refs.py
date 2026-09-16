"""Tier-1 RESTRICT blockers: every row still referencing (table, id).

Two sources, both workspace-scoped:
- every SQLAlchemy ForeignKey pointing at ``<parent_table>.id``;
- every cascade rule registered for the parent whose reference isn't one of
  those FKs (id-only columns, JSON, polymorphic links), whatever its action,
  because a Tier-1 delete removes nothing but the row itself.

Association/join tables that have no ``id`` column are count-only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.application.admin.cascade_service import InboundReference
from cellar.infrastructure.cascade.label_fields import label_for_table
from cellar.infrastructure.cascade.registry import get_rules_for_parent
from cellar.infrastructure.cascade.rules import CascadeRule
from cellar.infrastructure.persistence.sqlalchemy.base import Base

__all__ = ["InboundReference", "find_inbound_references"]


async def find_inbound_references(
    session: AsyncSession,
    *,
    parent_table: str,
    parent_id: uuid.UUID,
    workspace_id: uuid.UUID,
    sample_limit: int = 5,
) -> list[InboundReference]:
    """Return every group of rows referencing (parent_table, parent_id)."""
    references: list[InboundReference] = []

    for table in Base.metadata.tables.values():
        if table.name == parent_table:
            continue
        for fk in _foreign_keys_pointing_to(table, parent_table):
            column = fk.parent.name
            ref = await _reference(
                session,
                table,
                table.c[column] == parent_id,
                workspace_id,
                sample_limit,
                fk_column=column,
                label_column=label_for_table(table.name)[1],
            )
            if ref is not None:
                references.append(ref)

    for rule in get_rules_for_parent(parent_table):
        if _is_fk_to(rule, parent_table) and rule.child_table != parent_table:
            continue  # counted by the FK walk above, which skips self-references
        table = Base.metadata.tables[rule.child_table]
        ref = await _reference(
            session,
            table,
            rule.where(table, [parent_id]),
            workspace_id,
            sample_limit,
            fk_column=rule.fk_column or ", ".join(rule.covers),
            label_column=rule.label_field,
            display_label=rule.display_label or None,
        )
        if ref is not None:
            references.append(ref)

    return references


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _foreign_keys_pointing_to(table: Table, parent_table: str):
    """Yield ForeignKey objects on ``table`` that point at ``<parent_table>.id``."""
    for col in table.columns:
        for fk in col.foreign_keys:
            target_table, _, target_col = fk.target_fullname.partition(".")
            if target_table == parent_table and target_col == "id":
                yield fk


def _is_fk_to(rule: CascadeRule, parent_table: str) -> bool:
    if rule.fk_column is None:
        return False
    column = Base.metadata.tables[rule.child_table].c[rule.fk_column]
    return any(fk.target_fullname == f"{parent_table}.id" for fk in column.foreign_keys)


async def _reference(
    session: AsyncSession,
    table: Table,
    where: ColumnElement[bool],
    workspace_id: uuid.UUID,
    sample_limit: int,
    *,
    fk_column: str,
    label_column: str | None,
    display_label: str | None = None,
) -> InboundReference | None:
    if "workspace_id" in table.c:
        where = where & (table.c["workspace_id"] == workspace_id)
    count = int(
        (await session.execute(select(func.count()).select_from(table).where(where))).scalar_one()
    )
    if count == 0:
        return None

    samples: list[dict] = []
    if "id" in table.c:  # association tables are count-only
        label = label_column if label_column and label_column in table.c else None
        cols = [table.c["id"], table.c[label]] if label else [table.c["id"]]
        rows = (await session.execute(select(*cols).where(where).limit(sample_limit))).all()
        samples = [
            {
                "id": str(row[0]),
                "label": None if label is None or row[1] is None else str(row[1]),
            }
            for row in rows
        ]

    entity_type, _ = label_for_table(table.name)
    return InboundReference(
        table=table.name,
        fk_column=fk_column,
        entity_type=entity_type,
        count=count,
        samples=samples,
        truncated=count > len(samples),
        display_label=display_label,
    )
