"""Tests for CDD protocol mapper — pure functions, no I/O."""

import pytest

from cellar.application.cdd_import.mapper import (
    CddProtocolMappingResult,
    CddProtocolSummary,
    MappedReadout,
    MappingWarning,
    map_cdd_protocol,
    map_cdd_protocol_list,
)
from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)


def _protocol_json(*, protocol_id=1, name="Kinase IC50", readouts=None):
    return {
        "id": protocol_id,
        "name": name,
        "class": "protocol",
        "readout_definitions": readouts or [],
    }


def _readout(name="% Inhibition", data_type="Number", unit_label="%", **kwargs):
    """Build a readout definition using actual CDD Vault API field names."""
    rd = {"name": name, "data_type": data_type, "unit_label": unit_label}
    rd.update(kwargs)
    return rd


def _condition(name="Cell Type", data_type="Text", **kwargs):
    """Build a condition (readout with protocol_condition=True)."""
    rd = {"name": name, "data_type": data_type, "protocol_condition": True}
    rd.update(kwargs)
    return rd


class TestMapCddProtocolList:
    def test_empty_list(self):
        assert map_cdd_protocol_list([]) == []

    def test_maps_id_name_count(self):
        protocols = [
            _protocol_json(protocol_id=1, name="P1", readouts=[_readout()]),
            _protocol_json(protocol_id=2, name="P2", readouts=[]),
        ]
        result = map_cdd_protocol_list(protocols)
        assert len(result) == 2
        assert result[0] == CddProtocolSummary(external_id=1, name="P1", readout_count=1)
        assert result[1] == CddProtocolSummary(external_id=2, name="P2", readout_count=0)


class TestMapCddProtocol:
    def test_numeric_readout(self):
        proto = _protocol_json(readouts=[_readout("IC50", "Number", "nM")])
        result = map_cdd_protocol(proto)
        assert len(result.readouts) == 1
        assert result.readouts[0].name == "IC50"
        assert result.readouts[0].data_type == ReadoutDataType.NUMERIC
        assert result.readouts[0].unit == "nM"
        assert result.warnings == []

    def test_text_readout(self):
        proto = _protocol_json(readouts=[_readout("Notes", "Text")])
        result = map_cdd_protocol(proto)
        assert result.readouts[0].data_type == ReadoutDataType.TEXT

    def test_pick_list_readout(self):
        proto = _protocol_json(
            readouts=[_readout("Status", "Pick List", pick_list_values=["Active", "Inactive"])]
        )
        result = map_cdd_protocol(proto)
        assert result.readouts[0].data_type == ReadoutDataType.PICK_LIST
        assert result.readouts[0].pick_list_values == ["Active", "Inactive"]

    def test_plot_becomes_dose_response(self):
        proto = _protocol_json(readouts=[_readout("DR Curve", "Plot")])
        result = map_cdd_protocol(proto)
        assert result.readouts[0].data_type == ReadoutDataType.DOSE_RESPONSE
        assert result.readouts[0].dose_response_config is not None

    def test_batch_link_dropped_with_warning(self):
        # CDD "Batch Link" doesn't fit cellar's model — well.batch_id
        # is canonical. Mapper drops it + emits an informative warning.
        proto = _protocol_json(readouts=[_readout("Reference Batch", "Batch Link")])
        result = map_cdd_protocol(proto)
        assert result.readouts == []
        assert any(
            w.field_name == "Reference Batch" and "Batch Link" in w.source_type
            for w in result.warnings
        )

    def test_file_dropped_with_warning(self):
        # File readouts not yet supported (Phase 3). Drop with a clear
        # message rather than importing a placeholder column nothing
        # populates.
        proto = _protocol_json(readouts=[_readout("Attachment", "File")])
        result = map_cdd_protocol(proto)
        assert result.readouts == []
        assert any(
            w.field_name == "Attachment" and "File" in w.source_type
            for w in result.warnings
        )

    def test_date_dropped_with_warning(self):
        # Date duplicates run.run_date in cellar's model. Drop.
        proto = _protocol_json(readouts=[_readout("Exp Date", "Date")])
        result = map_cdd_protocol(proto)
        assert result.readouts == []
        assert any(
            w.field_name == "Exp Date" and "Date" in w.source_type
            for w in result.warnings
        )

    def test_unknown_type_skipped_with_warning(self):
        proto = _protocol_json(
            readouts=[
                _readout("IC50", "Number", "nM"),
                _readout("Custom", "SomeWeirdType"),
            ]
        )
        result = map_cdd_protocol(proto)
        assert len(result.readouts) == 1
        assert len(result.warnings) == 1
        assert result.warnings[0].field_name == "Custom"
        assert "SomeWeirdType" in result.warnings[0].reason

    def test_display_order_sequential(self):
        proto = _protocol_json(
            readouts=[_readout("A", "Number"), _readout("B", "Text")]
        )
        result = map_cdd_protocol(proto)
        assert result.readouts[0].display_order == 0
        assert result.readouts[1].display_order == 1

    def test_conditions_mapped(self):
        proto = _protocol_json(
            readouts=[_readout(), _condition("Cell Type", "Text")],
        )
        result = map_cdd_protocol(proto)
        assert len(result.readouts) == 1  # condition not counted as readout
        assert len(result.conditions) == 1
        assert result.conditions[0].name == "Cell Type"
        assert result.conditions[0].data_type == ConditionDataType.TEXT

    def test_external_source_id_preserved(self):
        proto = _protocol_json(protocol_id=42)
        result = map_cdd_protocol(proto)
        assert result.external_source_id == 42

    def test_protocol_name_preserved(self):
        proto = _protocol_json(name="My Protocol")
        result = map_cdd_protocol(proto)
        assert result.name == "My Protocol"

    def test_empty_readouts(self):
        proto = _protocol_json(readouts=[])
        result = map_cdd_protocol(proto)
        assert result.readouts == []
        assert result.warnings == []

    def test_defaults_for_mapped_readout(self):
        proto = _protocol_json(readouts=[_readout()])
        result = map_cdd_protocol(proto)
        rd = result.readouts[0]
        assert rd.aggregation == ReadoutAggregation.NONE
        assert rd.normalizations == frozenset()

    def test_dose_response_calculation_mapped(self):
        """Dose-response calculations become DOSE_RESPONSE readouts with proper config."""
        proto = {
            "id": 1,
            "name": "DR Protocol",
            "readout_definitions": [
                {"id": 100, "name": "Concentration", "data_type": "Number", "unit_label": "uM"},
                {"id": 101, "name": "% Inhibition", "data_type": "Number", "unit_label": "%"},
                # All below are auto-generated calculation outputs:
                {"id": 102, "name": "IC50calc", "data_type": "Number", "unit_label": "uM"},
                {"id": 103, "name": "Hill slope", "data_type": "Number"},
                {"id": 104, "name": "R squared", "data_type": "Number"},
                {"id": 105, "name": "IC50calc CI (Lower)", "data_type": "Number", "unit_label": "uM"},
                {"id": 106, "name": "IC50calc CI (Upper)", "data_type": "Number", "unit_label": "uM"},
            ],
            "calculations": [
                {
                    "id": 1,
                    "class": "dose response calculation",
                    "inputs": {"response_readout_definition": 101, "dose_readout_definition": 100},
                    "outputs": {
                        "intercept_readout_definitions": [[102, {"confidence_interval_readout_definitions": [105, 106]}]],
                        "hill_slope_readout_definition": 103,
                        "r_squared_readout_definition": 104,
                    },
                }
            ],
        }
        result = map_cdd_protocol(proto)
        # "Concentration" is the dose column (reserved name + referenced as
        # the calculation's dose_readout_definition) — it's skipped, with a
        # warning. Result: 1 user-defined Number readout (% Inhibition) + 1
        # synthesized DOSE_RESPONSE.
        names = [r.name for r in result.readouts]
        assert names == ["% Inhibition", "IC50calc"]
        assert len(result.readouts) == 2

        # Skipped Concentration shows up in warnings.
        assert any(w.field_name == "Concentration" for w in result.warnings)

        dr = result.readouts[1]
        assert dr.data_type == ReadoutDataType.DOSE_RESPONSE
        assert dr.unit == "uM"
        assert dr.dose_response_config is not None
        # X axis is None — cellar sources X from well.dose, not from a
        # separate readout column.
        assert dr.dose_response_config.x_readout_name is None
        assert dr.dose_response_config.y_readout_name == "% Inhibition"

    def test_reserved_name_readout_is_skipped(self):
        """A CDD readout literally named "Concentration"/"Dose"/etc. is
        well metadata, not a measurement. The mapper drops it with a
        warning so it never becomes a cellar ReadoutDefinition."""
        proto = _protocol_json(
            readouts=[
                _readout("Concentration", "Number", "uM"),
                _readout("Raw AU", "Number", "AU"),
                _readout("Dose", "Number", "uM"),
                _readout("Batch", "Number"),
            ]
        )
        result = map_cdd_protocol(proto)
        names = [r.name for r in result.readouts]
        assert names == ["Raw AU"], (
            "Reserved well-metadata names must be skipped"
        )
        skipped = {w.field_name for w in result.warnings}
        assert skipped == {"Concentration", "Dose", "Batch"}
        for w in result.warnings:
            assert "dose/concentration column" in w.reason

    def test_x_readout_name_referenced_dose_column_is_skipped(self):
        """A non-reserved name (e.g. "Compound Conc") that's referenced as
        the X axis of a Plot readout is also a dose column and must be
        skipped + null'd out on the DR config."""
        proto = _protocol_json(
            readouts=[
                {
                    "id": 1,
                    "name": "Compound Conc",
                    "data_type": "Number",
                    "unit_label": "uM",
                },
                {"id": 2, "name": "%Control", "data_type": "Number", "unit_label": "%"},
                {
                    "id": 3,
                    "name": "IC50",
                    "data_type": "Plot",
                    "x_readout_name": "Compound Conc",
                    "y_readout_name": "%Control",
                },
            ]
        )
        result = map_cdd_protocol(proto)
        names = [r.name for r in result.readouts]
        assert "Compound Conc" not in names, (
            "Dose column referenced by a DR readout must be skipped"
        )
        assert names == ["%Control", "IC50"]

        dr = next(r for r in result.readouts if r.name == "IC50")
        assert dr.dose_response_config is not None
        assert dr.dose_response_config.x_readout_name is None, (
            "DR config's x_readout_name must be nulled when its source was a "
            "skipped dose column — fitter then reads X from well.dose"
        )
        assert dr.dose_response_config.y_readout_name == "%Control"
        assert any(w.field_name == "Compound Conc" for w in result.warnings)

    def test_percent_inhibition_calc_lifted_to_input_normalizations(self):
        """A `percent inhibition calculation` in CDD is just-another-column
        on their side, but conceptually it's a normalization formula on
        the input readout. The mapper must lift it onto the input
        readout's normalizations set so the imported protocol declares
        the same computed layer the source vault was producing."""
        proto = {
            "id": 1,
            "name": "Inh Protocol",
            "readout_definitions": [
                {"id": 100, "name": "Raw Data", "data_type": "Number"},
                # Output of the calc — this row is auto-skipped via
                # _collect_calculated_readout_ids.
                {
                    "id": 101,
                    "name": "Raw Data % inhibition",
                    "data_type": "Number",
                    "unit_label": "%",
                },
            ],
            "calculations": [
                {
                    "id": 1,
                    "class": "percent inhibition calculation",
                    "inputs": {"input_readout_definition": 100},
                    "outputs": {"output_readout_definition": 101},
                }
            ],
        }
        result = map_cdd_protocol(proto)
        names = [r.name for r in result.readouts]
        # Output readout is skipped — only Raw Data emerges.
        assert names == ["Raw Data"]
        rd = result.readouts[0]
        assert rd.normalizations == frozenset(
            {ReadoutNormalization.PERCENT_INHIBITION}
        ), (
            "percent inhibition calc must lift onto input readout "
            "normalizations set"
        )

    def test_multiple_calcs_on_same_input_combine_into_one_normalizations_set(self):
        """The NadD-Sumo HTS shape (CDD 73684): a single Raw Data readout
        feeds both percent-inhibition and z-score calculations. Both
        normalizations land on the same input readout."""
        proto = {
            "id": 1,
            "name": "Combo",
            "readout_definitions": [
                {"id": 100, "name": "Raw Data", "data_type": "Number"},
                {"id": 101, "name": "Raw Data % inhibition", "data_type": "Number"},
                {"id": 102, "name": "Raw Data z score", "data_type": "Number"},
            ],
            "calculations": [
                {
                    "id": 1,
                    "class": "percent inhibition calculation",
                    "inputs": {"input_readout_definition": 100},
                    "outputs": {"output_readout_definition": 101},
                },
                {
                    "id": 2,
                    "class": "z score calculation",
                    "inputs": {"input_readout_definition": 100},
                    "outputs": {"output_readout_definition": 102},
                },
            ],
        }
        result = map_cdd_protocol(proto)
        names = [r.name for r in result.readouts]
        assert names == ["Raw Data"]
        rd = result.readouts[0]
        assert rd.normalizations == frozenset(
            {ReadoutNormalization.PERCENT_INHIBITION, ReadoutNormalization.Z_SCORE}
        )

    def test_unmapped_calc_class_does_not_lift_normalization(self):
        """A calculation class cellar doesn't recognize must not
        produce a phantom normalization. Output readout is still skipped
        via the calculated_ids path, but the input stays bare-raw."""
        proto = {
            "id": 1,
            "name": "Unknown",
            "readout_definitions": [
                {"id": 100, "name": "Raw Data", "data_type": "Number"},
                {"id": 101, "name": "Some Output", "data_type": "Number"},
            ],
            "calculations": [
                {
                    "id": 1,
                    "class": "made up calculation",
                    "inputs": {"input_readout_definition": 100},
                    "outputs": {"output_readout_definition": 101},
                }
            ],
        }
        result = map_cdd_protocol(proto)
        rd = next(r for r in result.readouts if r.name == "Raw Data")
        assert rd.normalizations == frozenset(), (
            "Unknown calc class must not invent a normalization"
        )

    def test_description_and_category_from_protocol_fields(self):
        proto = {
            "id": 1,
            "name": "Test",
            "readout_definitions": [_readout()],
            "protocol_fields": {"Category": "In vivo", "Description": "A test protocol"},
        }
        result = map_cdd_protocol(proto)
        assert result.category == "In vivo"
        assert result.description == "A test protocol"
