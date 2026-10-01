# backend/src/cellar/application/export/row_streams/base.py
from __future__ import annotations

from collections.abc import AsyncIterator
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

    @property
    def display_header(self) -> str:
        """Header with its unit — "IC50 (uM)". A bare "IC50" in a CSV handed
        to another tool loses the scale of every value under it."""
        return f"{self.header} ({self.unit})" if self.unit else self.header


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
