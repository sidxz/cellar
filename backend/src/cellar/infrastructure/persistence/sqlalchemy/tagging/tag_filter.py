"""Shared tag-filter subquery builder, reused by the search composer and the
per-entity list repositories. Returns a Select of entity ids that carry the
given tags (``match_all=False`` = any of them; ``match_all=True`` = all of them).
"""

from __future__ import annotations

import uuid

from sqlalchemy import distinct, func, select
from sqlalchemy.sql import Select


def tag_filter_subquery(
    link_model: type,
    entity_id_attr: str,
    tag_ids: list[uuid.UUID],
    *,
    match_all: bool,
) -> Select:
    col = getattr(link_model, entity_id_attr)
    unique_ids = list(dict.fromkeys(tag_ids))  # dedup, preserve order
    stmt = select(col).where(link_model.tag_id.in_(unique_ids))
    if match_all:
        stmt = stmt.group_by(col).having(
            func.count(distinct(link_model.tag_id)) == len(unique_ids)
        )
    else:
        stmt = stmt.distinct()
    return stmt
