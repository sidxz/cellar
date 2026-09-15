"""CascadeRunner: Tier-2 preview and execute engine.

``plan`` walks every rule from the root over every matched row, not just the
preview's samples. It returns what the delete would do: rows to delete,
pointers to clear, and the block and warn rules that match. ``preview`` pairs
a sampled display tree with that plan. ``execute`` refuses when the plan has
blockers; otherwise it snapshots and applies the plan. Both go through
``plan``, so a preview can't pass a delete that execute refuses.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, Row, Table, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.application.admin.cascade_service import (
    CascadeBlockedError,
    CascadePreviewResult,
    InboundReference,
)
from cellar.domain.audit_compliance.enums import AuditAction
from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.shared.cascade.actions import CascadeAction
from cellar.domain.shared.cascade.nodes import CascadeNode
from cellar.infrastructure.cascade.label_fields import label_for_table
from cellar.infrastructure.cascade.registry import get_rules_for_parent
from cellar.infrastructure.cascade.rules import CascadeRule, any_id
from cellar.infrastructure.persistence.sqlalchemy.base import Base

__all__ = ["CascadeBlockedError", "CascadePlan", "CascadeRunner"]

SAMPLE_LIMIT = 5
_REPORTED = (CascadeAction.BLOCK, CascadeAction.WARN)


@dataclass
class CascadePlan:
    """What deleting one root row would do. Built by ``CascadeRunner.plan``."""

    # (table, ids), shallow-first. Deletes apply in reverse, so children go first.
    deletes: list[tuple[str, list[uuid.UUID]]] = field(default_factory=list)
    # Rows of id-less join tables, removed by predicate before anything else.
    link_deletes: list[tuple[str, ColumnElement[bool]]] = field(default_factory=list)
    # (table, column, [(row id, the id the column held)])
    nulls: list[tuple[str, str, list[tuple[uuid.UUID, uuid.UUID]]]] = field(default_factory=list)
    blockers: list[InboundReference] = field(default_factory=list)
    warnings: list[InboundReference] = field(default_factory=list)


@dataclass
class _Matches:
    """Distinct rows one block or warn rule matched, across the whole walk."""

    rule: CascadeRule
    ids: set[uuid.UUID] = field(default_factory=set)
    samples: list[dict] = field(default_factory=list)

    def reference(self) -> InboundReference:
        entity_type, _ = label_for_table(self.rule.child_table)
        return InboundReference(
            table=self.rule.child_table,
            fk_column=self.rule.fk_column or ", ".join(self.rule.covers),
            entity_type=entity_type,
            count=len(self.ids),
            samples=self.samples,
            truncated=len(self.ids) > len(self.samples),
            display_label=self.rule.display_label or None,
        )


def _scoped(
    table: Table, where: ColumnElement[bool], workspace_id: uuid.UUID
) -> ColumnElement[bool]:
    if "workspace_id" in table.c:
        return where & (table.c["workspace_id"] == workspace_id)
    return where


def _label(row: Row, label_column: str | None) -> str | None:
    value = getattr(row, label_column) if label_column else None
    return None if value is None else str(value)


class CascadeRunner:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    async def preview(
        self, *, parent_table: str, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> CascadePreviewResult:
        """The sampled tree of what goes, plus every blocker and warning from ``plan``."""
        root = await self._build_node_for_root(parent_table, parent_id, workspace_id)
        plan = await self.plan(
            parent_table=parent_table, parent_id=parent_id, workspace_id=workspace_id
        )
        return CascadePreviewResult(root=root, blockers=plan.blockers, warnings=plan.warnings)

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
            if rule.action in _REPORTED:
                continue  # reported exhaustively by plan(), not per sampled branch
            child_table = Base.metadata.tables[rule.child_table]
            where = _scoped(child_table, rule.where(child_table, [parent_id]), workspace_id)
            count = await self._count(child_table, where)
            if count == 0:
                continue
            samples = await self._fetch_samples(child_table, where, rule.label_field)
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
                # Each sampled child row becomes a recursion seed (display only).
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

    async def _count(self, table: Table, where: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(table).where(where)
        return int((await self._session.execute(stmt)).scalar_one())

    async def _fetch_samples(
        self, table: Table, where: ColumnElement[bool], label_column: str | None
    ) -> list[dict]:
        # Association tables may have no id column: count only.
        if "id" not in table.c:
            return []
        label = label_column if label_column and label_column in table.c else None
        cols = [table.c["id"], table.c[label]] if label else [table.c["id"]]
        rows = (await self._session.execute(select(*cols).where(where).limit(SAMPLE_LIMIT))).all()
        return [{"id": str(row.id), "label": _label(row, label)} for row in rows]

    async def _fetch_label(
        self, table: Table, id_: uuid.UUID, workspace_id: uuid.UUID
    ) -> str | None:
        _et, label_col = label_for_table(table.name)
        if not label_col or label_col not in table.c:
            return None
        stmt = select(table.c[label_col]).where(_scoped(table, table.c.id == id_, workspace_id))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    async def plan(
        self, *, parent_table: str, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> CascadePlan:
        """Walk every rule over every matched row; change nothing."""
        plan = CascadePlan()
        matches: dict[CascadeRule, _Matches] = {}
        walked: dict[str, set[uuid.UUID]] = {parent_table: {parent_id}}
        await self._walk(parent_table, [parent_id], workspace_id, plan, matches, walked)

        deleted = {(parent_table, parent_id)} | {
            (table, row_id) for table, ids in plan.deletes for row_id in ids
        }
        plan.nulls = [
            (table, column, kept)
            for table, column, rows in plan.nulls
            if (kept := [(row_id, old) for row_id, old in rows if (table, row_id) not in deleted])
        ]
        for found in matches.values():
            target = plan.blockers if found.rule.action == CascadeAction.BLOCK else plan.warnings
            target.append(found.reference())
        return plan

    async def _walk(
        self,
        table: str,
        parent_ids: list[uuid.UUID],
        workspace_id: uuid.UUID,
        plan: CascadePlan,
        matches: dict[CascadeRule, _Matches],
        walked: dict[str, set[uuid.UUID]],
    ) -> None:
        for rule in get_rules_for_parent(table):
            child = Base.metadata.tables[rule.child_table]
            where = _scoped(child, rule.where(child, parent_ids), workspace_id)

            if rule.action in _REPORTED:
                await self._match(rule, child, where, matches)
                continue

            if "id" not in child.c:
                # Join rows carry no business data; they go by predicate, unaudited.
                if rule.action == CascadeAction.CASCADE:
                    plan.link_deletes.append((rule.child_table, where))
                continue

            if rule.action == CascadeAction.SET_NULL:
                assert rule.fk_column is not None  # CascadeRule guarantees it
                column = child.c[rule.fk_column]
                rows = (await self._session.execute(select(child.c.id, column).where(where))).all()
                if rows:
                    plan.nulls.append(
                        (rule.child_table, rule.fk_column, [(r[0], r[1]) for r in rows])
                    )
                continue

            ids = [
                r[0] for r in (await self._session.execute(select(child.c.id).where(where))).all()
            ]
            if not ids:
                continue
            # A row reached twice (e.g. readout data under its definition and its
            # run) is listed twice: dropping the second copy would reorder deletes
            # and break FKs. Snapshots dedupe instead.
            plan.deletes.append((rule.child_table, ids))
            if rule.recurse_into_entity:
                seen = walked.setdefault(rule.child_table, set())
                fresh = [row_id for row_id in ids if row_id not in seen]
                seen.update(fresh)
                if fresh:
                    await self._walk(rule.child_table, fresh, workspace_id, plan, matches, walked)

    async def _match(
        self,
        rule: CascadeRule,
        child: Table,
        where: ColumnElement[bool],
        matches: dict[CascadeRule, _Matches],
    ) -> None:
        label = rule.label_field if rule.label_field and rule.label_field in child.c else None
        cols = [child.c.id, child.c[label]] if label else [child.c.id]
        rows = (await self._session.execute(select(*cols).where(where))).all()
        if not rows:
            return
        found = matches.setdefault(rule, _Matches(rule))
        for row in rows:
            if row.id in found.ids:
                continue
            found.ids.add(row.id)
            if len(found.samples) < SAMPLE_LIMIT:
                found.samples.append({"id": str(row.id), "label": _label(row, label)})

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(
        self, *, parent_table: str, parent_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[AuditEntry]:
        """Apply the plan, or raise ``CascadeBlockedError`` when any block rule matches.

        Returns the entries for the caller's AuditOperation: a DELETE with a full
        snapshot for every removed row, and an UPDATE for every cleared pointer.
        """
        plan = await self.plan(
            parent_table=parent_table, parent_id=parent_id, workspace_id=workspace_id
        )
        if plan.blockers:
            raise CascadeBlockedError(plan.blockers)

        now = datetime.now(UTC)
        entries = await self._snapshot_deletes(
            [(parent_table, [parent_id]), *plan.deletes], workspace_id, now
        )
        for table, column, rows in plan.nulls:
            entity_type, _ = label_for_table(table)
            entries.extend(
                AuditEntry(
                    entity_type=entity_type,
                    entity_id=row_id,
                    field_name=column,
                    action=AuditAction.UPDATE,
                    old_value=str(old),
                    new_value=None,
                    timestamp=now,
                )
                for row_id, old in rows
            )

        for table, where in plan.link_deletes:
            await self._session.execute(delete(Base.metadata.tables[table]).where(where))
        for table, column, rows in plan.nulls:
            sa_table = Base.metadata.tables[table]
            await self._session.execute(
                update(sa_table)
                .where(any_id(sa_table.c.id, [row_id for row_id, _ in rows]))
                .values({column: None})
            )
        for table, ids in reversed(plan.deletes):
            sa_table = Base.metadata.tables[table]
            await self._session.execute(delete(sa_table).where(any_id(sa_table.c.id, ids)))

        root = Base.metadata.tables[parent_table]
        await self._session.execute(
            delete(root).where(_scoped(root, root.c.id == parent_id, workspace_id))
        )
        return entries

    async def _snapshot_deletes(
        self,
        deletes: list[tuple[str, list[uuid.UUID]]],
        workspace_id: uuid.UUID,
        now: datetime,
    ) -> list[AuditEntry]:
        entries: list[AuditEntry] = []
        done: set[tuple[str, uuid.UUID]] = set()
        for table_name, ids in deletes:
            fresh = [row_id for row_id in ids if (table_name, row_id) not in done]
            if not fresh:
                continue
            done.update((table_name, row_id) for row_id in fresh)
            sa_table = Base.metadata.tables[table_name]
            where = _scoped(sa_table, any_id(sa_table.c.id, fresh), workspace_id)
            rows = (await self._session.execute(sa_table.select().where(where))).mappings().all()
            entity_type, _ = label_for_table(table_name)
            entries.extend(
                AuditEntry(
                    entity_type=entity_type,
                    entity_id=row["id"],
                    field_name="*",
                    action=AuditAction.DELETE,
                    old_value=json.dumps(dict(row), default=str, sort_keys=True),
                    new_value=None,
                    timestamp=now,
                )
                for row in rows
            )
        return entries
