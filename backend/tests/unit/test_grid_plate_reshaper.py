"""Unit tests for the plate-reader grid reshaper."""

import csv
import io

import pytest
from openpyxl import Workbook

from cellar.application.shared.grid_plate_reshaper import reshape_grid_to_well_value_csv
from cellar.domain.shared.errors import ValidationError


def _parse(csv_bytes: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))


class TestReshape:
    def test_basic_grid(self):
        grid = "\n".join([",1,2,3", "A,2.3,5.1,1.9", "B,4.2,6.3,2.1"]).encode()
        out = _parse(reshape_grid_to_well_value_csv(grid, "plate.csv"))
        assert out[0] == ["Well", "Value"]
        rows = {r[0]: r[1] for r in out[1:]}
        assert rows["A1"] == "2.3"
        assert rows["A3"] == "1.9"
        assert rows["B2"] == "6.3"
        assert len(out) - 1 == 6  # 2 rows x 3 cols

    def test_skips_title_rows(self):
        grid = "\n".join(
            ["Plate 1 raw luminescence", "Exported 2024", ",1,2", "A,10,20", "B,30,40"]
        ).encode()
        rows = {r[0]: r[1] for r in _parse(reshape_grid_to_well_value_csv(grid, "x.csv"))[1:]}
        assert rows == {"A1": "10", "A2": "20", "B1": "30", "B2": "40"}

    def test_skips_empty_cells(self):
        grid = "\n".join([",1,2,3", "A,10,,30", "B,,,"]).encode()
        rows = {r[0]: r[1] for r in _parse(reshape_grid_to_well_value_csv(grid, "x.csv"))[1:]}
        assert rows == {"A1": "10", "A3": "30"}

    def test_384_addressing(self):
        header = "," + ",".join(str(i) for i in range(1, 25))
        row_a = "A," + ",".join(str(i) for i in range(1, 25))
        row_p = "P," + ",".join(str(100 + i) for i in range(1, 25))
        grid = "\n".join([header, row_a, row_p]).encode()
        rows = {r[0]: r[1] for r in _parse(reshape_grid_to_well_value_csv(grid, "x.csv"))[1:]}
        assert rows["A24"] == "24"
        assert rows["P1"] == "101"
        assert rows["P24"] == "124"

    def test_xlsx_grid(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["", 1, 2, 3])
        ws.append(["A", 2.3, 5.1, 1.9])
        ws.append(["B", 4.2, 6.3, 2.1])
        buf = io.BytesIO()
        wb.save(buf)
        rows = {
            r[0]: r[1]
            for r in _parse(reshape_grid_to_well_value_csv(buf.getvalue(), "plate.xlsx"))[1:]
        }
        assert rows["A1"] == "2.3"
        assert rows["B3"] == "2.1"

    def test_long_format_is_not_a_grid(self):
        not_grid = b"Well,Value\nA1,2.3\nA2,5.1\n"
        with pytest.raises(ValidationError, match="plate grid"):
            reshape_grid_to_well_value_csv(not_grid, "x.csv")

    def test_empty_grid_raises(self):
        grid = b",1,2\nA,,\nB,,\n"
        with pytest.raises(ValidationError, match="no readable values"):
            reshape_grid_to_well_value_csv(grid, "x.csv")
