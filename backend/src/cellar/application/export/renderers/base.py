from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from cellar.application.export.row_streams.base import ColumnSpec, ExportRow

BRAND = "ChemCellar"
ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_SVG = ASSETS_DIR / "chemcellar-logo.svg"  # the PDF header's mark
LOGO_PNG = ASSETS_DIR / "chemcellar-logo.png"  # the same, rasterised for Excel's Notes sheet


@dataclass(frozen=True)
class RenderOptions:
    include_sparklines: bool = True
    image_size: str = "small"  # "small" | "medium" | "large"
    page_size: str = "A4"
    page_orientation: str = "landscape"
    title: str = "Cellar Export"
    # Source-specific: query_summary, aggregation_label, and who exported it
    # when (exported_at, exported_by) for the PDF and Excel's Notes sheet.
    extras: dict = field(default_factory=dict)

    @property
    def attribution(self) -> str:
        """Where a file came from and who took it, apart from its records (the PDF's
        footer, Excel's Notes sheet): "ChemCellar export · 2026-11-15 19:35 UTC · ada@lab.org"."""
        parts = [f"{BRAND} export", self.extras.get("exported_at"), self.extras.get("exported_by")]
        return " · ".join(p for p in parts if p)


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
