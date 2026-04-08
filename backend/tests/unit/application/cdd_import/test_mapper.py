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


def _cdd_protocol_json(*, protocol_id=1, name="Kinase IC50", readouts=None):
    return {
        "id": protocol_id,
        "name": name,
        "class": "protocol",
        "readout_definitions": readouts or [],
    }


def _cdd_readout(name="% Inhibition", data_type="Number", unit_label="%", **kwargs):
    """Build a CDD readout definition using actual CDD API field names."""
    rd = {"name": name, "data_type": data_type, "unit_label": unit_label}
    rd.update(kwargs)
    return rd


def _cdd_condition(name="Cell Type", data_type="Text", **kwargs):
    """Build a CDD condition (readout with protocol_condition=True)."""
    rd = {"name": name, "data_type": data_type, "protocol_condition": True}
    rd.update(kwargs)
    return rd


class TestMapCddProtocolList:
    def test_empty_list(self):
        assert map_cdd_protocol_list([]) == []

    def test_maps_id_name_count(self):
        cdd = [
            _cdd_protocol_json(protocol_id=1, name="P1", readouts=[_cdd_readout()]),
            _cdd_protocol_json(protocol_id=2, name="P2", readouts=[]),
        ]
        result = map_cdd_protocol_list(cdd)
        assert len(result) == 2
        assert result[0] == CddProtocolSummary(cdd_id=1, name="P1", readout_count=1)
        assert result[1] == CddProtocolSummary(cdd_id=2, name="P2", readout_count=0)


class TestMapCddProtocol:
    def test_numeric_readout(self):
        cdd = _cdd_protocol_json(readouts=[_cdd_readout("IC50", "Number", "nM")])
        result = map_cdd_protocol(cdd)
        assert len(result.readouts) == 1
        assert result.readouts[0].name == "IC50"
        assert result.readouts[0].data_type == ReadoutDataType.NUMERIC
        assert result.readouts[0].unit == "nM"
        assert result.warnings == []

    def test_text_readout(self):
        cdd = _cdd_protocol_json(readouts=[_cdd_readout("Notes", "Text")])
        result = map_cdd_protocol(cdd)
        assert result.readouts[0].data_type == ReadoutDataType.TEXT

    def test_pick_list_readout(self):
        cdd = _cdd_protocol_json(
            readouts=[_cdd_readout("Status", "Pick List", pick_list_values=["Active", "Inactive"])]
        )
        result = map_cdd_protocol(cdd)
        assert result.readouts[0].data_type == ReadoutDataType.PICK_LIST
        assert result.readouts[0].pick_list_values == ["Active", "Inactive"]

    def test_plot_becomes_dose_response(self):
        cdd = _cdd_protocol_json(readouts=[_cdd_readout("DR Curve", "Plot")])
        result = map_cdd_protocol(cdd)
        assert result.readouts[0].data_type == ReadoutDataType.DOSE_RESPONSE
        assert result.readouts[0].dose_response_config is not None

    def test_batch_link_readout(self):
        cdd = _cdd_protocol_json(readouts=[_cdd_readout("Batch", "Batch Link")])
        result = map_cdd_protocol(cdd)
        assert result.readouts[0].data_type == ReadoutDataType.BATCH_LINK

    def test_file_readout(self):
        cdd = _cdd_protocol_json(readouts=[_cdd_readout("Attachment", "File")])
        result = map_cdd_protocol(cdd)
        assert result.readouts[0].data_type == ReadoutDataType.FILE

    def test_date_readout(self):
        cdd = _cdd_protocol_json(readouts=[_cdd_readout("Exp Date", "Date")])
        result = map_cdd_protocol(cdd)
        assert result.readouts[0].data_type == ReadoutDataType.DATE

    def test_unknown_type_skipped_with_warning(self):
        cdd = _cdd_protocol_json(
            readouts=[
                _cdd_readout("IC50", "Number", "nM"),
                _cdd_readout("Custom", "SomeWeirdType"),
            ]
        )
        result = map_cdd_protocol(cdd)
        assert len(result.readouts) == 1
        assert len(result.warnings) == 1
        assert result.warnings[0].field_name == "Custom"
        assert "SomeWeirdType" in result.warnings[0].reason

    def test_display_order_sequential(self):
        cdd = _cdd_protocol_json(
            readouts=[_cdd_readout("A", "Number"), _cdd_readout("B", "Text")]
        )
        result = map_cdd_protocol(cdd)
        assert result.readouts[0].display_order == 0
        assert result.readouts[1].display_order == 1

    def test_conditions_mapped(self):
        cdd = _cdd_protocol_json(
            readouts=[_cdd_readout(), _cdd_condition("Cell Type", "Text")],
        )
        result = map_cdd_protocol(cdd)
        assert len(result.readouts) == 1  # condition not counted as readout
        assert len(result.conditions) == 1
        assert result.conditions[0].name == "Cell Type"
        assert result.conditions[0].data_type == ConditionDataType.TEXT

    def test_cdd_source_id_preserved(self):
        cdd = _cdd_protocol_json(protocol_id=42)
        result = map_cdd_protocol(cdd)
        assert result.cdd_source_id == 42

    def test_protocol_name_preserved(self):
        cdd = _cdd_protocol_json(name="My Protocol")
        result = map_cdd_protocol(cdd)
        assert result.name == "My Protocol"

    def test_empty_readouts(self):
        cdd = _cdd_protocol_json(readouts=[])
        result = map_cdd_protocol(cdd)
        assert result.readouts == []
        assert result.warnings == []

    def test_defaults_for_mapped_readout(self):
        cdd = _cdd_protocol_json(readouts=[_cdd_readout()])
        result = map_cdd_protocol(cdd)
        rd = result.readouts[0]
        assert rd.aggregation == ReadoutAggregation.NONE
        assert rd.normalization == ReadoutNormalization.NONE
