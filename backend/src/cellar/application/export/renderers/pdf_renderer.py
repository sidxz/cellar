from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow

PDF_ROW_CAP = 5000
PDF_TEMPLATE_DIR = Path(__file__).parent / "pdf_template"


class PdfRenderer:
    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(PDF_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "j2"]),
        )

    async def render(
        self,
        *,
        columns: list[ColumnSpec],
        batches: AsyncIterator[list[ExportRow]],
        out_path: Path,
        options: RenderOptions,
        row_count_hint: int,
    ) -> None:
        if row_count_hint > PDF_ROW_CAP:
            raise ValueError(
                f"PDF row count {row_count_hint} exceeds {PDF_ROW_CAP} cap — use XLSX for larger exports."
            )

        # Materialize batches once — WeasyPrint needs the full body.
        all_rows: list[ExportRow] = []
        async for batch in batches:
            all_rows.extend(batch)

        tmpl = self._env.get_template("search_report.html.j2")
        html = tmpl.render(
            title=options.title,
            columns=columns,
            rows=all_rows,
            options=options,
        )

        from weasyprint import CSS, HTML
        HTML(string=html, base_url=str(PDF_TEMPLATE_DIR)).write_pdf(
            target=str(out_path),
            stylesheets=[CSS(filename=str(PDF_TEMPLATE_DIR / "search_report.css"))],
        )
