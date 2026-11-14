"""ColumnSplit — how a search splits one protocol's result columns into groups.

Optional and per protocol, set on the protocol's activity criterion:

- ``none``: today's columns — one value per readout, runs combined by the
  search's "Across runs" rule.
- ``run``: one column group per hand-picked run (the criterion's ``specific``
  run scope supplies the ids).
- ``condition``: one column group per value of a run condition (e.g. ATP
  concentration), the runs inside each group combined by the "Across runs" rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from cellar.domain.shared.errors import ValidationError

SplitBy = Literal["none", "run", "condition"]


@dataclass(frozen=True)
class ColumnSplit:
    by: SplitBy = "none"
    condition: str | None = None

    def is_split(self) -> bool:
        return self.by != "none"

    @classmethod
    def from_wire(cls, raw: Any) -> ColumnSplit:
        """The one parser for the criterion's ``split`` field. Absent means no split."""
        if raw is None or raw == {}:
            return cls()
        if not isinstance(raw, dict):
            raise ValidationError("split must be an object")
        by = raw.get("by", "none")
        condition = raw.get("condition")
        if by == "none":
            return cls()
        if by == "run":
            if condition is not None:
                raise ValidationError("split by run takes no condition")
            return cls(by="run")
        if by == "condition":
            name = condition.strip() if isinstance(condition, str) else ""
            if not name:
                raise ValidationError("split by condition needs a condition name")
            return cls(by="condition", condition=name)
        raise ValidationError(f"Unknown split: {by!r}")
