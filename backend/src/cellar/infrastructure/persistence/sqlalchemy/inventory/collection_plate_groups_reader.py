"""SQLAlchemy implementation of CollectionPlateGroupsReader (S16 §5).

Two recursive CTEs per call: ``up`` builds each linked group's ancestor path,
``down`` collects each linked group's subtree for the plate/loan counts.
"""

from __future__ import annotations

import uuid

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.application.inventory.collection_plate_groups import CollectionPlateGroupRow
from cellar.domain.inventory.enums import ACTIVE_LOAN_ITEM_STATUSES, LoanStatus

# Column order == CollectionPlateGroupRow field order (rows are splatted below).
_SQL = text(
    """
    WITH RECURSIVE linked AS (
        SELECT id FROM plate_groups
         WHERE workspace_id = :ws AND collection_id = :cid
    ), up AS (
        SELECT g.id AS root, g.parent_group_id, g.name, 0 AS depth
          FROM plate_groups g JOIN linked ON linked.id = g.id
        UNION ALL
        SELECT up.root, p.parent_group_id, p.name, up.depth + 1
          FROM plate_groups p JOIN up ON p.id = up.parent_group_id
         WHERE up.depth < 64
    ), down AS (
        SELECT id AS root, id FROM linked
        UNION ALL
        SELECT down.root, c.id
          FROM plate_groups c JOIN down ON c.parent_group_id = down.id
    ), paths AS (
        SELECT root, string_agg(name, ' › ' ORDER BY depth DESC) AS path
          FROM up GROUP BY root
    ), counts AS (
        SELECT down.root,
               count(DISTINCT rp.id) FILTER (WHERE rp.group_id = down.root) AS plate_count,
               count(DISTINCT rp.id) AS subtree_plate_count,
               count(DISTINCT rp.id) FILTER (WHERE l.id IS NOT NULL) AS on_loan_count,
               count(DISTINCT rp.id)
                   FILTER (WHERE l.id IS NOT NULL AND l.due_date < current_date) AS overdue_count
          FROM down
          LEFT JOIN registered_plates rp ON rp.group_id = down.id
          LEFT JOIN plate_loan_items li
                 ON li.plate_id = rp.id AND li.status IN :active_item_statuses
          LEFT JOIN plate_loans l ON l.id = li.loan_id AND l.status = :open_status
         GROUP BY down.root
    )
    SELECT g.id, g.name, g.group_type, g.owner_org_id, p.path,
           c.plate_count, c.subtree_plate_count, c.on_loan_count, c.overdue_count
      FROM plate_groups g
      JOIN paths p ON p.root = g.id
      JOIN counts c ON c.root = g.id
     ORDER BY p.path
    """  # noqa: RUF001 -- the spec-mandated path separator glyph (U+203A)
).bindparams(bindparam("active_item_statuses", expanding=True))


class SQLAlchemyCollectionPlateGroupsReader:
    """Opens a fresh session per call — safe to register as a singleton."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def groups_for_collection(
        self, workspace_id: uuid.UUID, collection_id: uuid.UUID
    ) -> list[CollectionPlateGroupRow]:
        params = {
            "ws": workspace_id,
            "cid": collection_id,
            "active_item_statuses": [s.value for s in ACTIVE_LOAN_ITEM_STATUSES],
            "open_status": LoanStatus.OPEN.value,
        }
        async with self._session_factory() as session:
            rows = (await session.execute(_SQL, params)).all()
        return [CollectionPlateGroupRow(*row) for row in rows]
