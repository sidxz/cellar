"""Plate geometry: dimensions per format, row labels, and well reading order.

Mirrors ``frontend/src/features/screening-assay/lib/plate-dimensions.ts`` so a
well's position means the same thing on both sides of the API.
"""

from __future__ import annotations

from cellar.domain.shared.enums import PlateFormat

_DIMENSIONS: dict[str, tuple[int, int]] = {
    PlateFormat.F6: (2, 3),
    PlateFormat.F12: (3, 4),
    PlateFormat.F24: (4, 6),
    PlateFormat.F48: (6, 8),
    PlateFormat.F96: (8, 12),
    PlateFormat.F384: (16, 24),
    PlateFormat.F1536: (32, 48),
}


def plate_dimensions(
    format: str | None, holder_rows: int | None, holder_columns: int | None
) -> tuple[int, int] | None:
    """(rows, columns): the holder's own size when both are set, else the format's."""
    if holder_rows is not None and holder_columns is not None:
        return (holder_rows, holder_columns)
    return _DIMENSIONS.get(format) if format else None


def row_index(label: str) -> int:
    """0-based row index for a row label: A→0, P→15, AA→26, AF→31."""
    if len(label) == 1:
        return ord(label) - 65
    return (ord(label[0]) - 65 + 1) * 26 + ord(label[1]) - 65


def well_order(row_label: str, column: int, n_columns: int) -> int:
    """1-based position in row-major reading order (A01=1, A02=2, B01=n_columns+1)."""
    return row_index(row_label) * n_columns + column
