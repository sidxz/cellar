"""Tests for CDD protocol mapper — pure functions, no I/O."""

import pytest

from chem_vault.application.cdd_import.mapper import (
    CddProtocolMappingResult,
    CddProtocolSummary,
    MappedReadout,
    MappingWarning,
    map_cdd_protocol,
    map_cdd_protocol_list,
)
from chem_vault.domain.screening_assay.enums import (
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

    def test_batch_link_readout(self):
        proto = _protocol_json(readouts=[_readout("Batch", "Batch Link")])
        result = map_cdd_protocol(proto)
        assert result.readouts[0].data_type == ReadoutDataType.BATCH_LINK

    def test_file_readout(self):
        proto = _protocol_json(readouts=[_readout("Attachment", "File")])
        result = map_cdd_protocol(proto)
        assert result.readouts[0].data_type == ReadoutDataType.FILE

    def test_date_readout(self):
        proto = _protocol_json(readouts=[_readout("Exp Date", "Date")])
        result = map_cdd_protocol(proto)
        assert result.readouts[0].data_type == ReadoutDataType.DATE

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
        assert rd.normalization == ReadoutNormalization.NONE

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
        # 2 user-defined Number readouts + 1 synthesized DOSE_RESPONSE
        names = [r.name for r in result.readouts]
        assert names == ["Concentration", "% Inhibition", "IC50calc"]
        assert len(result.readouts) == 3

        dr = result.readouts[2]
        assert dr.data_type == ReadoutDataType.DOSE_RESPONSE
        assert dr.unit == "uM"
        assert dr.dose_response_config is not None
        assert dr.dose_response_config.x_readout_name == "Concentration"
        assert dr.dose_response_config.y_readout_name == "% Inhibition"

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
