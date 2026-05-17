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


def _av_to_sparkline_snapshot(av: dict) -> dict | None:
    """Build a sparkline-renderer-compatible snapshot dict from an ActivityValue asdict.

    ``ActivityValue`` (via ``dataclasses.asdict``) carries raw_data, curve_params,
    value (the fitted primary intercept), and curve_class via curve_params — but
    NOT a pre-built ``curve_snapshot`` dict.  The sparkline renderer expects:
      - ``data_points``: list of {dose, response} (renderer uses "dose"/"response"
        keys; ActivityValue raw_data uses "x"/"y" — we remap).
      - ``fit``: {bottom, top, ec50, hill_slope} — ec50 comes from the top-level
        ``value`` field (the fitted primary intercept); curve_params carries the
        rest.
      - ``curve_class``: str | None — from curve_params.

    Returns None when there is not enough shape information to render (e.g. a
    readout_data source, or a curve with missing fit params).
    """
    if not av:
        return None
    curve_params = av.get("curve_params") or {}
    top = curve_params.get("top")
    bottom = curve_params.get("bottom")
    hill_slope = curve_params.get("hill_slope")
    if top is None or bottom is None or hill_slope is None:
        return None  # no fit — not a DR ActivityValue with usable shape

    # Remap raw_data x/y → dose/response for the sparkline renderer.
    raw_data = av.get("raw_data") or []
    data_points = [
        {"dose": pt["x"], "response": pt["y"], **{k: v for k, v in pt.items() if k not in ("x", "y")}}
        for pt in raw_data
        if isinstance(pt, dict) and "x" in pt and "y" in pt
    ]

    ec50 = av.get("value")  # fitted primary intercept value IS the EC50/IC50
    fit: dict = {"bottom": bottom, "top": top, "hill_slope": hill_slope}
    if ec50 is not None:
        fit["ec50"] = ec50

    return {
        "data_points": data_points,
        "fit": fit,
        "curve_class": curve_params.get("curve_class"),
    }


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
                        # Each image_curve column is keyed by "drc:<rd_id>::plot".
                        # The parent activity token is "drc:<rd_id>" — one
                        # ActivityValue (serialised via dataclasses.asdict) per
                        # readout-def.  ActivityValue has no pre-built
                        # curve_snapshot field; we assemble a snapshot-compatible
                        # dict from the component fields that the sparkline
                        # renderer expects.
                        activity = (row.raw.get("activity") or {}) if row.raw else {}
                        for ci in sparkline_col_indices:
                            col = columns[ci]
                            # col.key is "drc:<rd_id>::plot"
                            if "::" not in col.key:
                                continue
                            parent_token = col.key.rsplit("::", 1)[0]
                            av = activity.get(parent_token)
                            if not av:
                                continue
                            snapshot = _av_to_sparkline_snapshot(av)
                            png = render_sparkline_png(snapshot) if snapshot else None
                            if not png:
                                continue
                            tf = NamedTemporaryFile(suffix=".png", delete=False)
                            tf.write(png); tf.close()
                            tempfiles.append(tf.name)
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
