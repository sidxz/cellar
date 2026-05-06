"""Tabular file parser — application-layer Protocol + shared data types.

Importers (plate maps, readout files, long-format run files) consume tabular
data via the ``TabularParser`` Protocol. Concrete implementations (CSV / XLSX
parsing) live in ``infrastructure.parsers.tabular_file`` and are injected.

Keeping ``ParsedTable`` and ``TabularParseError`` here lets application code
type rows, errors, and Protocol bounds without importing infrastructure —
preserving the outward-dependency rule.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


class TabularParseError(ValueError):
    """Raised when a file cannot be parsed as a supported tabular format."""


@dataclass
class ParsedTable:
    """An immutable, in-memory tabular file."""

    headers: list[str]
    rows: list[dict[str, str]]
    source_format: str  # "xlsx" | "csv"

    def iter_rows(self) -> Iterator[dict[str, str]]:
        return iter(self.rows)

    @property
    def row_count(self) -> int:
        return len(self.rows)


class TabularParser(Protocol):
    """Parses CSV/XLSX bytes into a ``ParsedTable``.

    Implementations detect format from filename extension + magic bytes and
    raise ``TabularParseError`` on unparseable input.
    """

    def parse(self, content: bytes, filename: str = "") -> ParsedTable: ...
