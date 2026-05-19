"""RunScope — narrow which runs of a protocol contribute to a cell.

A criterion-level filter the chemist sets on the search panel
("Last 3 runs", "Since Apr 2026", "Specific runs"). The aggregator
then operates only over the runs that match.

Implemented as a tagged-union dataclass with smart constructors. The
SQL adapter inspects which field is non-default and translates to the
right WHERE clause.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class RunScope:
    """Filter on which runs of a (protocol, compound) feed into the cell."""

    last_n_count: int | None = None
    since_date: date | None = None
    from_date: date | None = None
    to_date: date | None = None
    explicit_run_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)

    @classmethod
    def all(cls) -> RunScope:
        return cls()

    @classmethod
    def last_n(cls, n: int) -> RunScope:
        if n < 1:
            raise ValueError("last_n requires n >= 1")
        return cls(last_n_count=n)

    @classmethod
    def since(cls, when: date) -> RunScope:
        return cls(since_date=when)

    @classmethod
    def between(cls, from_: date, to: date) -> RunScope:
        if to < from_:
            raise ValueError("between requires to >= from")
        return cls(from_date=from_, to_date=to)

    @classmethod
    def run_ids(cls, ids: list[uuid.UUID]) -> RunScope:
        return cls(explicit_run_ids=tuple(ids))

    def is_all(self) -> bool:
        return (
            self.last_n_count is None
            and self.since_date is None
            and self.from_date is None
            and self.to_date is None
            and not self.explicit_run_ids
        )

    @classmethod
    def from_wire(cls, raw: Any) -> RunScope:
        """Single parser for the FE's mode-keyed wire shape.

        Both the application-layer enrichment service and the SQL composer
        consume the same chemist-facing ``run_scope`` dict; this is the
        ONE place that interprets it. Wire shape:

        - ``{"mode": "any" | "all"}`` → ``RunScope.all()``
        - ``{"mode": "latest"}`` → ``RunScope.last_n(1)``
        - ``{"mode": "past_n_days", "days": N}`` →
          ``RunScope.since(today - N days)``
        - ``{"mode": "specific", "run_ids": [...]}`` (or legacy
          ``"run_id"``) → ``RunScope.run_ids(...)``
        - ``{"mode": "date_range", "date_from": ISO, "date_to": ISO}``
          → ``RunScope.between(d_from, d_to)``; either bound alone
          degrades to ``RunScope.since(d_from)`` / leaves to_date null.

        Malformed input (unknown mode, non-numeric days, unparseable
        dates, non-UUID run_ids) falls back to ``RunScope.all()`` rather
        than raising — the SQL composer's stricter validation will
        surface a 422 if needed, and we don't want enrichment to blow up
        after rows have already loaded.
        """
        if not isinstance(raw, dict):
            return cls.all()
        mode = raw.get("mode")
        if mode in (None, "any", "all"):
            return cls.all()
        if mode == "latest":
            return cls.last_n(1)
        if mode == "past_n_days":
            try:
                days = int(raw.get("days", 30))
            except (TypeError, ValueError):
                return cls.all()
            return cls.since(date.today() - timedelta(days=max(days, 0)))
        if mode == "specific":
            raw_ids = raw.get("run_ids")
            if not raw_ids:
                single = raw.get("run_id")
                raw_ids = [single] if single else []
            try:
                ids = [uuid.UUID(str(x)) for x in raw_ids]
            except (TypeError, ValueError):
                return cls.all()
            return cls.run_ids(ids) if ids else cls.all()
        if mode == "date_range":
            df = raw.get("date_from")
            dt = raw.get("date_to")
            try:
                d_from = date.fromisoformat(df) if df else None
                d_to = date.fromisoformat(dt) if dt else None
            except (TypeError, ValueError):
                return cls.all()
            if d_from is not None and d_to is not None:
                return cls.between(d_from, d_to)
            if d_from is not None:
                return cls.since(d_from)
            return cls.all()
        return cls.all()
