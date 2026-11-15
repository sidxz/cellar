"""A run's report in the standard export formats.

CSV is the results table alone, a file other tools read. Excel holds the records
(Results, Steps, and each signal's traces, measured and as the derivative) with
the ChemCellar mark, run details and who exported it on its Notes sheet, apart
from them. The PDF is the run report: details, the traces and shift figures as
vector SVG, the results and the step review log.
"""

from __future__ import annotations

import base64
import csv
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openpyxl import Workbook
from openpyxl.styles import Font

from cellar.application.export.renderers.base import BRAND, LOGO_SVG, RenderOptions
from cellar.application.export.renderers.excel_renderer import write_notes
from cellar.application.export.renderers.pdf_renderer import PDF_TEMPLATE_DIR
from cellar.application.export.renderers.run_figures import shift_svg, traces_svg
from cellar.application.export.run_report import RunReport, RunSignal
from cellar.domain.export.enums import ExportFormat

HIT_TEXT = {True: "Hit", False: "Not a hit", None: ""}


async def render_run_report(
    report: RunReport, fmt: ExportFormat, out_path: Path, options: RenderOptions
) -> None:
    if fmt == ExportFormat.CSV:
        _write_csv(report, out_path)
    elif fmt == ExportFormat.XLSX:
        _write_xlsx(report, out_path, options)
    elif fmt == ExportFormat.PDF:
        _write_pdf(report, out_path, options)
    else:
        raise ValueError(f"A run exports as Excel, CSV or PDF, not {fmt.value}")


# ---------------------------------------------------------------------------
# The records: results and steps as tables of raw values
# ---------------------------------------------------------------------------


def results_table(report: RunReport) -> tuple[list[str], list[list]]:
    headers = [
        "Position",
        "Sample",
        "Registration #",
        "Batch",
        "Label",
        f"Concentration ({report.dose_unit})",
        "Role",
    ]
    for w in report.windows:
        headers += [f"{w.name} Tm (°C)", f"{w.name} ΔTm (°C)", f"{w.name} status"]
    headers += ["Hit", "Note"]
    rows = []
    for r in report.rows:
        row = [
            r.position,
            r.sample,
            r.registration_number,
            r.batch,
            r.label,
            r.concentration,
            r.role,
        ]
        for w in report.windows:
            cell = r.cells.get(w.name)
            row += [cell.tm, cell.delta_tm, cell.status] if cell else [None, None, None]
        row += [HIT_TEXT[r.hit], r.note]
        rows.append(row)
    return headers, rows


def steps_table(report: RunReport) -> tuple[list[str], list[list]]:
    headers = [
        "Position",
        "Sample",
        "Signal",
        "Step (°C)",
        "Source",
        "Status",
        "Instrument value (°C)",
        "Reason",
        "Changed by",
        "Changed at (UTC)",
    ]
    rows = [
        [
            s.position,
            s.sample,
            s.signal,
            s.value,
            s.source,
            s.status,
            s.instrument_value,
            s.reason,
            s.changed_by,
            s.changed_at.strftime("%Y-%m-%d %H:%M") if s.changed_at else None,
        ]
        for s in report.steps
    ]
    return headers, rows


def _write_csv(report: RunReport, out_path: Path) -> None:
    headers, rows = results_table(report)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(["" if v is None else v for v in row] for row in rows)


def _write_xlsx(report: RunReport, out_path: Path, options: RenderOptions) -> None:
    wb = Workbook()
    for title, (headers, rows) in (
        ("Results", results_table(report)),
        ("Steps", steps_table(report)),
    ):
        ws = wb.active if title == "Results" else wb.create_sheet(title)
        ws.title = title
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append(row)
        ws.freeze_panes = "A2"
    for signal in report.signals:
        _write_traces(wb.create_sheet(_sheet_name(signal)), signal)

    notes = wb.create_sheet("Notes")
    write_notes(notes, options, len(report.rows))
    for line in _details(report):
        notes.append(["", line])
    wb.properties.title = f"{BRAND} · {options.title}"
    wb.properties.creator = options.extras.get("exported_by") or BRAND
    wb.properties.description = options.attribution
    wb.save(out_path)


def _write_traces(ws, signal: RunSignal) -> None:
    """Each position has its own temperatures, so two columns each: its
    temperature and its signal, under a "position · sample" heading."""
    first, second = [], []
    for t in signal.traces:
        first += [f"{t.position} · {t.sample}", None]
        second += [signal.x_label, signal.label if signal.view == "measured" else "Derivative"]
    ws.append(first)
    ws.append(second)
    for cell in [*ws[1], *ws[2]]:
        cell.font = Font(bold=True)
    for i in range(max((len(t.x) for t in signal.traces), default=0)):
        row: list = []
        for t in signal.traces:
            row += [t.x[i], t.y[i]] if i < len(t.x) else [None, None]
        ws.append(row)
    ws.freeze_panes = "A3"


def _sheet_name(signal: RunSignal) -> str:
    """ "Ratio 350-330 derivative": Excel forbids / \\ ? * [ ] : and caps a name at 31."""
    name = re.sub(r"[/\\?*\[\]:]", "-", f"{signal.label} {signal.view}")
    return name[:31]


def _details(report: RunReport) -> list[str]:
    lines = [
        f"Protocol: {report.protocol}",
        f"Run date: {report.run_date.isoformat()}",
        f"Status: {report.status.capitalize()}",
        f"Holder: {report.holder}",
    ]
    if report.operator:
        lines.append(f"Operator: {report.operator}")
    if report.notes:
        lines.append(f"Run notes: {report.notes}")
    for w in report.windows:
        ref = f"{w.reference_tm:.1f} °C (n={w.reference_count})" if w.reference_tm else "none"
        lines.append(
            f"Window {w.name}: {w.channel_label}, {w.low:g}\u2013{w.high:g} °C, reference Tm {ref}"
        )
    lines.append("Hit rule: " + ("; ".join(report.hit_rule) if report.hit_rule else "none"))
    for s in report.signals:
        if s.view == "derivative" and s.window is not None:
            lines.append(f"{s.label} derivative smoothed over {s.window:.3g} °C")
    return lines


# ---------------------------------------------------------------------------
# The PDF report
# ---------------------------------------------------------------------------


def _svg_uri(svg: str | None) -> str | None:
    if not svg:
        return None
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode("ascii")


def _tm(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}"


def _delta(v: float | None) -> str:
    """A shift as the Traces tab writes it: signed, one decimal, a true minus sign."""
    if v is None:
        return "—"
    r = round(v, 1)
    return f"{'+' if r > 0 else '\u2212' if r < 0 else ''}{abs(r):.1f}"


def _write_pdf(report: RunReport, out_path: Path, options: RenderOptions) -> None:
    env = Environment(
        loader=FileSystemLoader(str(PDF_TEMPLATE_DIR)), autoescape=select_autoescape(["j2"])
    )
    env.filters["tm"] = _tm
    env.filters["delta"] = _delta
    env.filters["num"] = lambda v: "—" if v is None else f"{v:g}"
    _, steps = steps_table(report)
    html = env.get_template("run_report.html.j2").render(
        brand=BRAND,
        logo_src=LOGO_SVG.as_uri(),
        title=options.title,
        attribution=options.attribution,
        extras=options.extras or {},
        report=report,
        details=_details(report),
        traces=_svg_uri(traces_svg(report)),
        shifts=[(w, _svg_uri(shift_svg(report, w))) for w in report.windows],
        hit_text=HIT_TEXT,
        steps=steps,
    )
    from weasyprint import CSS, HTML

    HTML(string=html, base_url=str(PDF_TEMPLATE_DIR)).write_pdf(
        target=str(out_path),
        stylesheets=[
            CSS(filename=str(PDF_TEMPLATE_DIR / "search_report.css")),
            CSS(filename=str(PDF_TEMPLATE_DIR / "run_report.css")),
        ],
    )
