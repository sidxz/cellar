from __future__ import annotations
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import AsyncIterator

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.sparkline import render_sparkline_png
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow

SPARKLINE_ROW_CAP = 5000


class ExcelRenderer:
    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None:
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Data")
        headers = [c.header for c in columns]
        ws.append(headers)

        embed_sparklines = (
            options.include_sparklines
            and row_count_hint <= SPARKLINE_ROW_CAP
        )
        sparkline_col_indices = [
            i for i, c in enumerate(columns) if c.kind == "image_curve"
        ]

        tempfiles: list = []  # keep open until write
        rows_written = 0
        try:
            async for batch in batches:
                for row in batch:
                    out_row = []
                    for c in columns:
                        v = row.cells.get(c.key)
                        if c.kind == "number" and v is not None:
                            try:
                                v = float(v)
                            except (TypeError, ValueError):
                                pass
                        out_row.append(v if c.kind != "image_curve" else "")
                    ws.append(out_row)
                    rows_written += 1
                    if embed_sparklines and sparkline_col_indices:
                        snapshot = ((row.raw.get("activity") or {})
                                    .get("curve_snapshot") if row.raw else None)
                        png = render_sparkline_png(snapshot) if snapshot else None
                        if png:
                            tf = NamedTemporaryFile(suffix=".png", delete=False)
                            tf.write(png); tf.close()
                            tempfiles.append(tf.name)
                            for ci in sparkline_col_indices:
                                img = XLImage(tf.name)
                                cell_ref = f"{get_column_letter(ci+1)}{rows_written+1}"
                                ws.add_image(img, cell_ref)

            notes = wb.create_sheet("Notes")
            notes.append([options.title])
            notes.append([f"Rows: {rows_written}"])
            if not embed_sparklines and row_count_hint > SPARKLINE_ROW_CAP:
                notes.append([f"Sparklines omitted: row count {row_count_hint} exceeds {SPARKLINE_ROW_CAP} cap."])

            wb.save(out_path)
        finally:
            import os
            for p in tempfiles:
                try:
                    os.unlink(p)
                except OSError:
                    pass
