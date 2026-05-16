from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

import pytest

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.csv_renderer import CsvRenderer
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


async def _batches(rows: list[list[ExportRow]]) -> AsyncIterator[list[ExportRow]]:
    for b in rows:
        yield b


@pytest.mark.asyncio
async def test_csv_writes_headers_and_rows(tmp_path: Path):
    cols = [
        ColumnSpec(key="reg", header="Reg #", kind="text"),
        ColumnSpec(key="mw", header="MW", kind="number"),
        ColumnSpec(key="drc:rd1:ec:50.0::value", header="Mtb::EC50", kind="number", unit="µM"),
        ColumnSpec(key="drc:rd1:ec:50.0::qualifier", header="Mtb::EC50::q", kind="qualifier"),
    ]
    out = tmp_path / "out.csv"
    renderer = CsvRenderer()
    rows = [[
        ExportRow(cells={"reg": "CV-1", "mw": 421.5, "drc:rd1:ec:50.0::value": 1.23,
                         "drc:rd1:ec:50.0::qualifier": "="}),
        ExportRow(cells={"reg": "CV-2", "mw": 380.1, "drc:rd1:ec:50.0::value": None,
                         "drc:rd1:ec:50.0::qualifier": "ND"}),
    ]]
    await renderer.render(
        columns=cols,
        batches=_batches(rows),
        out_path=out,
        options=RenderOptions(),
        row_count_hint=2,
    )
    text = out.open(encoding="utf-8-sig", newline="").read()
    assert text.startswith("Reg #,MW,Mtb::EC50,Mtb::EC50::q\r\n")
    assert "CV-1,421.5,1.23,=\r\n" in text
    assert "CV-2,380.1,,ND\r\n" in text
