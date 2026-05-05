"""Tests for the long-format run file normalizer."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from chem_vault.application.screening.long_format_normalizer import (
    ColumnMapping,
    NormalizedTable,
    ReadoutColumn,
    WellPosition,
    infer_mapping,
    normalize,
)
from chem_vault.domain.shared.enums import PlateFormat
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.infrastructure.parsers.tabular_file import ParsedTable, parse_tabular


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_table(headers: list[str], rows: list[dict[str, str]]) -> ParsedTable:
    return ParsedTable(headers=headers, rows=rows, source_format="csv")


_NADD_FIXTURE = "/Users/sidx/Downloads/NadD_LG-2200467564_100uM-DR_4.20.26.xlsx"


# ---------------------------------------------------------------------------
# infer_mapping — synonym matching
# ---------------------------------------------------------------------------


class TestInferMappingSynonyms:
    def test_nadd_headers_resolved_via_synonyms(self) -> None:
        table = _make_table(
            ["Plate Name", "Well", "Concentration", "LGCY BATCH NAME", "Raw Data", "Scientist"],
            [{"Plate Name": "P1", "Well": "A01", "Concentration": "100",
              "LGCY BATCH NAME": "LG-001", "Raw Data": "0.6", "Scientist": "Dan"}],
        )
        suggestion = infer_mapping(table)
        roles = {s.header: (s.role, s.confidence) for s in suggestion.suggestions}
        assert roles["Plate Name"] == ("plate_name", "high")
        assert roles["Well"] == ("well", "high")
        assert roles["Concentration"] == ("concentration", "high")
        assert roles["LGCY BATCH NAME"] == ("batch_ref", "high")
        assert roles["Raw Data"] == ("readout", "high")
        assert roles["Scientist"] == ("scientist", "high")

    def test_synonyms_are_case_and_space_insensitive(self) -> None:
        table = _make_table(["plate_name", "WELL", "% Inhibition"], [])
        s = infer_mapping(table)
        roles = {x.header: x.role for x in s.suggestions}
        assert roles["plate_name"] == "plate_name"
        assert roles["WELL"] == "well"
        assert roles["% Inhibition"] == "readout"

    def test_multiple_readout_columns_all_match(self) -> None:
        table = _make_table(["Well", "Absorbance", "Fluorescence"], [])
        s = infer_mapping(table)
        readouts = [x.header for x in s.by_role("readout")]
        assert set(readouts) == {"Absorbance", "Fluorescence"}


# ---------------------------------------------------------------------------
# infer_mapping — value-based fallback
# ---------------------------------------------------------------------------


class TestInferMappingValueFallback:
    def test_unknown_header_with_well_values_inferred_as_well(self) -> None:
        table = _make_table(
            ["xyz", "v"],
            [{"xyz": f"A{i:02d}", "v": "1"} for i in range(1, 13)],
        )
        s = infer_mapping(table)
        roles = {x.header: (x.role, x.confidence) for x in s.suggestions}
        assert roles["xyz"][0] == "well"
        assert roles["xyz"][1] == "medium"

    def test_unknown_numeric_with_high_uniqueness_inferred_as_readout(self) -> None:
        # Header "metric" is not a synonym; values are mostly unique numbers.
        rows = [{"Well": f"A{i:02d}", "metric": str(0.123 + i * 0.0017)} for i in range(1, 50)]
        table = _make_table(["Well", "metric"], rows)
        s = infer_mapping(table)
        roles = {x.header: x.role for x in s.suggestions}
        assert roles["metric"] == "readout"


# ---------------------------------------------------------------------------
# normalize — well coordinate handling
# ---------------------------------------------------------------------------


class TestNormalizeWellCoords:
    def test_a01_and_a1_both_canonicalize(self) -> None:
        rd_id = uuid.uuid4()
        table = _make_table(
            ["Well", "Raw"],
            [{"Well": "A01", "Raw": "1.0"}, {"Well": "A1", "Raw": "2.0"}],
        )
        mapping = ColumnMapping(
            well="Well",
            readout_columns=(ReadoutColumn(header="Raw", readout_definition_id=rd_id),),
        )
        out = normalize(table, mapping).unwrap()
        wells = [r.well for r in out.rows]
        assert wells[0] == WellPosition(row="A", column=1)
        assert wells[1] == WellPosition(row="A", column=1)

    def test_invalid_well_strings_are_skipped(self) -> None:
        rd_id = uuid.uuid4()
        table = _make_table(
            ["Well", "Raw"],
            [
                {"Well": "A1", "Raw": "1.0"},
                {"Well": "garbage", "Raw": "2.0"},
                {"Well": "", "Raw": "3.0"},
            ],
        )
        mapping = ColumnMapping(
            well="Well",
            readout_columns=(ReadoutColumn(header="Raw", readout_definition_id=rd_id),),
        )
        out = normalize(table, mapping).unwrap()
        assert len(out.rows) == 1
        assert out.skipped_rows == 2


# ---------------------------------------------------------------------------
# normalize — plate-format inference
# ---------------------------------------------------------------------------


class TestNormalizePlateFormat:
    def _table(self, wells: list[str]) -> ParsedTable:
        return _make_table(
            ["Well", "Raw"], [{"Well": w, "Raw": "1.0"} for w in wells]
        )

    def _mapping(self, rd_id: uuid.UUID) -> ColumnMapping:
        return ColumnMapping(
            well="Well",
            readout_columns=(ReadoutColumn(header="Raw", readout_definition_id=rd_id),),
        )

    def test_96_well_plate_inferred(self) -> None:
        rd_id = uuid.uuid4()
        out = normalize(self._table(["A1", "H12"]), self._mapping(rd_id)).unwrap()
        assert out.plate_formats == {"Plate-1": PlateFormat.F96}

    def test_384_well_plate_inferred(self) -> None:
        rd_id = uuid.uuid4()
        out = normalize(self._table(["A1", "P24"]), self._mapping(rd_id)).unwrap()
        assert out.plate_formats == {"Plate-1": PlateFormat.F384}

    def test_1536_well_plate_inferred(self) -> None:
        rd_id = uuid.uuid4()
        out = normalize(
            self._table(["A1", "AF48"]), self._mapping(rd_id)
        ).unwrap()
        assert out.plate_formats == {"Plate-1": PlateFormat.F1536}


# ---------------------------------------------------------------------------
# normalize — control inference + multi-plate
# ---------------------------------------------------------------------------


class TestNormalizeBlankDetection:
    def test_no_batch_no_concentration_yields_blank_row(self) -> None:
        rd_id = uuid.uuid4()
        table = _make_table(
            ["Well", "Conc", "Batch", "Raw"],
            [{"Well": "A1", "Conc": "", "Batch": "", "Raw": "0.5"}],
        )
        mapping = ColumnMapping(
            well="Well",
            concentration="Conc",
            batch_ref="Batch",
            readout_columns=(ReadoutColumn(header="Raw", readout_definition_id=rd_id),),
        )
        row = normalize(table, mapping).unwrap().rows[0]
        assert row.batch_ref is None
        assert row.concentration is None

    def test_with_batch_is_sample_row(self) -> None:
        rd_id = uuid.uuid4()
        table = _make_table(
            ["Well", "Conc", "Batch", "Raw"],
            [{"Well": "A1", "Conc": "100", "Batch": "LG-001", "Raw": "0.5"}],
        )
        mapping = ColumnMapping(
            well="Well",
            concentration="Conc",
            batch_ref="Batch",
            readout_columns=(ReadoutColumn(header="Raw", readout_definition_id=rd_id),),
        )
        row = normalize(table, mapping).unwrap().rows[0]
        assert row.batch_ref == "LG-001"
        assert row.concentration == 100.0


class TestNormalizeMultiPlate:
    def test_two_plates_grouped_separately(self) -> None:
        rd_id = uuid.uuid4()
        table = _make_table(
            ["Plate", "Well", "Raw"],
            [
                {"Plate": "P1", "Well": "A1", "Raw": "1"},
                {"Plate": "P1", "Well": "B2", "Raw": "2"},
                {"Plate": "P2", "Well": "A1", "Raw": "3"},
            ],
        )
        mapping = ColumnMapping(
            well="Well",
            plate_name="Plate",
            readout_columns=(ReadoutColumn(header="Raw", readout_definition_id=rd_id),),
        )
        out = normalize(table, mapping).unwrap()
        plates = {r.plate_name for r in out.rows}
        assert plates == {"P1", "P2"}


# ---------------------------------------------------------------------------
# normalize — error paths
# ---------------------------------------------------------------------------


class TestNormalizeErrors:
    def test_missing_well_column_returns_failure(self) -> None:
        table = _make_table(["Plate", "Raw"], [{"Plate": "P1", "Raw": "1"}])
        result = normalize(table, ColumnMapping(well="Well"))
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    def test_no_valid_rows_returns_failure(self) -> None:
        table = _make_table(
            ["Well", "Raw"], [{"Well": "garbage", "Raw": "1"}]
        )
        rd_id = uuid.uuid4()
        mapping = ColumnMapping(
            well="Well",
            readout_columns=(ReadoutColumn(header="Raw", readout_definition_id=rd_id),),
        )
        result = normalize(table, mapping)
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# NadD fixture roundtrip
# ---------------------------------------------------------------------------


class TestNadDFixture:
    @pytest.fixture
    def fixture_table(self) -> ParsedTable:
        try:
            with open(_NADD_FIXTURE, "rb") as fh:
                return parse_tabular(fh.read(), _NADD_FIXTURE)
        except FileNotFoundError:
            pytest.skip(f"NadD fixture missing at {_NADD_FIXTURE}")

    def test_infer_mapping_finds_all_six_roles(self, fixture_table: ParsedTable) -> None:
        s = infer_mapping(fixture_table)
        roles_present = {x.role for x in s.suggestions if x.role is not None}
        assert {"plate_name", "well", "concentration", "batch_ref", "readout", "scientist"} <= roles_present

    def test_normalize_produces_two_plates(self, fixture_table: ParsedTable) -> None:
        s = infer_mapping(fixture_table)
        rd_id = uuid.uuid4()
        readout_header = s.first("readout")
        assert readout_header is not None
        mapping = ColumnMapping(
            well=s.first("well") or "Well",
            plate_name=s.first("plate_name"),
            concentration=s.first("concentration"),
            batch_ref=s.first("batch_ref"),
            scientist=s.first("scientist"),
            readout_columns=(
                ReadoutColumn(header=readout_header, readout_definition_id=rd_id),
            ),
        )
        out: NormalizedTable = normalize(fixture_table, mapping).unwrap()
        assert len(out.plate_formats) == 2
        for fmt in out.plate_formats.values():
            assert fmt == PlateFormat.F384

    def test_normalize_separates_sample_and_blank_rows(
        self, fixture_table: ParsedTable
    ) -> None:
        s = infer_mapping(fixture_table)
        rd_id = uuid.uuid4()
        readout_header = s.first("readout")
        assert readout_header is not None
        mapping = ColumnMapping(
            well=s.first("well") or "Well",
            plate_name=s.first("plate_name"),
            concentration=s.first("concentration"),
            batch_ref=s.first("batch_ref"),
            readout_columns=(
                ReadoutColumn(header=readout_header, readout_definition_id=rd_id),
            ),
        )
        out = normalize(fixture_table, mapping).unwrap()
        sample_rows = [r for r in out.rows if r.batch_ref]
        blank_rows = [r for r in out.rows if not r.batch_ref]
        assert len(sample_rows) > 0
        assert len(blank_rows) > 0
