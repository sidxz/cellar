"""Unit tests for ExportPlateLayout use case + CSV/XLSX renderers."""

import csv
import io
import uuid
from dataclasses import dataclass

from returns.result import Failure, Success

from cellar.application.inventory.export_plate_layout import (
    ExportPlateLayout,
    ExportPlateLayoutQuery,
    PlateLayoutRow,
    render_csv,
    render_xlsx,
)
from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.well_assignment import WellAssignment
from cellar.domain.shared.enums import ConcentrationUnit, PlateFormat, WellType
from cellar.domain.shared.value_objects import Barcode, BatchNumber, Concentration
from tests.fakes.fake_auth import FakeAuth


class _FakeUow:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@dataclass
class _FakeBatch:
    id: uuid.UUID
    batch_number: BatchNumber


class _FakePlateRepo:
    def __init__(self, plate):
        self._plate = plate

    async def find_by_id_in_workspace(self, workspace_id, id):
        return self._plate if self._plate is not None and self._plate.id == id else None


class _FakeBatchRepo:
    def __init__(self, batches):
        self._batches = batches

    async def find_by_ids(self, workspace_id, ids):
        return [b for b in self._batches if b.id in ids]


def _plate(ws: uuid.UUID, batch_id: uuid.UUID) -> RegisteredPlate:
    p = RegisteredPlate.register(
        workspace_id=ws,
        barcode=Barcode(value="PLT-X"),
        plate_label="X",
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=uuid.uuid4(),
    )
    p.map_wells(
        {
            "A1": WellAssignment(
                well_type=WellType.SAMPLE,
                batch_id=batch_id,
                concentration=Concentration(value=10.0, unit=ConcentrationUnit.UM),
            ),
            "A2": WellAssignment(well_type=WellType.POSITIVE_CONTROL),
        }
    )
    return p


class TestExportUseCase:
    async def test_resolves_batch_number_and_builds_rows(self):
        ws = uuid.uuid4()
        batch_id = uuid.uuid4()
        plate = _plate(ws, batch_id)
        uc = ExportPlateLayout(
            _FakeUow(),
            _FakePlateRepo(plate),
            _FakeBatchRepo([_FakeBatch(id=batch_id, batch_number=BatchNumber(value="CC-000001-001"))]),
        )
        result = await uc(
            ExportPlateLayoutQuery(workspace_id=ws, plate_id=plate.id),
            auth=FakeAuth(role="viewer"),
        )
        assert isinstance(result, Success)
        rows = {r.well: r for r in result.unwrap().rows}
        # UUID resolved back to the human-readable batch number
        assert rows["A1"].batch_number == "CC-000001-001"
        assert rows["A1"].concentration_value == 10.0
        assert rows["A1"].concentration_unit == "uM"
        assert rows["A1"].well_type == "sample"
        # control well: no batch
        assert rows["A2"].batch_number == ""
        assert rows["A2"].well_type == "positive_control"

    async def test_not_found(self):
        ws = uuid.uuid4()
        uc = ExportPlateLayout(_FakeUow(), _FakePlateRepo(None), _FakeBatchRepo([]))
        result = await uc(
            ExportPlateLayoutQuery(workspace_id=ws, plate_id=uuid.uuid4()),
            auth=FakeAuth(role="viewer"),
        )
        assert isinstance(result, Failure)


class TestRenderers:
    @staticmethod
    def _rows():
        return [
            PlateLayoutRow("A1", "CC-000001-001", 10.0, "uM", "sample"),
            PlateLayoutRow("A2", "", None, None, "positive_control"),
        ]

    def test_csv_columns_match_import_template(self):
        out = render_csv(self._rows()).decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(out)))
        # Header is the exact order the well-mapping import reads.
        assert reader[0] == ["Well", "Batch Number", "Concentration", "Unit", "Role"]
        assert reader[1] == ["A1", "CC-000001-001", "10.0", "uM", "sample"]
        assert reader[2] == ["A2", "", "", "", "positive_control"]

    def test_xlsx_is_a_workbook(self):
        out = render_xlsx(self._rows())
        # XLSX files are zip archives — magic bytes "PK".
        assert out[:2] == b"PK"
        assert len(out) > 100
