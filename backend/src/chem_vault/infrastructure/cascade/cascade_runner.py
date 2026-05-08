"""CascadeRunner — Tier-2 preview + execute engine.

Walks the per-module cascade registry to build a CascadeNode tree.
Preview half only — execute engine lands in Task 13.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.shared.cascade import (
    CascadeAction,
    CascadeNode,
    get_rules_for_parent,
)
from chem_vault.infrastructure.cascade.label_fields import label_for_table
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base


SAMPLE_LIMIT = 5


class CascadeRunner:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def preview(
        self, *, parent_table: str, parent_id: uuid.UUID
    ) -> CascadeNode:
        """Build the full cascade tree rooted at (parent_table, parent_id)."""
        return await self._build_node_for_root(parent_table, parent_id)

    async def _build_node_for_root(self, table: str, id_: uuid.UUID) -> CascadeNode:
        entity_type, _label_col = label_for_table(table)
        sa_table = Base.metadata.tables[table]
        root_label = await self._fetch_label(sa_table, id_)
        root = CascadeNode(
            entity_type=entity_type,
            table=table,
            display_label=entity_type,
            count=1,
            samples=[{"id": str(id_), "label": root_label}],
            truncated=False,
            action=CascadeAction.CASCADE,
            children=[],
        )
        await self._populate_children(root, parent_id=id_)
        return root

    async def _populate_children(
        self, node: CascadeNode, *, parent_id: uuid.UUID
    ) -> None:
        for rule in get_rules_for_parent(node.table):
            child_table = Base.metadata.tables[rule.child_table]
            count = await self._count(child_table, rule.fk_column, parent_id)
            if count == 0 and rule.action != CascadeAction.WARN:
                continue
            samples = await self._fetch_samples(
                child_table,
                rule.fk_column,
                parent_id,
                rule.label_field,
                SAMPLE_LIMIT,
            )
            child_node = CascadeNode(
                entity_type=label_for_table(rule.child_table)[0],
                table=rule.child_table,
                display_label=rule.display_label or rule.child_table,
                count=count,
                samples=samples,
                truncated=count > len(samples),
                action=rule.action,
                children=[],
            )
            node.children.append(child_node)

            if rule.action == CascadeAction.CASCADE and rule.recurse_into_entity:
                # Recurse: each matched child row becomes a recursion seed.
                for s in samples:
                    sub = CascadeNode(
                        entity_type=child_node.entity_type,
                        table=rule.child_table,
                        display_label=s.get("label") or child_node.entity_type,
                        count=1,
                        samples=[s],
                        truncated=False,
                        action=CascadeAction.CASCADE,
                        children=[],
                    )
                    await self._populate_children(sub, parent_id=uuid.UUID(s["id"]))
                    child_node.children.append(sub)

    # --- helpers ---

    async def _count(
        self, table: Table, fk_column: str, parent_id: uuid.UUID
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(table)
            .where(table.c[fk_column] == parent_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def _fetch_samples(
        self,
        table: Table,
        fk_column: str,
        parent_id: uuid.UUID,
        label_column: str | None,
        limit: int,
    ) -> list[dict]:
        # Association tables may have no id column — return count-only.
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
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "id": str(row.id),
                "label": getattr(row, label_column, None) if has_label else None,
            }
            for row in rows
        ]

    async def _fetch_label(self, table: Table, id_: uuid.UUID) -> str | None:
        _et, label_col = label_for_table(table.name)
        if not label_col or label_col not in table.c:
            return None
        stmt = select(table.c[label_col]).where(table.c.id == id_)
        return (await self._session.execute(stmt)).scalar_one_or_none()
