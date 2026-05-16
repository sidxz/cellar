from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

import pytest
from openpyxl import load_workbook

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.excel_renderer import (
    ExcelRenderer,
    SPARKLINE_ROW_CAP,
)
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


async def _batches(rows):
    for b in rows:
        yield b


@pytest.mark.asyncio
async def test_excel_writes_data_sheet_with_numeric_cells(tmp_path: Path):
    cols = [
        ColumnSpec(key="reg", header="Reg #", kind="text"),
        ColumnSpec(key="mw", header="MW", kind="number"),
        ColumnSpec(key="drc:rd1:ec:50.0::value", header="Mtb::EC50", kind="number", unit="µM"),
    ]
    rows = [[ExportRow(cells={"reg": "CV-1", "mw": 421.5, "drc:rd1:ec:50.0::value": 1.23})]]
    out = tmp_path / "out.xlsx"
    await ExcelRenderer().render(
        columns=cols, batches=_batches(rows), out_path=out,
        options=RenderOptions(), row_count_hint=1,
    )
    wb = load_workbook(out)
    ws = wb["Data"]
    assert ws["A1"].value == "Reg #"
    assert ws["B2"].value == 421.5
    assert isinstance(ws["B2"].value, float)
    assert ws["C2"].value == 1.23


@pytest.mark.asyncio
async def test_excel_notes_sheet_when_sparkline_cap_tripped(tmp_path: Path):
    cols = [ColumnSpec(key="reg", header="Reg #", kind="text")]
    big_rows = [[ExportRow(cells={"reg": f"CV-{i}"}) for i in range(SPARKLINE_ROW_CAP + 10)]]
    out = tmp_path / "out.xlsx"
    await ExcelRenderer().render(
        columns=cols, batches=_batches(big_rows), out_path=out,
        options=RenderOptions(), row_count_hint=SPARKLINE_ROW_CAP + 10,
    )
    wb = load_workbook(out)
    assert "Notes" in wb.sheetnames
    notes_text = "\n".join(str(c.value or "") for c in wb["Notes"]["A"])
    assert "Sparklines omitted" in notes_text
