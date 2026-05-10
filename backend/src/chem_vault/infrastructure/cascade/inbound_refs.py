"""Inbound FK introspection — Tier-1 RESTRICT helper.

For a given (table, primary_key_value), enumerate every row in OTHER
tables that has a FK pointing at it. Used to compute the blocker
payload for the admin RESTRICT delete path.

Association/join tables that have no ``id`` column are count-only
(label will be None even if TABLE_LABELS maps them to a label column).
"""
from __future__ import annotations

import uuid

from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.application.admin.cascade_service import InboundReference
from chem_vault.infrastructure.cascade.label_fields import label_for_table
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base

__all__ = ["InboundReference", "find_inbound_references"]


async def find_inbound_references(
    session: AsyncSession,
    *,
    parent_table: str,
    parent_id: uuid.UUID,
    workspace_id: uuid.UUID,
    sample_limit: int = 5,
) -> list[InboundReference]:
    """Return all rows referencing (parent_table, parent_id) via FK.

    Walks ``Base.metadata`` at call-time — no registry, no per-entity
    boilerplate required.  Only tables that have at least one matching
    row are included in the result.

    ``workspace_id`` is ANDed into every query on child tables that carry
    a ``workspace_id`` column, so that an admin in workspace A cannot see
    references that originate in workspace B.
    """
    references: list[InboundReference] = []

    for table in Base.metadata.tables.values():
        if table.name == parent_table:
            continue
        for fk in _foreign_keys_pointing_to(table, parent_table):
            count = await _count_rows(
                session, table, fk.parent.name, parent_id, workspace_id
            )
            if count == 0:
                continue
            samples = await _fetch_samples(
                session, table, fk.parent.name, parent_id, workspace_id, sample_limit
            )
            entity_type, _label_col = label_for_table(table.name)
            references.append(
                InboundReference(
                    table=table.name,
                    fk_column=fk.parent.name,
                    entity_type=entity_type,
                    count=count,
                    samples=samples,
                    truncated=count > len(samples),
                )
            )

    return references


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _foreign_keys_pointing_to(table: Table, parent_table: str):
    """Yield ForeignKey objects on ``table`` that point at ``<parent_table>.id``."""
    for col in table.columns:
        for fk in col.foreign_keys:
            # fk.target_fullname e.g. "protocols.id"
            target_table, _, target_col = fk.target_fullname.partition(".")
            if target_table == parent_table and target_col == "id":
                yield fk


async def _count_rows(
    session: AsyncSession,
    table: Table,
    fk_column: str,
    parent_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> int:
    stmt = (
        select(func.count())
        .select_from(table)
        .where(table.c[fk_column] == parent_id)
    )
    if "workspace_id" in table.c:
        stmt = stmt.where(table.c["workspace_id"] == workspace_id)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _fetch_samples(
    session: AsyncSession,
    table: Table,
    fk_column: str,
    parent_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit: int,
) -> list[dict]:
    """Fetch up to ``limit`` rows and render label using TABLE_LABELS.

    Falls back to count-only (label=None) when the table has no ``id``
    column (association tables) or no label column is defined.
    """
    _entity_type, label_column = label_for_table(table.name)

    # Association tables may have no ``id`` column — return count-only samples.
    if "id" not in table.c:
        return []

    cols = [table.c["id"]]
    has_label = label_column is not None and label_column in table.c
    if has_label:
        cols.append(table.c[label_column])

    stmt = (
        select(*cols)
        .where(table.c[fk_column] == parent_id)
        .limit(limit)
    )
    if "workspace_id" in table.c:
        stmt = stmt.where(table.c["workspace_id"] == workspace_id)
    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "id": str(row.id),
            "label": getattr(row, label_column, None) if has_label else None,
        }
        for row in rows
    ]
