from __future__ import annotations
import csv
from pathlib import Path
from typing import AsyncIterator

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


class CsvRenderer:
    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None:
        # Image columns (sparklines) aren't meaningful in CSV — drop them
        # before writing so chemists don't see an empty "Plot" column.
        out_cols = [c for c in columns if c.kind != "image_curve"]
        with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([c.header for c in out_cols])
            async for batch in batches:
                for row in batch:
                    writer.writerow([_serialize(row.cells.get(c.key)) for c in out_cols])


def _serialize(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # Preserve full precision but strip trailing zeros.
        s = f"{value!r}"
        return s
    return str(value)
