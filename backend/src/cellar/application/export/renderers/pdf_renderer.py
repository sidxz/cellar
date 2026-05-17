from __future__ import annotations
import base64
from pathlib import Path
from typing import Any, AsyncIterator

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.sparkline import (
    SIZE_PRESETS,
    av_to_sparkline_snapshot,
    render_sparkline_png,
)
from cellar.application.export.renderers.structure import (
    STRUCTURE_SIZE_PRESETS,
    render_structure_pngs,
)
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow

PDF_ROW_CAP = 5000
PDF_IMAGE_ROW_CAP = 1000  # above this we ship text-only to keep PDFs <50MB
PDF_TEMPLATE_DIR = Path(__file__).parent / "pdf_template"


def _png_to_data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


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

        embed_images = len(all_rows) <= PDF_IMAGE_ROW_CAP
        image_omission_reason: str | None = None
        if not embed_images:
            image_omission_reason = (
                f"Structure + curve images omitted: {len(all_rows)} rows "
                f"exceeds the {PDF_IMAGE_ROW_CAP}-row image cap."
            )

        size_preset = options.image_size if options.image_size in SIZE_PRESETS else "medium"
        struct_size = options.image_size if options.image_size in STRUCTURE_SIZE_PRESETS else "medium"
        sparkline_w, sparkline_h = SIZE_PRESETS[size_preset]
        struct_w, struct_h = STRUCTURE_SIZE_PRESETS[struct_size]

        sparkline_col_keys = [c.key for c in columns if c.kind == "image_curve"]
        has_structure = any(c.kind == "image_structure" for c in columns)

        # Per-row image dicts: {column_key: data_uri} for curves, plus
        # "structure" → data_uri for the structure column.
        structure_cache: dict[str, str | None] = {}
        rendered_rows: list[dict[str, Any]] = []
        for row in all_rows:
            row_images: dict[str, str] = {}
            if embed_images:
                if has_structure:
                    smiles = (row.raw or {}).get("smiles")
                    if smiles:
                        uri = structure_cache.get(smiles)
                        if uri is None:
                            pngs = render_structure_pngs([smiles], size=struct_size)
                            png = pngs.get(smiles)
                            uri = _png_to_data_uri(png) if png else ""
                            structure_cache[smiles] = uri
                        if uri:
                            row_images["structure"] = uri
                if sparkline_col_keys:
                    activity = (row.raw or {}).get("activity") or {}
                    for col_key in sparkline_col_keys:
                        if "::" not in col_key:
                            continue
                        parent_token = col_key.rsplit("::", 1)[0]
                        av = activity.get(parent_token)
                        if not av:
                            continue
                        snap = av_to_sparkline_snapshot(av)
                        if not snap:
                            continue
                        png = render_sparkline_png(snap, size=size_preset)
                        if png:
                            row_images[col_key] = _png_to_data_uri(png)
            rendered_rows.append({"row": row, "images": row_images})

        extras = options.extras or {}
        tmpl = self._env.get_template("search_report.html.j2")
        html = tmpl.render(
            title=options.title,
            columns=columns,
            rendered_rows=rendered_rows,
            options=options,
            extras=extras,
            embed_images=embed_images,
            image_omission_reason=image_omission_reason,
            sparkline_w=sparkline_w,
            sparkline_h=sparkline_h,
            struct_w=struct_w,
            struct_h=struct_h,
            row_count=len(all_rows),
        )

        from weasyprint import CSS, HTML
        HTML(string=html, base_url=str(PDF_TEMPLATE_DIR)).write_pdf(
            target=str(out_path),
            stylesheets=[CSS(filename=str(PDF_TEMPLATE_DIR / "search_report.css"))],
        )
