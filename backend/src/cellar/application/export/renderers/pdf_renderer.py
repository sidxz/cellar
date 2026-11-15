from __future__ import annotations

import base64
import re
from collections.abc import AsyncIterator
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cellar.application.export.renderers.base import BRAND, LOGO_SVG, RenderOptions
from cellar.application.export.renderers.sparkline import SIZE_PRESETS, column_plot
from cellar.application.export.renderers.structure import (
    STRUCTURE_SIZE_PRESETS,
    render_structure_svgs,
)
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow, group_spans

PDF_ROW_CAP = 5000
PDF_IMAGE_ROW_CAP = 1000  # above this we ship text-only to keep PDFs <50MB
PDF_TEMPLATE_DIR = Path(__file__).parent / "pdf_template"

# A bound as the row stream renders it for the data formats: ">100.0", "<0.1".
_BOUND = re.compile(r"^([<>])\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)$")


def _svg_data_uri(svg: bytes | str) -> str:
    """Structures and plots go in as SVG: vector, so sharp when zoomed or printed."""
    data = svg.encode() if isinstance(svg, str) else svg
    return "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")


def to_precision(x: float, p: int) -> str:
    """JavaScript's ``Number.prototype.toPrecision``, so a cell reads as the grid's
    does: 70.38, 35.50, 0.05070, 1.235e+4. Half rounds away from zero, on the
    float's exact value."""
    if x == 0:
        return "0" if p == 1 else "0." + "0" * (p - 1)
    d = Decimal(x)
    e = d.adjusted()
    if abs(d.scaleb(-e).quantize(Decimal(1).scaleb(1 - p), ROUND_HALF_UP)) >= 10:
        e += 1  # rounding carried into a new digit: 9.9995 → 10.00
    if e < -6 or e >= p:
        mantissa = d.scaleb(-e).quantize(Decimal(1).scaleb(1 - p), ROUND_HALF_UP)
        return f"{mantissa:f}e{'+' if e >= 0 else '-'}{abs(e)}"
    return f"{d.quantize(Decimal(1).scaleb(e - p + 1), ROUND_HALF_UP):f}"


def cell_text(value: Any, column: ColumnSpec) -> str | None:
    """A cell as the grid shows it: properties to their decimals (MW 365.4),
    values to their significant figures, a bound as "> 100.0". None is no data."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        if column.digits is not None:
            return f"{Decimal(value).quantize(Decimal(1).scaleb(-column.digits), ROUND_HALF_UP):f}"
        if column.precision is not None:
            return to_precision(float(value), column.precision)
        return str(value) if isinstance(value, int) else f"{value:g}"
    if column.precision is not None and (bound := _BOUND.match(str(value))):
        return f"{bound.group(1)} {to_precision(float(bound.group(2)), column.precision)}"
    return str(value)


class PdfRenderer:
    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(PDF_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "j2"]),
        )
        self._env.filters["cell_text"] = lambda value, column: cell_text(value, column)

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
                f"PDF row count {row_count_hint} exceeds {PDF_ROW_CAP} cap — "
                "use XLSX for larger exports."
            )

        # Materialize batches once — WeasyPrint needs the full body.
        all_rows: list[ExportRow] = []
        async for batch in batches:
            all_rows.extend(batch)

        html = self.html(columns=columns, rows=all_rows, options=options)

        from weasyprint import CSS, HTML

        HTML(string=html, base_url=str(PDF_TEMPLATE_DIR)).write_pdf(
            target=str(out_path),
            stylesheets=[CSS(filename=str(PDF_TEMPLATE_DIR / "search_report.css"))],
        )

    def html(
        self, *, columns: list[ColumnSpec], rows: list[ExportRow], options: RenderOptions
    ) -> str:
        embed_images = len(rows) <= PDF_IMAGE_ROW_CAP
        image_omission_reason: str | None = None
        if not embed_images:
            image_omission_reason = (
                f"Structure + curve images omitted: {len(rows)} rows "
                f"exceeds the {PDF_IMAGE_ROW_CAP}-row image cap."
            )

        size_preset = options.image_size if options.image_size in SIZE_PRESETS else "medium"
        struct_size = (
            options.image_size if options.image_size in STRUCTURE_SIZE_PRESETS else "medium"
        )
        sparkline_w, sparkline_h = SIZE_PRESETS[size_preset]
        struct_w, struct_h = STRUCTURE_SIZE_PRESETS[struct_size]

        curve_columns = [c for c in columns if c.kind == "image_curve"]
        has_structure = any(c.kind == "image_structure" for c in columns)

        # Per-row image dicts: {column_key: data_uri} for curves, plus
        # "structure" → data_uri for the structure column.
        structure_cache: dict[str, str | None] = {}
        rendered_rows: list[dict[str, Any]] = []
        for row in rows:
            row_images: dict[str, str] = {}
            if embed_images:
                if has_structure:
                    smiles = (row.raw or {}).get("smiles")
                    if smiles:
                        uri = structure_cache.get(smiles)
                        if uri is None:
                            svg = render_structure_svgs([smiles], size=struct_size).get(smiles)
                            uri = _svg_data_uri(svg) if svg else ""
                            structure_cache[smiles] = uri
                        if uri:
                            row_images["structure"] = uri
                activity = (row.raw or {}).get("activity") or {}
                for column in curve_columns:
                    svg = column_plot(column, activity, size=size_preset, fmt="svg")
                    if svg:
                        row_images[column.key] = _svg_data_uri(svg)
            rendered_rows.append({"row": row, "images": row_images})

        extras = options.extras or {}
        tmpl = self._env.get_template("search_report.html.j2")
        return tmpl.render(
            brand=BRAND,
            logo_src=LOGO_SVG.as_uri(),
            title=options.title,
            attribution=options.attribution,
            columns=columns,
            # Reg # and Name hold codes like SACC-0014683 that must not wrap mid-word.
            identity_keys=("registration_number", "name"),
            # Protocol headers, then a split protocol's group headers under them
            # (an overlaid group with its curve's colour swatch), as in the grid.
            group_spans=[
                {"label": c.group, "span": end - start + 1}
                for start, end, c in group_spans(columns, key=lambda c: c.group)
            ],
            subgroup_spans=[
                {"label": c.subgroup, "span": end - start + 1, "color": c.group_color}
                for start, end, c in group_spans(
                    columns, key=lambda c: (c.group, c.subgroup, c.group_color)
                )
            ]
            if any(c.subgroup for c in columns)
            else [],
            rendered_rows=rendered_rows,
            options=options,
            extras=extras,
            embed_images=embed_images,
            image_omission_reason=image_omission_reason,
            sparkline_w=sparkline_w,
            sparkline_h=sparkline_h,
            struct_w=struct_w,
            struct_h=struct_h,
            row_count=len(rows),
        )
