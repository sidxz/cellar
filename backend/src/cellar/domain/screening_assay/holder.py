"""Holder vocabulary: how positions and holders are named for display.

The only domain module that spells instrument-holder wording.
"""

from __future__ import annotations

from cellar.domain.screening_assay.enums import HolderKind


def row_letters(row: int) -> str:
    """1-based row number to letters: 1 -> "A", 26 -> "Z", 27 -> "AA"."""
    letters = ""
    while row > 0:
        row, rem = divmod(row - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def position_label(kind: HolderKind, row: str, column: int) -> str:
    if kind is HolderKind.CASSETTE:
        return f"Capillary {column}"
    return f"{row}{column}"


def holder_label(kind: HolderKind, rows: int | None, columns: int | None) -> str:
    if kind is HolderKind.CASSETTE:
        return f"Cassette, {columns} capillaries"
    if rows is None or columns is None:
        return "Plate"
    return f"Plate, {rows} × {columns}"
