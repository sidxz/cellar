"""Tests for the shared tabular file parser (csv + xlsx)."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from chem_vault.infrastructure.parsers.tabular_file import (
    ParsedTable,
    TabularParseError,
    parse_tabular,
)


def _xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestCSV:
    def test_basic_comma_csv(self) -> None:
        content = b"Well,Value\nA1,2.3\nA2,5.1\n"
        table = parse_tabular(content, "x.csv")
        assert table.source_format == "csv"
        assert table.headers == ["Well", "Value"]
        assert table.row_count == 2
        assert table.rows[0] == {"Well": "A1", "Value": "2.3"}

    def test_utf8_bom_is_stripped(self) -> None:
        content = "\ufeffWell,Value\nA1,2.3\n".encode("utf-8")
        table = parse_tabular(content, "x.csv")
        assert table.headers == ["Well", "Value"]
        assert table.rows[0]["Well"] == "A1"

    def test_semicolon_delimiter(self) -> None:
        content = b"Well;Value\nA1;2.3\nA2;5.1\n"
        table = parse_tabular(content, "x.csv")
        assert table.headers == ["Well", "Value"]
        assert table.row_count == 2

    def test_tab_delimiter(self) -> None:
        content = b"Well\tValue\nA1\t2.3\n"
        table = parse_tabular(content, "x.csv")
        assert table.headers == ["Well", "Value"]
        assert table.rows[0]["Value"] == "2.3"

    def test_blank_rows_are_skipped(self) -> None:
        content = b"Well,Value\nA1,2.3\n,\nA2,5.1\n"
        table = parse_tabular(content, "x.csv")
        assert table.row_count == 2

    def test_empty_file_raises(self) -> None:
        with pytest.raises(TabularParseError):
            parse_tabular(b"", "x.csv")

    def test_whitespace_only_csv_raises(self) -> None:
        with pytest.raises(TabularParseError):
            parse_tabular(b"   \n  \n", "x.csv")

    def test_short_row_pads_missing_columns(self) -> None:
        content = b"A,B,C\n1,2\n"
        table = parse_tabular(content, "x.csv")
        assert table.rows[0] == {"A": "1", "B": "2", "C": ""}


class TestXLSX:
    def test_basic_xlsx(self) -> None:
        content = _xlsx_bytes(
            ["Well", "Value", "Scientist"],
            [["A1", 2.3, "Dan"], ["A2", 5.1, "Dan"]],
        )
        table = parse_tabular(content, "x.xlsx")
        assert table.source_format == "xlsx"
        assert table.headers == ["Well", "Value", "Scientist"]
        assert table.row_count == 2
        assert table.rows[0]["Well"] == "A1"
        assert table.rows[0]["Value"] == "2.3"
        assert table.rows[1]["Scientist"] == "Dan"

    def test_xlsx_detected_by_magic_bytes(self) -> None:
        content = _xlsx_bytes(["A"], [["1"]])
        # No filename — must still detect via PK\x03\x04 zip signature.
        table = parse_tabular(content, "")
        assert table.source_format == "xlsx"

    def test_xlsx_integers_render_without_decimals(self) -> None:
        content = _xlsx_bytes(["N"], [[100], [3]])
        table = parse_tabular(content, "x.xlsx")
        assert table.rows[0]["N"] == "100"
        assert table.rows[1]["N"] == "3"

    def test_xlsx_blank_rows_skipped(self) -> None:
        content = _xlsx_bytes(
            ["Well", "Value"],
            [["A1", 2.3], [None, None], ["A2", 5.1]],
        )
        table = parse_tabular(content, "x.xlsx")
        assert table.row_count == 2

    def test_xlsx_trailing_empty_header_columns_trimmed(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.append(["Well", "Value", None, None])
        ws.append(["A1", 2.3, None, None])
        buf = io.BytesIO()
        wb.save(buf)
        table = parse_tabular(buf.getvalue(), "x.xlsx")
        assert table.headers == ["Well", "Value"]

    def test_malformed_xlsx_raises(self) -> None:
        # PK signature plus garbage — tries the xlsx code path.
        content = b"PK\x03\x04garbage data not actually a zip"
        with pytest.raises(TabularParseError):
            parse_tabular(content, "x.xlsx")

    def test_xlsx_extension_with_csv_content_falls_through_to_xlsx(self) -> None:
        # Pathological: .xlsx extension but CSV bytes. We attempt xlsx and fail.
        with pytest.raises(TabularParseError):
            parse_tabular(b"a,b\n1,2\n", "x.xlsx")
