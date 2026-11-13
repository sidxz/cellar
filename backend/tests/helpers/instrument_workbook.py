"""Synthetic NanoTemper Prometheus exports, built in code from the documented file layout.

No laboratory data: sample IDs, values and dates are invented.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from openpyxl import Workbook

SETTINGS_HEADERS = [
    "Capillary",
    "Sample ID",
    "Excitation Power",
    "Start Temperature",
    "End Temperature",
    "Temperature Slope",
    "Start Time",
    "Duration",
]
VALUE_HEADERS = {
    "Ratio": "Ratio of Integrated Fluorescence at 350nm/330nm [-]",
    "330nm": "Integrated Fluorescence at 330nm [counts*mm]",
    "350nm": "Integrated Fluorescence at 350nm [counts*mm]",
    "Scattering": "Scattering [mAU]",
}


def temperature(i: int) -> float:
    # Rounded so the value survives openpyxl's 16-significant-digit float write unchanged.
    return round(25.0 + i * 0.057, 3)


def _default_reported(numbers: Sequence[int]) -> dict[str, dict[int, float | None]]:
    return {
        "Onset #1 for Ratio ": {n: 50.0 + n * 0.1 for n in numbers},
        "Inflection Point #1 for Ratio ": {n: 55.0 + n * 0.1 for n in numbers},
        "Inflection Point #2 for Ratio ": {n: 70.0 + n * 0.1 for n in numbers if n % 2},
        "Inflection Point #3 for Ratio ": {},
    }


def _save(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_raw_workbook(
    *,
    positions: Mapping[int, str | None] | None = None,
    points: int | Mapping[int, int] = 50,
    sheets: Sequence[str] = ("Ratio", "330nm", "350nm", "Scattering"),
    reported: Mapping[str, Mapping[int, float | None]] | None = None,
    cells: Mapping[tuple[str, int, int, str], object] | None = None,
) -> bytes:
    """A raw export: ``Overview`` plus one three-column group per position on each signal sheet.

    ``cells`` overrides one data cell: (sheet, position number, 0-based data row, "temperature"
    or "value") -> the cell's content.
    """
    positions = positions if positions is not None else {n: f"S{n}" for n in range(1, 25)}
    numbers = list(positions)
    reported = reported if reported is not None else _default_reported(numbers)
    cells = cells or {}

    wb = Workbook()
    overview = wb.active
    overview.title = "Overview"
    overview.append(SETTINGS_HEADERS + list(reported))
    for n in numbers:
        start = datetime(2026, 1, 5, 9, 0) + timedelta(minutes=n)
        overview.append(
            [n, positions[n], 0.45, 25, 95, 1, start, timedelta(minutes=70)]
            + [values.get(n) for values in reported.values()]
        )

    for title in sheets:
        ws = wb.create_sheet(title)
        captions = [
            f"Capillary #{n} ({positions[n]})" if positions[n] else f"Capillary #{n}"
            for n in numbers
        ]
        ws.append([c for caption in captions for c in (caption, caption, caption)])
        value_header = VALUE_HEADERS.get(title, f"{title} [-]")
        ws.append(["Time [s]", "Temperature [°C]", value_header] * len(numbers))
        counts = {n: points if isinstance(points, int) else points[n] for n in numbers}
        for i in range(max(counts.values(), default=0)):
            row: list[object] = []
            for n in numbers:
                if i >= counts[n]:
                    row += [None, None, None]
                    continue
                temp = cells.get((title, n, i, "temperature"), temperature(i))
                value = cells.get((title, n, i, "value"), 0.8 + i * 0.001 + n * 0.01)
                row += [i * 3.0, temp, value]
            ws.append(row)
    return _save(wb)


def build_processed_workbook() -> bytes:
    """A processed export: signal sheets with one column per position under a "Capillary" row."""
    wb = Workbook()
    overview = wb.active
    overview.title = "Overview"
    overview.append(SETTINGS_HEADERS)
    for n in (1, 2):
        overview.append([n, f"S{n}", 0.45, 25, 95, 1, datetime(2026, 1, 5, 9, 0), None])
    ws = wb.create_sheet("Ratio")
    ws.append([None, "Capillary", 1, 2])
    ws.append(["Time [s]", "Temperature [°C]", None, None])
    ws.append([None, None, "Ratio", "Ratio"])
    for i in range(5):
        ws.append([i * 3.0, temperature(i), 0.8, 0.81])
    return _save(wb)
