"""Tests for Protocol extensions: dose_response readout type, pick_list values, control layouts."""

import uuid

import pytest

from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.enums import (
    CurveType,
    PlateFormat,
    ProtocolType,
    ReadoutDataType,
)
from chem_vault.domain.screening_assay.protocol import (
    Protocol,
    ReadoutDefinition,
)
from chem_vault.domain.shared.errors import ConflictError, ValidationError
from chem_vault.domain.shared.ontology import OntologyTerm


_PLACEHOLDER_ID = uuid.UUID(int=0)


def _make_readout(name: str = "IC50", **kwargs) -> ReadoutDefinition:
    defaults = dict(
        protocol_id=_PLACEHOLDER_ID,
        name=name,
        data_type=ReadoutDataType.NUMERIC,
    )
    defaults.update(kwargs)
    return ReadoutDefinition(**defaults)


def _make_protocol(workspace_id=None, user_id=None, **kwargs):
    ws = workspace_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    defaults = dict(
        workspace_id=ws,
        name="Test Protocol",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uid,
        readout_definitions=[_make_readout()],
    )
    defaults.update(kwargs)
    return Protocol.create(**defaults)


# ---------------------------------------------------------------------------
# ReadoutDefinition — pick_list type
# ---------------------------------------------------------------------------


class TestReadoutDefinitionPickList:
    def test_pick_list_with_values(self):
        rd = ReadoutDefinition(
            protocol_id=_PLACEHOLDER_ID,
            name="Result",
            data_type=ReadoutDataType.PICK_LIST,
            pick_list_values=["Active", "Inactive"],
        )
        assert rd.pick_list_values == ["Active", "Inactive"]

    def test_pick_list_without_values_raises(self):
        with pytest.raises(ValidationError, match="pick_list_values"):
            ReadoutDefinition(
                protocol_id=_PLACEHOLDER_ID,
                name="Result",
                data_type=ReadoutDataType.PICK_LIST,
            )

    def test_pick_list_values_on_non_pick_list_raises(self):
        with pytest.raises(ValidationError, match="pick_list_values can only"):
            ReadoutDefinition(
                protocol_id=_PLACEHOLDER_ID,
                name="Signal",
                data_type=ReadoutDataType.NUMERIC,
                pick_list_values=["A", "B"],
            )


# ---------------------------------------------------------------------------
# ReadoutDefinition — dose_response type
# ---------------------------------------------------------------------------


class TestReadoutDefinitionDoseResponse:
    def test_dose_response_with_config(self):
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="concentration",
            y_readout_name="% inhibition",
        )
        rd = ReadoutDefinition(
            protocol_id=_PLACEHOLDER_ID,
            name="IC50",
            data_type=ReadoutDataType.DOSE_RESPONSE,
            unit="uM",
            dose_response_config=cfg,
        )
        assert rd.dose_response_config is not None
        assert rd.dose_response_config.curve_type == CurveType.IC50

    def test_dose_response_without_config_raises(self):
        with pytest.raises(ValidationError, match="dose_response_config"):
            ReadoutDefinition(
                protocol_id=_PLACEHOLDER_ID,
                name="IC50",
                data_type=ReadoutDataType.DOSE_RESPONSE,
            )

    def test_dose_response_config_on_non_dose_response_raises(self):
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="conc",
            y_readout_name="response",
        )
        with pytest.raises(ValidationError, match="dose_response_config can only"):
            ReadoutDefinition(
                protocol_id=_PLACEHOLDER_ID,
                name="Signal",
                data_type=ReadoutDataType.NUMERIC,
                dose_response_config=cfg,
            )


# ---------------------------------------------------------------------------
# ReadoutDefinition — batch_link type
# ---------------------------------------------------------------------------


class TestReadoutDefinitionBatchLink:
    def test_batch_link_creates_successfully(self):
        rd = ReadoutDefinition(
            protocol_id=_PLACEHOLDER_ID,
            name="Batch",
            data_type=ReadoutDataType.BATCH_LINK,
        )
        assert rd.data_type == ReadoutDataType.BATCH_LINK


# ---------------------------------------------------------------------------
# Protocol — cross-readout validation for dose_response
# ---------------------------------------------------------------------------


class TestProtocolDoseResponseCrossValidation:
    def test_add_dose_response_with_valid_axis_readouts(self):
        protocol = _make_protocol(
            readout_definitions=[
                _make_readout("concentration"),
                _make_readout("% inhibition"),
            ]
        )
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="concentration",
            y_readout_name="% inhibition",
        )
        dr_readout = ReadoutDefinition(
            protocol_id=protocol.id,
            name="IC50",
            data_type=ReadoutDataType.DOSE_RESPONSE,
            unit="uM",
            dose_response_config=cfg,
        )
        protocol.add_readout_definition(dr_readout)
        assert len(protocol.readout_definitions) == 3

    def test_add_dose_response_with_missing_x_axis_raises(self):
        protocol = _make_protocol(
            readout_definitions=[_make_readout("% inhibition")]
        )
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="concentration",
            y_readout_name="% inhibition",
        )
        dr_readout = ReadoutDefinition(
            protocol_id=protocol.id,
            name="IC50",
            data_type=ReadoutDataType.DOSE_RESPONSE,
            dose_response_config=cfg,
        )
        with pytest.raises(ValidationError, match="X-axis.*concentration"):
            protocol.add_readout_definition(dr_readout)

    def test_add_dose_response_with_missing_y_axis_raises(self):
        protocol = _make_protocol(
            readout_definitions=[_make_readout("concentration")]
        )
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="concentration",
            y_readout_name="% inhibition",
        )
        dr_readout = ReadoutDefinition(
            protocol_id=protocol.id,
            name="IC50",
            data_type=ReadoutDataType.DOSE_RESPONSE,
            dose_response_config=cfg,
        )
        with pytest.raises(ValidationError, match="Y-axis.*% inhibition"):
            protocol.add_readout_definition(dr_readout)


# ---------------------------------------------------------------------------
# Protocol — control layouts
# ---------------------------------------------------------------------------


class TestProtocolControlLayouts:
    def test_set_control_layout(self):
        protocol = _make_protocol()
        tpl_id = uuid.uuid4()
        protocol.set_control_layout(PlateFormat.F96, tpl_id)
        assert protocol.control_layouts["96"] == tpl_id

    def test_set_multiple_layouts(self):
        protocol = _make_protocol()
        tpl_96 = uuid.uuid4()
        tpl_384 = uuid.uuid4()
        protocol.set_control_layout(PlateFormat.F96, tpl_96)
        protocol.set_control_layout(PlateFormat.F384, tpl_384)
        assert len(protocol.control_layouts) == 2
        assert protocol.control_layouts["96"] == tpl_96
        assert protocol.control_layouts["384"] == tpl_384

    def test_overwrite_layout(self):
        protocol = _make_protocol()
        tpl1 = uuid.uuid4()
        tpl2 = uuid.uuid4()
        protocol.set_control_layout(PlateFormat.F96, tpl1)
        protocol.set_control_layout(PlateFormat.F96, tpl2)
        assert protocol.control_layouts["96"] == tpl2

    def test_remove_control_layout(self):
        protocol = _make_protocol()
        tpl_id = uuid.uuid4()
        protocol.set_control_layout(PlateFormat.F96, tpl_id)
        protocol.remove_control_layout(PlateFormat.F96)
        assert "96" not in protocol.control_layouts

    def test_remove_nonexistent_layout_is_noop(self):
        protocol = _make_protocol()
        protocol.remove_control_layout(PlateFormat.F96)  # no error

    def test_set_layout_on_active_protocol_raises(self):
        protocol = _make_protocol()
        protocol.publish()
        with pytest.raises(ConflictError, match="DRAFT"):
            protocol.set_control_layout(PlateFormat.F96, uuid.uuid4())

    def test_remove_layout_on_active_protocol_raises(self):
        protocol = _make_protocol()
        protocol.set_control_layout(PlateFormat.F96, uuid.uuid4())
        protocol.publish()
        with pytest.raises(ConflictError, match="DRAFT"):
            protocol.remove_control_layout(PlateFormat.F96)


# ---------------------------------------------------------------------------
# Protocol — versioning clones new fields
# ---------------------------------------------------------------------------


class TestProtocolVersioningNewFields:
    def test_versioning_clones_pick_list_values(self):
        from chem_vault.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )

        protocol = _make_protocol(
            readout_definitions=[
                ReadoutDefinition(
                    protocol_id=_PLACEHOLDER_ID,
                    name="Result",
                    data_type=ReadoutDataType.PICK_LIST,
                    pick_list_values=["Active", "Inactive"],
                ),
            ]
        )
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        assert new_protocol.readout_definitions[0].pick_list_values == ["Active", "Inactive"]
        # Verify it's a copy, not shared reference
        assert new_protocol.readout_definitions[0].pick_list_values is not protocol.readout_definitions[0].pick_list_values

    def test_versioning_clones_dose_response_config(self):
        from chem_vault.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )

        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="conc",
            y_readout_name="response",
        )
        protocol = _make_protocol(
            readout_definitions=[
                _make_readout("conc"),
                _make_readout("response"),
                ReadoutDefinition(
                    protocol_id=_PLACEHOLDER_ID,
                    name="IC50",
                    data_type=ReadoutDataType.DOSE_RESPONSE,
                    dose_response_config=cfg,
                ),
            ]
        )
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        ic50_def = next(rd for rd in new_protocol.readout_definitions if rd.name == "IC50")
        assert ic50_def.dose_response_config is not None
        assert ic50_def.dose_response_config.curve_type == CurveType.IC50

    def test_versioning_clones_control_layouts(self):
        from chem_vault.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )

        tpl_id = uuid.uuid4()
        protocol = _make_protocol()
        protocol.set_control_layout(PlateFormat.F96, tpl_id)
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        assert new_protocol.control_layouts["96"] == tpl_id
        # Verify it's a copy
        assert new_protocol.control_layouts is not protocol.control_layouts


# ---------------------------------------------------------------------------
# Protocol — ontology annotations
# ---------------------------------------------------------------------------


class TestProtocolOntologyAnnotations:
    def test_set_ontology_annotation(self):
        protocol = _make_protocol()
        terms = [
            OntologyTerm(term_id="BAO:0000142", label="biosensor method", ontology_source="BAO"),
        ]
        protocol.set_ontology_annotation("bioassay_type", terms)
        assert "bioassay_type" in protocol.ontology_annotations
        assert len(protocol.ontology_annotations["bioassay_type"]) == 1
        assert protocol.ontology_annotations["bioassay_type"][0].term_id == "BAO:0000142"

    def test_set_ontology_annotation_strips_slot_name(self):
        protocol = _make_protocol()
        terms = [
            OntologyTerm(term_id="BAO:0000142", label="biosensor method", ontology_source="BAO"),
        ]
        protocol.set_ontology_annotation("  bioassay_type  ", terms)
        assert "bioassay_type" in protocol.ontology_annotations

    def test_set_ontology_annotation_empty_slot_raises(self):
        protocol = _make_protocol()
        with pytest.raises(ValidationError, match="slot name must not be empty"):
            protocol.set_ontology_annotation("", [])

    def test_set_ontology_annotation_whitespace_slot_raises(self):
        protocol = _make_protocol()
        with pytest.raises(ValidationError, match="slot name must not be empty"):
            protocol.set_ontology_annotation("   ", [])

    def test_set_ontology_annotation_on_active_raises(self):
        protocol = _make_protocol()
        protocol.publish()
        with pytest.raises(ConflictError, match="DRAFT"):
            protocol.set_ontology_annotation("bioassay_type", [])

    def test_remove_ontology_annotation(self):
        protocol = _make_protocol()
        terms = [
            OntologyTerm(term_id="BAO:0000142", label="biosensor method", ontology_source="BAO"),
        ]
        protocol.set_ontology_annotation("bioassay_type", terms)
        protocol.remove_ontology_annotation("bioassay_type")
        assert "bioassay_type" not in protocol.ontology_annotations

    def test_remove_nonexistent_annotation_is_noop(self):
        protocol = _make_protocol()
        protocol.remove_ontology_annotation("nonexistent")  # no error

    def test_remove_ontology_annotation_on_active_raises(self):
        protocol = _make_protocol()
        protocol.set_ontology_annotation("bioassay_type", [])
        protocol.publish()
        with pytest.raises(ConflictError, match="DRAFT"):
            protocol.remove_ontology_annotation("bioassay_type")

    def test_default_ontology_annotations_empty(self):
        protocol = _make_protocol()
        assert protocol.ontology_annotations == {}

    def test_overwrite_annotation(self):
        protocol = _make_protocol()
        terms1 = [
            OntologyTerm(term_id="BAO:001", label="method A", ontology_source="BAO"),
        ]
        terms2 = [
            OntologyTerm(term_id="BAO:002", label="method B", ontology_source="BAO"),
        ]
        protocol.set_ontology_annotation("bioassay_type", terms1)
        protocol.set_ontology_annotation("bioassay_type", terms2)
        assert len(protocol.ontology_annotations["bioassay_type"]) == 1
        assert protocol.ontology_annotations["bioassay_type"][0].term_id == "BAO:002"


# ---------------------------------------------------------------------------
# Protocol — versioning clones ontology annotations
# ---------------------------------------------------------------------------


class TestProtocolVersioningOntologyAnnotations:
    def test_versioning_clones_ontology_annotations(self):
        from chem_vault.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )

        protocol = _make_protocol()
        terms = [
            OntologyTerm(term_id="BAO:0000142", label="biosensor method", ontology_source="BAO"),
        ]
        protocol.set_ontology_annotation("bioassay_type", terms)
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        assert "bioassay_type" in new_protocol.ontology_annotations
        assert new_protocol.ontology_annotations["bioassay_type"][0].term_id == "BAO:0000142"
        # Verify it's a deep copy
        assert new_protocol.ontology_annotations is not protocol.ontology_annotations
        assert new_protocol.ontology_annotations["bioassay_type"] is not protocol.ontology_annotations["bioassay_type"]

    def test_versioning_empty_annotations(self):
        from chem_vault.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )

        protocol = _make_protocol()
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        assert new_protocol.ontology_annotations == {}
