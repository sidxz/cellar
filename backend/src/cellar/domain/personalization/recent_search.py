"""RecentSearch — a search the user ran, kept so they can run it again."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cellar.domain.shared.errors import ValidationError

#: How many searches a user's history keeps; older ones drop off.
MAX_RECENT_SEARCHES = 20


def _canonical(value: Any, key: str | None = None) -> Any:
    if isinstance(value, list):
        items = [_canonical(item) for item in value]
        if key == "criteria":  # the same criteria in another order are the same search
            items.sort(key=lambda item: json.dumps(item, sort_keys=True, default=str))
        return items
    if isinstance(value, dict):
        return {k: _canonical(v, k) for k, v in value.items()}
    return value


def recent_search_key(query: dict[str, Any]) -> str:
    """One history entry per search, however its runs are summarised.

    The stored query carries the aggregation rule (latest run, mean, …), but
    that is how values are shown, not what is searched: running the same
    criteria under another rule moves the entry instead of adding one. Same
    equivalence as the frontend's ``searchQueryKey`` (criteria order, key
    order and a missing ``logic`` meaning "and" don't matter).
    """
    criteria = {k: v for k, v in query.items() if k != "aggregation"}
    criteria["logic"] = criteria.get("logic") or "and"
    canonical = json.dumps(
        _canonical(criteria), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class RecentSearch:
    """A search in the user's own history, with the table set-up it ran with.

    ``query`` and ``columns`` have the shape a saved search stores, so either
    reloads through the same path. Not an AggregateRoot: no domain events and
    no optimistic concurrency — it is the user's own history, where the latest
    run of a search simply wins (like ``UserPreferences``).
    """

    workspace_id: uuid.UUID
    user_id: uuid.UUID
    query: dict[str, Any]
    columns: dict[str, Any] | None
    result_count: int | None
    ran_at: datetime
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    @property
    def query_key(self) -> str:
        return recent_search_key(self.query)

    @classmethod
    def record(
        cls,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        query: dict[str, Any],
        columns: dict[str, Any] | None = None,
        result_count: int | None = None,
    ) -> RecentSearch:
        criteria = query.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ValidationError("A recent search needs at least one criterion")
        if result_count is not None and result_count < 0:
            raise ValidationError("A search cannot match a negative number of compounds")
        return cls(
            workspace_id=workspace_id,
            user_id=user_id,
            query=dict(query),
            columns=dict(columns) if columns else None,
            result_count=result_count,
            ran_at=datetime.now(UTC),
        )
