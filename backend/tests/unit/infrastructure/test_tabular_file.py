"""Tests for the shared tabular file parser (csv + xlsx)."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from cellar.infrastructure.parsers.tabular_file import (
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

    def test_leading_apostrophes_are_text_not_quotes(self) -> None:
        """A spreadsheet-safe file puts ' before = + - @; quoting is always the double
        quote, so those cells keep their columns."""
        content = b"Position,Label,Note\n'+P1,'=a,'@n\n'+P2,'=b,'@m\n"
        table = parse_tabular(content, "x.csv")
        assert table.rows == [
            {"Position": "'+P1", "Label": "'=a", "Note": "'@n"},
            {"Position": "'+P2", "Label": "'=b", "Note": "'@m"},
        ]

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


class TestMaxRows:
    """``max_rows`` stops the read one row past the limit, so a caller can refuse a long
    file without the parser building every row."""

    def test_csv_stops_one_row_past_the_limit(self) -> None:
        content = ("Well\n" + "\n".join(f"A{n}" for n in range(1000))).encode()
        table = parse_tabular(content, "x.csv", max_rows=3)
        assert [r["Well"] for r in table.rows] == ["A0", "A1", "A2", "A3"]

    def test_csv_blank_rows_do_not_count(self) -> None:
        table = parse_tabular(b"Well\nA1\n\n\nA2\nA3\n", "x.csv", max_rows=2)
        assert table.row_count == 3

    def test_xlsx_stops_one_row_past_the_limit(self) -> None:
        content = _xlsx_bytes(["Well"], [[f"A{n}"] for n in range(1000)])
        table = parse_tabular(content, "x.xlsx", max_rows=3)
        assert [r["Well"] for r in table.rows] == ["A0", "A1", "A2", "A3"]

    def test_no_limit_by_default(self) -> None:
        content = ("Well\n" + "\n".join(f"A{n}" for n in range(1000))).encode()
        assert parse_tabular(content, "x.csv").row_count == 1000


def test_openpyxl_reads_uploads_through_defusedxml() -> None:
    import openpyxl.xml

    assert openpyxl.xml.DEFUSEDXML
