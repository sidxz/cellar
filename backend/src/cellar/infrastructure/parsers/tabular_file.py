"""CSV/XLSX implementation of the ``TabularParser`` Protocol.

Format is detected from the filename extension and the file's magic bytes
(xlsx is a zip; csv is plain text). The application layer owns
``ParsedTable`` and ``TabularParseError``; this module is the concrete impl.
"""

from __future__ import annotations

import csv
import io

from cellar.application.shared.parsers import ParsedTable, TabularParseError

__all__ = ["ParsedTable", "TabularFileParser", "TabularParseError", "parse_tabular"]


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

_XLSX_MAGIC = b"PK\x03\x04"  # ZIP signature; xlsx is a zip container


def _detect_format(content: bytes, filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".xlsx") or content[:4] == _XLSX_MAGIC:
        return "xlsx"
    return "csv"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def parse_tabular(
    content: bytes,
    filename: str = "",
    *,
    max_rows: int | None = None,
    quotechar: str | None = None,
) -> ParsedTable:
    """Parse a tabular file into a ParsedTable.

    Detects xlsx vs csv from extension + magic bytes. xlsx is read with
    openpyxl in read-only mode; csv falls back to delimiter-sniffing
    against `,;\\t|` and tolerates UTF-8 BOM.

    With ``max_rows``, reading stops once ``max_rows + 1`` non-blank rows are
    read, so a caller can refuse a longer file without every row being built.

    ``quotechar`` fixes a CSV's quote character; by default it is sniffed with the
    delimiter. A file whose cells may start with an apostrophe (one that keeps a
    spreadsheet from reading the cell as a formula) passes the double quote.

    Raises TabularParseError on unparseable input.
    """
    if not content:
        raise TabularParseError("File is empty")

    fmt = _detect_format(content, filename)
    if fmt == "xlsx":
        return _parse_xlsx(content, max_rows)
    return _parse_csv(content, max_rows, quotechar)


class TabularFileParser:
    """``TabularParser`` Protocol implementation backed by ``parse_tabular``."""

    def parse(
        self,
        content: bytes,
        filename: str = "",
        max_rows: int | None = None,
        *,
        quotechar: str | None = None,
    ) -> ParsedTable:
        return parse_tabular(content, filename, max_rows=max_rows, quotechar=quotechar)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _parse_csv(
    content: bytes, max_rows: int | None = None, quotechar: str | None = None
) -> ParsedTable:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")

    if not text.strip():
        raise TabularParseError("CSV file is empty")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # type: ignore[assignment]

    quoting = {} if quotechar is None else {"quotechar": quotechar, "doublequote": True}
    reader = csv.reader(io.StringIO(text), dialect, **quoting)
    first = next(reader, None)
    if first is None:
        raise TabularParseError("CSV has no rows")

    headers = [(h or "").strip() for h in first]
    if not any(headers):
        raise TabularParseError("CSV has no header row")

    rows: list[dict[str, str]] = []
    for raw in reader:
        if not any((c or "").strip() for c in raw):
            continue
        row = {
            headers[i]: (raw[i].strip() if i < len(raw) and raw[i] is not None else "")
            for i in range(len(headers))
        }
        rows.append(row)
        if max_rows is not None and len(rows) > max_rows:
            break

    return ParsedTable(headers=headers, rows=rows, source_format="csv")


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def _parse_xlsx(content: bytes, max_rows: int | None = None) -> ParsedTable:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dep is declared
        raise TabularParseError("openpyxl is required to parse xlsx") from exc

    try:
        wb = load_workbook(filename=io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise TabularParseError(f"Cannot read xlsx: {exc}") from exc

    try:
        ws = wb.active
        if ws is None:
            raise TabularParseError("xlsx has no active sheet")

        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration as exc:
            raise TabularParseError("xlsx has no header row") from exc

        headers = [_cell_to_str(c).strip() for c in header_row]
        # Trim trailing empty header columns
        while headers and not headers[-1]:
            headers.pop()
        if not headers:
            raise TabularParseError("xlsx has no header row")

        rows: list[dict[str, str]] = []
        for raw in rows_iter:
            cells = [_cell_to_str(c) for c in raw]
            if not any(c.strip() for c in cells):
                continue
            row = {
                headers[i]: (cells[i].strip() if i < len(cells) else "")
                for i in range(len(headers))
            }
            rows.append(row)
            if max_rows is not None and len(rows) > max_rows:
                break
    finally:
        wb.close()

    return ParsedTable(headers=headers, rows=rows, source_format="xlsx")


def _cell_to_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value) if abs(value) < 1e-4 or abs(value) >= 1e16 else f"{value}"
    return str(value)
