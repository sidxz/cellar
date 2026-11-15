# backend/src/cellar/application/export/row_streams/base.py
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ColumnKind = Literal[
    "text",
    "number",
    "smiles",
    "image_curve",
    "image_structure",
    "qualifier",
    "structure",
]


@dataclass(frozen=True)
class ColumnSpec:
    key: str  # stable identifier
    header: str  # human-readable
    kind: ColumnKind
    unit: str | None = None
    group: str | None = None  # logical column-group (e.g. protocol name)
    subgroup: str | None = None  # a split protocol's group under it ("10 µM")
    group_code: str | None = None  # protocol code of the group; flat formats append it
    digits: int | None = None  # fixed decimals, as the grid shows the property (MW 365.4)
    precision: int | None = None  # significant figures, as the grid shows a value (70.38)
    group_color: str | None = None  # a split group's curve colour when its plots overlay
    # An overlay plot: the activity keys of the split groups whose curves it draws, in order.
    overlay_of: tuple[str, ...] | None = None

    @property
    def display_header(self) -> str:
        """Header with its unit — "IC50 (uM)". A bare "IC50" in a CSV handed
        to another tool loses the scale of every value under it."""
        return f"{self.header} ({self.unit})" if self.unit else self.header

    @property
    def group_label(self) -> str | None:
        """Protocol and split group on one line, for a format with one group row."""
        return " · ".join(p for p in (self.group, self.subgroup) if p) or None

    @property
    def flat_header(self) -> str:
        """CSV and SDF have no group row: without the code, IC50 from two protocols
        collide, and without the split group, IC50 at 10 µM and at 1 mM."""
        tag = " · ".join(p for p in (self.group_code, self.subgroup) if p)
        return f"{self.display_header} [{tag}]" if tag else self.display_header


def group_spans(
    columns: list[ColumnSpec], key: Callable[[ColumnSpec], Any]
) -> list[tuple[int, int, ColumnSpec]]:
    """Runs of consecutive columns with the same ``key``: (start, end inclusive,
    the run's first column), one header cell each."""
    spans: list[tuple[int, int, ColumnSpec]] = []
    for i, c in enumerate(columns):
        if spans and key(spans[-1][2]) == key(c):
            spans[-1] = (spans[-1][0], i, spans[-1][2])
        else:
            spans.append((i, i, c))
    return spans


@dataclass
class ExportRow:
    cells: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)


class RowStream(Protocol):
    """Source of export rows + column metadata.

    Implementations must yield rows in deterministic order and expose a
    total_count that the workflow uses to compute progress.
    """

    columns: list[ColumnSpec]

    async def total_count(self) -> int: ...
    async def iter_batches(self, batch_size: int) -> AsyncIterator[list[ExportRow]]: ...
