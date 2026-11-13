"""Reader for the NanoTemper Prometheus raw Excel export (nanoDSF).

Layout: an ``Overview`` sheet with one row per capillary (sample ID, run settings,
reported onsets and inflection points), and one sheet per signal with three columns
per capillary (time, temperature, value) under a ``Capillary #<n>`` header.
"""

from __future__ import annotations

import io
import math
import re
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import openpyxl

from cellar.application.screening.instrument_export import (
    ExportChannel,
    ExportCurve,
    ExportPosition,
    HolderLayout,
    InstrumentExport,
    InstrumentFileError,
    ReportedValue,
)
from cellar.domain.screening_assay.enums import HolderKind

_CHANNEL_KEYS = {"ratio": "ratio", "330nm": "f330", "350nm": "f350", "scattering": "scattering"}
_CHANNEL_LABELS = {
    "ratio": "Ratio 350/330",
    "f330": "330 nm",
    "f350": "350 nm",
    "scattering": "Scattering",
}
_SETTINGS = (
    "Excitation Power",
    "Start Temperature",
    "End Temperature",
    "Temperature Slope",
    "Start Time",
    "Duration",
)
_REPORTED = re.compile(r"^(Onset|Inflection Point)\s*#\s*(\d+)\s*for\s*(.+)$", re.IGNORECASE)
_POSITION = re.compile(r"#\s*(\d+)")
_UNIT = re.compile(r"\[([^\]]*)\]")

Rows = list[tuple[Any, ...]]


def _channel_key(title: str) -> str:
    title = title.strip()
    return _CHANNEL_KEYS.get(title.lower(), title)


def _is_raw(row1: Sequence[Any]) -> bool:
    return (
        bool(row1) and isinstance(row1[0], str) and row1[0].strip().lower().startswith("capillary")
    )


def _is_processed(row1: Sequence[Any]) -> bool:
    return len(row1) > 1 and isinstance(row1[1], str) and row1[1].strip().lower() == "capillary"


def _number(cell: Any) -> bool:
    return isinstance(cell, int | float) and not isinstance(cell, bool) and math.isfinite(cell)


def _cell(row: Sequence[Any], index: int) -> Any:
    return row[index] if index < len(row) else None


def _unit(header: Any) -> str | None:
    units = _UNIT.findall(str(header or ""))
    return units[-1].strip() if units else None


def _name(header: Any) -> str | None:
    """The quantity's name: the header text before its last ``[unit]``."""
    text = str(header or "")
    name = text[: text.rfind("[")] if "[" in text else text
    return name.strip() or None


def _load(content: bytes) -> tuple[Rows, list[tuple[str, Rows]]]:
    """The ``Overview`` rows, and (title, rows) of every other sheet, in workbook order."""
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheets = [(ws.title, list(ws.iter_rows(values_only=True))) for ws in wb.worksheets]
    finally:
        wb.close()
    overview = next((rows for title, rows in sheets if title.strip().lower() == "overview"), None)
    if overview is None:
        raise InstrumentFileError("The workbook has no Overview sheet.")
    others = [(title, rows) for title, rows in sheets if title.strip().lower() != "overview"]
    return overview, others


class PrometheusRawXlsxReader:
    id = "nanotemper-prometheus-raw-xlsx"
    label = "NanoTemper Prometheus raw export (.xlsx)"
    hint = (
        "Export the raw data from the instrument's software as an Excel workbook. "
        "The processed export is not supported."
    )

    def recognises(self, content: bytes, filename: str) -> bool:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                titles = [ws.title.strip().lower() for ws in wb.worksheets]
                first_rows = [
                    next(ws.iter_rows(max_row=1, values_only=True), ())
                    for ws in wb.worksheets
                    if ws.title.strip().lower() != "overview"
                ]
            finally:
                wb.close()
            return "overview" in titles and any(_is_raw(r) or _is_processed(r) for r in first_rows)
        except Exception:  # any unreadable file is simply not this format
            return False

    def read(self, content: bytes, filename: str) -> InstrumentExport:
        overview, others = _load(content)
        raw = [(title, rows) for title, rows in others if rows and _is_raw(rows[0])]
        if not raw:
            raise InstrumentFileError(
                "This is the instrument's processed export. "
                "Export the raw data and upload that file."
            )

        headers = (
            [str(h).strip() if h is not None else "" for h in overview[0]] if overview else []
        )
        position_rows = [
            (row[0], dict(zip(headers, row, strict=False)))
            for row in overview[1:]
            if row and isinstance(row[0], int) and not isinstance(row[0], bool)
        ]
        if not position_rows:
            raise InstrumentFileError("The Overview sheet lists no capillaries.")
        counts = Counter(n for n, _ in position_rows)
        if bad := sorted(n for n in counts if n < 1):
            raise InstrumentFileError(
                f"The Overview sheet numbers a capillary {bad[0]}; capillary numbers start at 1."
            )
        if twice := sorted(n for n, k in counts.items() if k > 1):
            noun = "capillary" if len(twice) == 1 else "capillaries"
            raise InstrumentFileError(
                f"The Overview sheet lists {noun} {', '.join(map(str, twice))} more than once."
            )
        positions = tuple(
            ExportPosition(
                row=1,
                column=n,
                label="" if r.get("Sample ID") is None else str(r["Sample ID"]).strip(),
            )
            for n, r in position_rows
        )
        numbers = {p.column for p in positions}

        channels: list[ExportChannel] = []
        curves: list[ExportCurve] = []
        for title, rows in raw:
            key = _channel_key(title)
            units = rows[1] if len(rows) > 1 else ()
            y_unit = _unit(_cell(units, 2))
            channel = ExportChannel(
                key=key,
                label=_CHANNEL_LABELS.get(key, title.strip()),
                x_unit=_unit(_cell(units, 1)) or "",
                y_unit=None if y_unit == "-" else y_unit,
                x_label=_name(_cell(units, 1)),
            )
            channels.append(channel)
            curves += _curves(key, rows, numbers)

        return InstrumentExport(
            reader=self.id,
            holder=HolderLayout(HolderKind.CASSETTE, 1, max(numbers)),
            positions=positions,
            channels=tuple(channels),
            curves=tuple(curves),
            reported=_reported(headers, position_rows, channels, raw),
            settings=_settings(position_rows[0][1]),
        )


def _curves(key: str, rows: Rows, numbers: set[int]) -> list[ExportCurve]:
    curves = []
    header = rows[0]
    for j in range(0, len(header), 3):
        match = _POSITION.search(str(header[j] or ""))
        if not match or int(match.group(1)) not in numbers:
            continue
        kept = [
            (float(t), float(v))
            for row in rows[2:]
            if _number(t := _cell(row, j + 1)) and _number(v := _cell(row, j + 2))
        ]
        if len(kept) >= 2:
            xs, ys = zip(*kept, strict=True)
            curves.append(ExportCurve(row=1, column=int(match.group(1)), channel=key, x=xs, y=ys))
    return curves


def _reported(
    headers: list[str],
    position_rows: list[tuple[int, dict[str, Any]]],
    channels: list[ExportChannel],
    raw: list[tuple[str, Rows]],
) -> tuple[ReportedValue, ...]:
    by_title = {title.strip().lower(): ch for (title, _), ch in zip(raw, channels, strict=True)}
    columns = []
    for header in headers:
        match = _REPORTED.match(header)
        if not match:
            continue
        name = match.group(3).strip()
        channel = by_title.get(name.lower())
        key = channel.key if channel else _channel_key(name)
        unit = (channel or channels[0]).x_unit
        kind = "onset" if match.group(1).lower() == "onset" else "transition"
        columns.append((header, key, kind, int(match.group(2)), unit))
    return tuple(
        ReportedValue(
            row=1,
            column=n,
            channel=key,
            kind=kind,
            ordinal=ordinal,
            label=header,
            value=float(r[header]),
            unit=unit,
        )
        for n, r in position_rows
        for header, key, kind, ordinal, unit in columns
        if _number(r.get(header))
    )


def _settings(first: dict[str, Any]) -> dict[str, str]:
    settings = {}
    for name in _SETTINGS:
        value = first.get(name)
        if value is None or value == "":
            continue
        settings[name] = value.isoformat() if isinstance(value, datetime) else str(value)
    return settings
