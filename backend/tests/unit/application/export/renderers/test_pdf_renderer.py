from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

import pytest

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.pdf_renderer import PDF_ROW_CAP, PdfRenderer
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow


async def _batches(rows):
    for b in rows:
        yield b


@pytest.mark.asyncio
async def test_pdf_renders_a_small_report(tmp_path: Path):
    cols = [
        ColumnSpec(key="reg", header="Reg #", kind="text"),
        ColumnSpec(key="mw", header="MW", kind="number"),
    ]
    rows = [[ExportRow(cells={"reg": "CV-1", "mw": 421.5})]]
    out = tmp_path / "out.pdf"
    await PdfRenderer().render(
        columns=cols, batches=_batches(rows), out_path=out,
        options=RenderOptions(title="Test export"),
        row_count_hint=1,
    )
    data = out.read_bytes()
    assert data.startswith(b"%PDF")  # valid PDF header


@pytest.mark.asyncio
async def test_pdf_refuses_above_row_cap(tmp_path: Path):
    cols = [ColumnSpec(key="reg", header="Reg #", kind="text")]
    rows = [[ExportRow(cells={"reg": f"CV-{i}"}) for i in range(PDF_ROW_CAP + 1)]]
    out = tmp_path / "out.pdf"
    with pytest.raises(ValueError, match="exceeds"):
        await PdfRenderer().render(
            columns=cols, batches=_batches(rows), out_path=out,
            options=RenderOptions(), row_count_hint=PDF_ROW_CAP + 1,
        )
