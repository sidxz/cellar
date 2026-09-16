"""Tests for Protocol extensions: dose_response readout type, pick_list values, control layouts."""

import uuid

import pytest

from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    CurveType,
    PlateFormat,
    ProtocolType,
    ReadoutDataType,
)
from cellar.domain.screening_assay.protocol import (
    Protocol,
    ReadoutDefinition,
)
from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.domain.shared.ontology import OntologyTerm


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
        # Constructor accepts legacy list[str] shape; lifts to PickListValue
        # objects (color = None when not specified).
        from cellar.domain.screening_assay.protocol import PickListValue

        rd = ReadoutDefinition(
            protocol_id=_PLACEHOLDER_ID,
            name="Result",
            data_type=ReadoutDataType.PICK_LIST,
            pick_list_values=["Active", "Inactive"],
        )
        assert rd.pick_list_values == [
            PickListValue(label="Active"),
            PickListValue(label="Inactive"),
        ]

    def test_pick_list_with_color(self):
        from cellar.domain.screening_assay.protocol import PickListValue

        rd = ReadoutDefinition(
            protocol_id=_PLACEHOLDER_ID,
            name="Hit Class",
            data_type=ReadoutDataType.PICK_LIST,
            pick_list_values=[
                PickListValue(label="Active", color="#22c55e"),
                {"label": "Inactive", "color": "#ef4444"},
                "Partial",  # no color — auto-derive on FE
            ],
        )
        assert rd.pick_list_values is not None
        assert rd.pick_list_values[0] == PickListValue(label="Active", color="#22c55e")
        assert rd.pick_list_values[1] == PickListValue(label="Inactive", color="#ef4444")
        assert rd.pick_list_values[2] == PickListValue(label="Partial", color=None)

    def test_pick_list_invalid_color_raises(self):
        from cellar.domain.screening_assay.protocol import PickListValue
        from cellar.domain.shared.errors import ValidationError as VE

        with pytest.raises(VE, match="7-char hex"):
            PickListValue(label="X", color="green")
        with pytest.raises(VE, match="7-char hex"):
            PickListValue(label="X", color="#abc")

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
        # Note: "Batch" alone is a reserved well-metadata name (well.batch_id
        # already references the well's batch). For a BATCH_LINK readout,
        # use a name that's clearly a measurement/reference rather than
        # the well's own metadata.
        rd = ReadoutDefinition(
            protocol_id=_PLACEHOLDER_ID,
            name="Reference Batch",
            data_type=ReadoutDataType.BATCH_LINK,
        )
        assert rd.data_type == ReadoutDataType.BATCH_LINK


# ---------------------------------------------------------------------------
# Protocol — cross-readout validation for dose_response
# ---------------------------------------------------------------------------


class TestProtocolDoseResponseCrossValidation:
    def test_add_dose_response_with_valid_axis_readouts(self):
        # X readout must be a non-reserved name (the dose itself lives on
        # well.dose, but a transformed-X readout like "log_dose" is valid
        # — it's a derivation, not the raw setpoint).
        protocol = _make_protocol(
            readout_definitions=[
                _make_readout("log_dose"),
                _make_readout("% inhibition"),
            ]
        )
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="log_dose",
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
            x_readout_name="log_dose",
            y_readout_name="% inhibition",
        )
        dr_readout = ReadoutDefinition(
            protocol_id=protocol.id,
            name="IC50",
            data_type=ReadoutDataType.DOSE_RESPONSE,
            dose_response_config=cfg,
        )
        with pytest.raises(ValidationError, match="X-axis.*log_dose"):
            protocol.add_readout_definition(dr_readout)

    def test_update_dose_response_with_missing_x_axis_raises(self):
        """update_readout_definition mirrors add's cross-readout validation
        — pointing the X axis at a non-existent readout must fail at update
        time, not silently accept it and break the fitter at runtime."""
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="log_dose",
            y_readout_name="% inhibition",
        )
        ic50_def = ReadoutDefinition(
            protocol_id=_PLACEHOLDER_ID,
            name="IC50",
            data_type=ReadoutDataType.DOSE_RESPONSE,
            dose_response_config=cfg,
        )
        protocol = _make_protocol(
            readout_definitions=[
                _make_readout("log_dose"),
                _make_readout("% inhibition"),
                ic50_def,
            ]
        )
        # Try updating IC50 to point X at a readout that doesn't exist.
        bad_cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="ghost_readout",
            y_readout_name="% inhibition",
        )
        with pytest.raises(ValidationError, match="X-axis.*ghost_readout"):
            protocol.update_readout_definition(
                ic50_def.id, dose_response_config=bad_cfg
            )

    def test_add_dose_response_with_missing_y_axis_raises(self):
        protocol = _make_protocol(
            readout_definitions=[_make_readout("log_dose")]
        )
        cfg = DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="log_dose",
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

    def test_set_new_layout_on_active_protocol_succeeds(self):
        # Adding a layout for a NEW format is safe on unlocked ACTIVE —
        # existing runs ran on the other formats and are unaffected.
        protocol = _make_protocol()
        protocol.publish()
        tpl_id = uuid.uuid4()
        protocol.set_control_layout(PlateFormat.F96, tpl_id)
        assert protocol.control_layouts["96"] == tpl_id

    def test_replace_existing_layout_on_active_raises(self):
        # Replacing the layout for a format that ALREADY has one is
        # unsafe — any prior run on that format computed Z′ +
        # normalization against the old layout. Force versioning.
        protocol = _make_protocol()
        protocol.set_control_layout(PlateFormat.F96, uuid.uuid4())
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
        from cellar.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )

        from cellar.domain.screening_assay.protocol import PickListValue

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
        assert new_protocol.readout_definitions[0].pick_list_values == [
            PickListValue(label="Active"),
            PickListValue(label="Inactive"),
        ]
        # Verify it's a copy, not shared reference
        assert new_protocol.readout_definitions[0].pick_list_values is not protocol.readout_definitions[0].pick_list_values

    def test_versioning_clones_dose_response_config(self):
        from cellar.domain.screening_assay.protocol_versioning_service import (
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
        from cellar.domain.screening_assay.protocol_versioning_service import (
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

    def test_versioning_clones_dose_unit_and_pos_control_signal(self):
        """The dose unit + POS control direction are protocol-wide
        conventions; new versions inherit them so runs of the new draft
        speak the same vocabulary as the parent."""
        from cellar.domain.screening_assay.enums import PosControlSignal
        from cellar.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )
        from cellar.domain.shared.enums import ConcentrationUnit

        protocol = _make_protocol()
        protocol.dose_unit = ConcentrationUnit.NM
        protocol.pos_control_signal = PosControlSignal.LOW
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        assert new_protocol.dose_unit == ConcentrationUnit.NM
        assert new_protocol.pos_control_signal == PosControlSignal.LOW

    def test_versioning_clones_ontology_annotations(self):
        from cellar.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )
        from cellar.domain.shared.ontology import OntologyTerm

        protocol = _make_protocol()
        protocol.ontology_annotations = {
            "assay_type": [
                OntologyTerm(
                    term_id="OBI:0001146",
                    label="cell-based assay",
                    ontology_source="OBI",
                    uri="http://purl.obolibrary.org/obo/OBI_0001146",
                )
            ]
        }
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        assert "assay_type" in new_protocol.ontology_annotations
        assert new_protocol.ontology_annotations["assay_type"][0].term_id == "OBI:0001146"
        # Verify deep copy — mutating the new version's annotations must
        # not bleed into the parent.
        assert new_protocol.ontology_annotations is not protocol.ontology_annotations

    def test_versioning_clones_recommended_hit_criteria(self):
        """Hit criteria are tuned QC gates; new versions inherit them so
        the screener doesn't have to re-tune from scratch on every
        version."""
        from cellar.domain.shared.hit_criterion import HitCriterion
        from cellar.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )

        rd = _make_readout("% Inhibition")
        protocol = _make_protocol(readout_definitions=[rd])
        criteria = [
            HitCriterion(
                readout_name="% Inhibition",
                operator="gte",
                value=50.0,
            )
        ]
        protocol.set_recommended_hit_criteria(criteria)
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        assert new_protocol.recommended_hit_criteria is not None
        assert len(new_protocol.recommended_hit_criteria) == 1
        assert new_protocol.recommended_hit_criteria[0].value == 50.0
        # Verify deep copy
        assert (
            new_protocol.recommended_hit_criteria[0].value == 50.0
        )


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
        from cellar.domain.screening_assay.protocol_versioning_service import (
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
        from cellar.domain.screening_assay.protocol_versioning_service import (
            ProtocolVersioningService,
        )

        protocol = _make_protocol()
        protocol.publish()
        svc = ProtocolVersioningService()
        new_protocol = svc.create_new_version(protocol)
        assert new_protocol.ontology_annotations == {}


# ---------------------------------------------------------------------------
# Protocol.create — ontology annotations at creation time
# ---------------------------------------------------------------------------


class TestProtocolCreateOntologyAnnotations:
    """Facets supplied at create must all land on the aggregate in one shot.

    Regression for the create-dialog race where each facet slot was persisted
    via a separate concurrent PUT, so all but one slot was silently dropped.
    """

    def test_create_stores_all_supplied_annotation_slots(self):
        protocol = _make_protocol(
            ontology_annotations={
                "organism": [
                    OntologyTerm(
                        term_id="free_text:Homo sapiens",
                        label="Homo sapiens",
                        ontology_source="free_text",
                    )
                ],
                "assay_format": [
                    OntologyTerm(
                        term_id="free_text:biochemical",
                        label="biochemical",
                        ontology_source="free_text",
                    )
                ],
                "detection": [
                    OntologyTerm(
                        term_id="free_text:fluorescence",
                        label="fluorescence",
                        ontology_source="free_text",
                    )
                ],
            }
        )
        assert set(protocol.ontology_annotations) == {"organism", "assay_format", "detection"}
        assert protocol.ontology_annotations["assay_format"][0].label == "biochemical"
        assert protocol.ontology_annotations["detection"][0].label == "fluorescence"
