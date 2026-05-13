"""Tests for the long-format run file normalizer."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.screening.long_format_normalizer import (
    ColumnMapping,
    NormalizedTable,
    ReadoutColumn,
    ReadoutDefRef,
    WellPosition,
    infer_mapping,
    normalize,
)
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.errors import ValidationError
from cellar.infrastructure.parsers.tabular_file import ParsedTable, parse_tabular


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
    def test_compound_ref_synonyms_recognized(self) -> None:
        # Compound name / synonym / external id all map to compound_ref,
        # not batch_ref. Reg number does too.
        for header in ("Compound", "Compound Name", "Synonym", "External ID", "Reg Number"):
            table = _make_table(
                ["Well", header, "Raw"],
                [{"Well": "A1", header: "MOL-A", "Raw": "0.5"}],
            )
            suggestion = infer_mapping(table)
            roles = {s.header: s.role for s in suggestion.suggestions}
            assert roles[header] == "compound_ref", header

    def test_compound_id_no_longer_maps_to_batch_ref(self) -> None:
        # Pre-resolver wiring, "Compound ID" was a batch_ref synonym;
        # it should now map to compound_ref instead.
        table = _make_table(
            ["Well", "Compound ID", "Raw"],
            [{"Well": "A1", "Compound ID": "MOL-A", "Raw": "0.5"}],
        )
        suggestion = infer_mapping(table)
        roles = {s.header: s.role for s in suggestion.suggestions}
        assert roles["Compound ID"] == "compound_ref"

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
        # "Scientist" is no longer a top-level role — it falls through to no
        # synonym match. The user maps it to a Text readout def in the wizard.
        assert roles["Scientist"][0] is None

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
# infer_mapping — readout-definition name match (Phase B follow-on)
# ---------------------------------------------------------------------------


class TestInferMappingReadoutDefMatch:
    """Headers whose normalized name equals a protocol-defined readout's
    name should be suggested as role=readout / confidence=high with the
    matching def id pre-bound — without the FE having to second-guess.
    """

    def _scientist_def(self) -> ReadoutDefRef:
        return ReadoutDefRef(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            name="Scientist",
            data_type="text",
        )

    def test_text_readout_def_name_match_yields_high_confidence_with_binding(
        self,
    ) -> None:
        table = _make_table(
            ["Well", "Scientist"],
            [{"Well": "A01", "Scientist": "Dan"}],
        )
        defs = [self._scientist_def()]
        s = infer_mapping(table, readout_defs=defs)

        sci = next(x for x in s.suggestions if x.header == "Scientist")
        assert sci.role == "readout"
        assert sci.confidence == "high"
        assert sci.readout_definition_id == defs[0].id
        assert "readout def" in sci.reason

    def test_match_is_case_and_punctuation_insensitive(self) -> None:
        table = _make_table(["Well", "raw au"], [{"Well": "A01", "raw au": "0.6"}])
        defs = [
            ReadoutDefRef(
                id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                name="Raw AU",
                data_type="numeric",
            )
        ]
        s = infer_mapping(table, readout_defs=defs)
        raw = next(x for x in s.suggestions if x.header == "raw au")
        assert raw.role == "readout"
        assert raw.readout_definition_id == defs[0].id

    def test_synonym_wins_over_readout_def_name_match(self) -> None:
        """A protocol that smuggled a reserved well-metadata name as a
        readout def shouldn't override the synonym dictionary — synonyms
        win, the user can manually re-bind if they really meant it."""
        table = _make_table(
            ["Well", "Concentration"],
            [{"Well": "A01", "Concentration": "100"}],
        )
        defs = [
            ReadoutDefRef(
                id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
                name="Concentration",  # name collides with the synonym
                data_type="numeric",
            )
        ]
        s = infer_mapping(table, readout_defs=defs)
        conc = next(x for x in s.suggestions if x.header == "Concentration")
        assert conc.role == "concentration"  # synonym precedence
        assert conc.readout_definition_id is None

    def test_dose_response_def_is_not_eligible_for_binding(self) -> None:
        """Dose-response readouts are computed/derived; mapping a column
        to one would be nonsensical. They must be excluded from the
        match catalog regardless of name."""
        table = _make_table(["Well", "IC50"], [{"Well": "A01", "IC50": ""}])
        defs = [
            ReadoutDefRef(
                id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
                name="IC50",
                data_type="dose_response",
            )
        ]
        s = infer_mapping(table, readout_defs=defs)
        ic50 = next(x for x in s.suggestions if x.header == "IC50")
        assert ic50.readout_definition_id is None

    def test_pick_list_def_is_not_eligible_for_binding(self) -> None:
        table = _make_table(["Well", "Status"], [{"Well": "A01", "Status": "ok"}])
        defs = [
            ReadoutDefRef(
                id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
                name="Status",
                data_type="pick_list",
            )
        ]
        s = infer_mapping(table, readout_defs=defs)
        status = next(x for x in s.suggestions if x.header == "Status")
        assert status.readout_definition_id is None

    def test_no_readout_defs_passed_preserves_legacy_behavior(self) -> None:
        """Back-compat: pre-Phase-B callers don't pass readout_defs;
        suggestions must look identical to before."""
        table = _make_table(["Well", "Scientist"], [{"Well": "A01", "Scientist": "Dan"}])
        s = infer_mapping(table)  # default readout_defs=()
        sci = next(x for x in s.suggestions if x.header == "Scientist")
        assert sci.readout_definition_id is None
        # "Scientist" has no synonym hit, no readout-def hit, falls through
        # to value-based which can't classify text → role=None.
        assert sci.role is None

    def test_no_match_when_protocol_lacks_def(self) -> None:
        table = _make_table(["Well", "Scientist"], [{"Well": "A01", "Scientist": "Dan"}])
        defs = [
            ReadoutDefRef(
                id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
                name="raw AU",
                data_type="numeric",
            )
        ]
        s = infer_mapping(table, readout_defs=defs)
        sci = next(x for x in s.suggestions if x.header == "Scientist")
        assert sci.readout_definition_id is None
        assert sci.role is None


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

    def test_compound_ref_propagated_to_row(self) -> None:
        rd_id = uuid.uuid4()
        table = _make_table(
            ["Well", "Compound", "Batch", "Raw"],
            [
                {"Well": "A1", "Compound": "MOL-A", "Batch": "", "Raw": "0.5"},
                {"Well": "A2", "Compound": "", "Batch": "CV-1", "Raw": "0.4"},
            ],
        )
        mapping = ColumnMapping(
            well="Well",
            batch_ref="Batch",
            compound_ref="Compound",
            readout_columns=(ReadoutColumn(header="Raw", readout_definition_id=rd_id),),
        )
        rows = normalize(table, mapping).unwrap().rows
        assert rows[0].compound_ref == "MOL-A"
        assert rows[0].batch_ref is None
        assert rows[1].compound_ref is None
        assert rows[1].batch_ref == "CV-1"

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


class TestNormalizeTextReadouts:
    def test_text_readout_keeps_string_values(self) -> None:
        rd_id = uuid.uuid4()
        table = _make_table(
            ["Well", "Scientist"],
            [
                {"Well": "A1", "Scientist": "Dan Selle"},
                {"Well": "A2", "Scientist": " "},  # whitespace → dropped
                {"Well": "A3", "Scientist": ""},
            ],
        )
        mapping = ColumnMapping(
            well="Well",
            readout_columns=(
                ReadoutColumn(
                    header="Scientist",
                    readout_definition_id=rd_id,
                    data_type="text",
                ),
            ),
        )
        out = normalize(table, mapping).unwrap()
        readouts = [r.readouts.get(rd_id) for r in out.rows]
        assert readouts[0] == "Dan Selle"
        assert readouts[1] is None
        assert readouts[2] is None

    def test_numeric_default_drops_text_cells(self) -> None:
        rd_id = uuid.uuid4()
        table = _make_table(
            ["Well", "Raw"],
            [
                {"Well": "A1", "Raw": "0.5"},
                {"Well": "A2", "Raw": "not a number"},
            ],
        )
        mapping = ColumnMapping(
            well="Well",
            readout_columns=(
                ReadoutColumn(header="Raw", readout_definition_id=rd_id),
            ),
        )
        out = normalize(table, mapping).unwrap()
        assert out.rows[0].readouts[rd_id] == 0.5
        assert rd_id not in out.rows[1].readouts


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

    def test_infer_mapping_finds_core_roles(self, fixture_table: ParsedTable) -> None:
        s = infer_mapping(fixture_table)
        roles_present = {x.role for x in s.suggestions if x.role is not None}
        assert {"plate_name", "well", "concentration", "batch_ref", "readout"} <= roles_present

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
