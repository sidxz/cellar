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
from datetime import date


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
