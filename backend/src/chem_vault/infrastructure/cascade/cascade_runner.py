"""CascadeRunner — Tier-2 preview + execute engine.

Walks the per-module cascade registry to build a CascadeNode tree.
Preview half: builds a CascadeNode tree for user confirmation.
Execute half: snapshots all rows, applies SET NULL + DELETEs, returns AuditEntries.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import Table, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.audit_compliance.enums import AuditAction
from chem_vault.domain.audit_compliance.models import AuditEntry
from chem_vault.domain.shared.cascade import (
    CascadeAction,
    CascadeNode,
    get_rules_for_parent,
)
from chem_vault.infrastructure.cascade.label_fields import label_for_table
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base


class CascadeExecutionError(Exception):
    """Raised when a BLOCK rule matched at execute time (race after preview)."""


SAMPLE_LIMIT = 5


class CascadeRunner:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def preview(
        self, *, parent_table: str, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> CascadeNode:
        """Build the full cascade tree rooted at (parent_table, parent_id).

        ``workspace_id`` scopes every child query so that only rows belonging
        to the caller's workspace are reflected in the tree.
        """
        return await self._build_node_for_root(parent_table, parent_id, workspace_id)

    async def _build_node_for_root(
        self, table: str, id_: uuid.UUID, workspace_id: uuid.UUID
    ) -> CascadeNode:
        entity_type, _label_col = label_for_table(table)
        sa_table = Base.metadata.tables[table]
        root_label = await self._fetch_label(sa_table, id_, workspace_id)
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
        await self._populate_children(root, parent_id=id_, workspace_id=workspace_id)
        return root

    async def _populate_children(
        self, node: CascadeNode, *, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        for rule in get_rules_for_parent(node.table):
            child_table = Base.metadata.tables[rule.child_table]
            count = await self._count(child_table, rule.fk_column, parent_id, workspace_id)
            if count == 0 and rule.action != CascadeAction.WARN:
                continue
            samples = await self._fetch_samples(
                child_table,
                rule.fk_column,
                parent_id,
                workspace_id,
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
                    await self._populate_children(
                        sub, parent_id=uuid.UUID(s["id"]), workspace_id=workspace_id
                    )
                    child_node.children.append(sub)

    # --- helpers ---

    async def _count(
        self,
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
        return int((await self._session.execute(stmt)).scalar_one())

    async def _fetch_samples(
        self,
        table: Table,
        fk_column: str,
        parent_id: uuid.UUID,
        workspace_id: uuid.UUID,
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
        if "workspace_id" in table.c:
            stmt = stmt.where(table.c["workspace_id"] == workspace_id)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "id": str(row.id),
                "label": getattr(row, label_column, None) if has_label else None,
            }
            for row in rows
        ]

    async def _fetch_label(
        self, table: Table, id_: uuid.UUID, workspace_id: uuid.UUID
    ) -> str | None:
        _et, label_col = label_for_table(table.name)
        if not label_col or label_col not in table.c:
            return None
        stmt = select(table.c[label_col]).where(table.c.id == id_)
        if "workspace_id" in table.c:
            stmt = stmt.where(table.c["workspace_id"] == workspace_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Execute engine
    # ------------------------------------------------------------------

    async def execute(
        self,
        *,
        parent_table: str,
        parent_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> list[AuditEntry]:
        """Execute the cascade. Returns audit entries to attach to the
        AuditOperation by the caller. Raises CascadeExecutionError if a BLOCK
        rule matches at execute time (rare race).

        ``workspace_id`` is threaded through every query so that only rows
        belonging to the caller's workspace are touched.

        Strategy:
          1. Topologically collect all rows that will be deleted, in
             dependency order (deepest descendants first).
          2. Snapshot each into an AuditEntry.
          3. Apply: SET NULL for set_null rules, DELETE for cascade rules.
          4. Finally DELETE the root row (also workspace-scoped).
        """
        entries: list[AuditEntry] = []
        null_ops: list[tuple[str, str, list[uuid.UUID]]] = []  # (table, fk_col, ids)
        delete_ops: list[tuple[str, list[uuid.UUID]]] = []     # (table, ids)

        await self._collect(
            parent_table, [parent_id], workspace_id,
            entries=entries, null_ops=null_ops, delete_ops=delete_ops,
        )

        # Apply set-null first (so downstream cascades see NULLs already), then deletes.
        for table_name, fk_col, ids in null_ops:
            sa_table = Base.metadata.tables[table_name]
            await self._session.execute(
                update(sa_table).where(sa_table.c.id.in_(ids)).values(**{fk_col: None})
            )

        # Delete in reverse topological order: collected list has deepest last.
        for table_name, ids in reversed(delete_ops):
            sa_table = Base.metadata.tables[table_name]
            await self._session.execute(
                delete(sa_table).where(sa_table.c.id.in_(ids))
            )

        # Delete the root row last — also workspace-scoped for safety.
        root_table = Base.metadata.tables[parent_table]
        root_where = root_table.c.id == parent_id
        if "workspace_id" in root_table.c:
            root_where = root_where & (root_table.c["workspace_id"] == workspace_id)
        await self._session.execute(
            delete(root_table).where(root_where)
        )
        return entries

    async def _collect(
        self,
        table: str,
        parent_ids: list[uuid.UUID],
        workspace_id: uuid.UUID,
        *,
        entries: list[AuditEntry],
        null_ops: list[tuple[str, str, list[uuid.UUID]]],
        delete_ops: list[tuple[str, list[uuid.UUID]]],
    ) -> None:
        """Walk the cascade graph from a set of parent rows, gather plans.

        ``workspace_id`` is used to scope queries on tables that carry that
        column, preventing cross-workspace data leakage or deletion.
        """
        sa_table = Base.metadata.tables[table]
        # Snapshot the parents themselves (already workspace-isolated via FK chain
        # from the root, but apply filter defensively if column exists).
        snap_where = sa_table.c.id.in_(parent_ids)
        if "workspace_id" in sa_table.c:
            snap_where = snap_where & (sa_table.c["workspace_id"] == workspace_id)
        rows = (
            await self._session.execute(
                sa_table.select().where(snap_where)
            )
        ).mappings().all()
        et, _ = label_for_table(table)
        now = datetime.now(UTC)
        for row in rows:
            entries.append(
                AuditEntry(
                    entity_type=et,
                    entity_id=row["id"],
                    field_name="*",
                    action=AuditAction.DELETE,
                    old_value=json.dumps(dict(row), default=str, sort_keys=True),
                    new_value=None,
                    timestamp=now,
                )
            )
        # Now walk children
        for rule in get_rules_for_parent(table):
            child_sa = Base.metadata.tables[rule.child_table]
            child_fk_where = child_sa.c[rule.fk_column].in_(parent_ids)
            if "workspace_id" in child_sa.c:
                child_fk_where = child_fk_where & (
                    child_sa.c["workspace_id"] == workspace_id
                )
            if rule.action == CascadeAction.BLOCK:
                count = (
                    await self._session.execute(
                        select(func.count()).select_from(child_sa).where(child_fk_where)
                    )
                ).scalar_one()
                if count > 0:
                    raise CascadeExecutionError(
                        f"Blocking rule fired: {rule.child_table}.{rule.fk_column}"
                    )
                continue
            if rule.action == CascadeAction.WARN:
                continue
            # Association/join tables may have no id column — handle separately.
            if "id" not in child_sa.c:
                if rule.action == CascadeAction.CASCADE:
                    # DELETE directly by FK; no snapshot (join rows carry no
                    # business data worth auditing individually).
                    await self._session.execute(
                        delete(child_sa).where(child_fk_where)
                    )
                # SET_NULL on a no-id table is structurally unusual but guard anyway.
                continue

            # Find child IDs (workspace-scoped)
            child_ids = [
                row.id
                for row in (
                    await self._session.execute(
                        select(child_sa.c.id).where(child_fk_where)
                    )
                ).all()
            ]
            if not child_ids:
                continue
            if rule.action == CascadeAction.SET_NULL:
                null_ops.append((rule.child_table, rule.fk_column, child_ids))
                continue
            # CASCADE — recurse if rule says so, otherwise just snapshot+delete
            if rule.recurse_into_entity:
                await self._collect(
                    rule.child_table, child_ids, workspace_id,
                    entries=entries, null_ops=null_ops, delete_ops=delete_ops,
                )
            else:
                # Snapshot leaf rows
                leaf_rows = (
                    await self._session.execute(
                        child_sa.select().where(child_sa.c.id.in_(child_ids))
                    )
                ).mappings().all()
                child_et, _ = label_for_table(rule.child_table)
                now2 = datetime.now(UTC)
                for row in leaf_rows:
                    entries.append(
                        AuditEntry(
                            entity_type=child_et,
                            entity_id=row["id"],
                            field_name="*",
                            action=AuditAction.DELETE,
                            old_value=json.dumps(dict(row), default=str, sort_keys=True),
                            new_value=None,
                            timestamp=now2,
                        )
                    )
            delete_ops.append((rule.child_table, child_ids))
