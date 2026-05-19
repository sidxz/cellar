from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Protocol

from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


@dataclass(frozen=True)
class RenderOptions:
    include_sparklines: bool = True
    image_size: str = "small"   # "small" | "medium" | "large"
    page_size: str = "A4"
    page_orientation: str = "landscape"
    title: str = "Cellar Export"
    extras: dict = field(default_factory=dict)  # source-specific (e.g. query summary string)


class ExportRenderer(Protocol):
    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None: ...
