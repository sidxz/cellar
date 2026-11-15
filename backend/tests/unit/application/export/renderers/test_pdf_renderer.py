from __future__ import annotations

from pathlib import Path

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
        columns=cols,
        batches=_batches(rows),
        out_path=out,
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
            columns=cols,
            batches=_batches(rows),
            out_path=out,
            options=RenderOptions(),
            row_count_hint=PDF_ROW_CAP + 1,
        )


# ---------------------------------------------------------------------------
# Cells read as the grid's; the header says ChemCellar, when and by whom.
# ---------------------------------------------------------------------------

from cellar.application.export.renderers.pdf_renderer import cell_text, to_precision  # noqa: E402


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (70.38, "70.38"),
        (35.5, "35.50"),
        (-1.105, "-1.105"),
        (6.25, "6.250"),
        (0.0507, "0.05070"),
        (1234.5, "1235"),
        (12345.0, "1.235e+4"),
        (9999.5, "1.000e+4"),
        (0.0000001234, "1.234e-7"),
        (0.0, "0.000"),
    ],
)
def test_values_read_like_javascripts_to_precision(value, expected):
    assert to_precision(value, 4) == expected


def test_cells_take_the_grids_decimals_figures_and_bounds():
    value = ColumnSpec(key="v", header="IC50", kind="number", precision=4)
    mw = ColumnSpec(key="mw", header="MW", kind="number", digits=1)
    hbd = ColumnSpec(key="hbd", header="HBD", kind="number")
    assert cell_text(70.38, value) == "70.38"
    assert cell_text(">100.0", value) == "> 100.0"
    assert cell_text("ND", value) == "ND"
    assert cell_text(None, value) is None
    assert cell_text(1234.56, mw) == "1234.6"  # never 1.23e+03
    assert cell_text(365.45, mw) == "365.4"  # the float sits below .45
    assert cell_text(1, hbd) == "1"


def test_the_report_keeps_header_case_and_names_who_exported_it():
    cols = [
        ColumnSpec(key="structure", header="Structure", kind="image_structure"),
        ColumnSpec(key="reg", header="Reg #", kind="text"),
        ColumnSpec(
            key="drc:r:ic:50.0@cond:10 µM::value",
            header="IC50",
            kind="number",
            unit="µM",
            group="PRT-1 InhA · by ATP",
            subgroup="10 µM",
            group_color="#3b6fb6",
            precision=4,
        ),
    ]
    html = PdfRenderer().html(
        columns=cols,
        rows=[
            ExportRow(
                cells={"reg": "CV-1", "drc:r:ic:50.0@cond:10 µM::value": 1.33},
                raw={"smiles": "CCO"},
            )
        ],
        options=RenderOptions(
            title="Search results",
            extras={
                "exported_at": "2026-11-15 19:35 UTC",
                "exported_by": "ada@lab.org",
                "query_summary": "All projects · Tested in InhA (any run, split by ATP)",
            },
        ),
    )
    assert "ChemCellar" in html and "chemcellar-logo.svg" in html
    assert "Exported 2026-11-15 19:35 UTC" in html and "by ada@lab.org" in html
    assert "ChemCellar export · 2026-11-15 19:35 UTC · ada@lab.org" in html  # every page's footer
    assert "Tested in InhA (any run, split by ATP)" in html
    assert "PRT-1 InhA · by ATP" in html and "10 µM" in html  # protocol row, then its group
    assert "background: #3b6fb6" in html
    assert "1.330" in html
    # Vector, so the structure stays sharp when the PDF is zoomed or printed.
    assert "data:image/svg+xml" in html and "data:image/png" not in html
