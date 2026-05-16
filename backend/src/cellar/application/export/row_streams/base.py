# backend/src/cellar/application/export/row_streams/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol


ColumnKind = Literal["text", "number", "smiles", "image_curve", "qualifier", "structure"]


@dataclass(frozen=True)
class ColumnSpec:
    key: str               # stable identifier
    header: str            # human-readable
    kind: ColumnKind
    unit: str | None = None
    group: str | None = None  # logical column-group (e.g. protocol name)


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
