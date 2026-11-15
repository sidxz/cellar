from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from cellar.application.export.renderers.base import BRAND, LOGO_PNG, RenderOptions
from cellar.application.export.renderers.sparkline import SIZE_PRESETS, column_plot
from cellar.application.export.renderers.structure import (
    STRUCTURE_SIZE_PRESETS,
    render_structure_pngs,
)
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow, group_spans

SPARKLINE_ROW_CAP = 5000


_GROUP_FILL = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
_GROUP_FONT = Font(bold=True, size=10, color="1E40AF")
_GROUP_ALIGN = Alignment(horizontal="center", vertical="center")
_GROUP_BORDER = Border(bottom=Side(style="medium", color="93C5FD"))


def _style_group_header(cell, color: str | None = None) -> None:
    """``color`` is an overlaid split group's curve colour: the header wears it,
    the key to the group's curve in the overlay plot."""
    argb = "FF" + color.lstrip("#").upper() if color else None  # opaque
    cell.font = Font(bold=True, size=10, color=argb) if argb else _GROUP_FONT
    cell.fill = _GROUP_FILL
    cell.alignment = _GROUP_ALIGN
    cell.border = Border(bottom=Side(style="thick", color=argb)) if argb else _GROUP_BORDER


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
        # NB: not using Workbook(write_only=True). Write-only sheets silently
        # ignore row_dimensions after `append` and don't reliably persist
        # column_dimensions when images are added — leaving structures + plots
        # squished into default-height rows. Memory budget at the 5K row cap
        # is comfortable (~150 MB peak) so the simplicity is worth it.
        wb = Workbook()
        ws = wb.active
        ws.title = "Data"

        # Two-row header when any column carries a group label. Protocol
        # group labels (merged across each protocol's columns) on row 1,
        # per-column labels on row 2. With image_curve cells stacked under
        # the group, this mirrors the FE search grid 1:1.
        has_groups = any(c.group_label for c in columns)
        if has_groups:
            ws.append([""] * len(columns))  # placeholder for group row
            spans = group_spans(columns, key=lambda c: (c.group_label, c.group_color))
            for start, end, first in spans:
                label, color = first.group_label, first.group_color
                if not label:
                    continue
                if end > start:
                    ws.merge_cells(
                        start_row=1,
                        start_column=start + 1,
                        end_row=1,
                        end_column=end + 1,
                    )
                cell = ws.cell(row=1, column=start + 1, value=label)
                _style_group_header(cell, color)
            _HEADER_ROWS = 2
        else:
            _HEADER_ROWS = 1

        header_row = [c.display_header for c in columns]
        ws.append(header_row)

        embed_images = options.include_sparklines and row_count_hint <= SPARKLINE_ROW_CAP
        sparkline_col_indices = [i for i, c in enumerate(columns) if c.kind == "image_curve"]
        structure_col_indices = [i for i, c in enumerate(columns) if c.kind == "image_structure"]
        size_preset = options.image_size if options.image_size in SIZE_PRESETS else "medium"
        sparkline_w, sparkline_h = SIZE_PRESETS[size_preset]
        struct_w, struct_h = STRUCTURE_SIZE_PRESETS.get(
            options.image_size, STRUCTURE_SIZE_PRESETS["medium"]
        )

        # Column widths: Excel uses character widths (~7 px each) plus a
        # ~5-px padding fudge. Empirically (width = px / 7 + 1) lands the
        # image inside the cell without horizontal clipping.
        if embed_images and sparkline_col_indices:
            for ci in sparkline_col_indices:
                ws.column_dimensions[get_column_letter(ci + 1)].width = sparkline_w / 7 + 1
        if embed_images and structure_col_indices:
            for ci in structure_col_indices:
                ws.column_dimensions[get_column_letter(ci + 1)].width = struct_w / 7 + 1

        # Per-row height in points (1 pt = 4/3 px). The tallest of the two
        # image kinds drives the row, plus a small margin so the image
        # doesn't kiss the gridline above.
        image_h_px = 0
        if embed_images and sparkline_col_indices:
            image_h_px = max(image_h_px, sparkline_h)
        if embed_images and structure_col_indices:
            image_h_px = max(image_h_px, struct_h)
        row_height_pt = (image_h_px * 0.75) + 6 if image_h_px else None

        tempfiles: list = []  # keep open until write
        rows_written = 0
        # Cache SMILES → tempfile path so repeated SMILES embed quickly.
        structure_cache: dict[str, str] = {}
        try:
            async for batch in batches:
                for row in batch:
                    out_row = []
                    for c in columns:
                        v = row.cells.get(c.key)
                        if c.kind == "number" and v is not None:
                            with contextlib.suppress(TypeError, ValueError):
                                v = float(v)
                        if c.kind in ("image_curve", "image_structure"):
                            out_row.append("")
                        else:
                            out_row.append(v)
                    ws.append(out_row)
                    rows_written += 1
                    excel_row = rows_written + _HEADER_ROWS  # +N for header rows
                    if row_height_pt is not None:
                        ws.row_dimensions[excel_row].height = row_height_pt

                    if embed_images and sparkline_col_indices:
                        # One curve per "drc:<rd_id>[@group]::plot" column, or
                        # every group's curve on an overlay column.
                        activity = (row.raw.get("activity") or {}) if row.raw else {}
                        for ci in sparkline_col_indices:
                            png = column_plot(columns[ci], activity, size=size_preset)
                            if not png:
                                continue
                            with NamedTemporaryFile(suffix=".png", delete=False) as tf:
                                tf.write(png)
                            tempfiles.append(tf.name)
                            img = XLImage(tf.name)
                            img.width = sparkline_w
                            img.height = sparkline_h
                            cell_ref = f"{get_column_letter(ci + 1)}{excel_row}"
                            ws.add_image(img, cell_ref)

                    if embed_images and structure_col_indices:
                        smiles = (row.raw or {}).get("smiles")
                        if not smiles:
                            continue
                        tf_path = structure_cache.get(smiles)
                        if tf_path is None:
                            pngs = render_structure_pngs([smiles], size=options.image_size)
                            png = pngs.get(smiles)
                            if not png:
                                continue
                            with NamedTemporaryFile(suffix=".png", delete=False) as tf:
                                tf.write(png)
                            tempfiles.append(tf.name)
                            tf_path = tf.name
                            structure_cache[smiles] = tf_path
                        for ci in structure_col_indices:
                            img = XLImage(tf_path)
                            img.width = struct_w
                            img.height = struct_h
                            cell_ref = f"{get_column_letter(ci + 1)}{excel_row}"
                            ws.add_image(img, cell_ref)

            # The Data sheet holds only the records; where they came from and
            # who took them sits apart, on Notes and in the file's properties.
            notes = wb.create_sheet("Notes")
            write_notes(notes, options, rows_written)
            if not embed_images and row_count_hint > SPARKLINE_ROW_CAP:
                notes.append(
                    [
                        "",
                        f"Images omitted: row count {row_count_hint} "
                        f"exceeds {SPARKLINE_ROW_CAP} cap.",
                    ]
                )
            wb.properties.title = f"{BRAND} · {options.title}"
            wb.properties.creator = options.extras.get("exported_by") or BRAND
            wb.properties.description = options.attribution

            wb.save(out_path)
        finally:
            import os

            for p in tempfiles:
                with contextlib.suppress(OSError):
                    os.unlink(p)


def write_notes(ws, options: RenderOptions, rows_written: int) -> None:
    """The ChemCellar mark, then what was exported, when and by whom."""
    ws.row_dimensions[1].height = 30
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 90
    logo = XLImage(str(LOGO_PNG))
    logo.width = logo.height = 32
    ws.add_image(logo, "A1")
    ws["B1"] = BRAND
    ws["B1"].font = Font(bold=True, size=16)
    ws["B1"].alignment = Alignment(vertical="center")
    extras = options.extras or {}
    lines = [
        options.title,
        extras.get("query_summary"),
        f"Rows: {rows_written}",
        extras.get("aggregation_label"),
        f"Exported {extras['exported_at']}" if extras.get("exported_at") else None,
        f"By {extras['exported_by']}" if extras.get("exported_by") else None,
    ]
    for line in lines:
        if line:
            ws.append(["", line])
