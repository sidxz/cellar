"""A dose-response curve always names readouts it can fit: create and publish refuse a broken
curve, edits refuse to break one, and drafts carry curves along when their readouts change."""

import uuid

import pytest

from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    CurveType,
    ProtocolStatus,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import ConflictError, ValidationError

INH = ReadoutNormalization.PERCENT_INHIBITION
Z = ReadoutNormalization.Z_SCORE


def _numeric(name: str, *layers: ReadoutNormalization) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name=name,
        data_type=ReadoutDataType.NUMERIC,
        normalizations=frozenset(layers),
    )


def _curve(name: str = "IC50", y: str = "Signal", **cfg) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name=name,
        data_type=ReadoutDataType.DOSE_RESPONSE,
        unit="µM",
        dose_response_config=DoseResponseConfig(
            curve_type=CurveType.IC50, y_readout_name=y, **cfg
        ),
    )


def _create(*readouts: ReadoutDefinition) -> Protocol:
    return Protocol.create(
        workspace_id=uuid.uuid4(),
        name="DfrA inhibition",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=list(readouts),
    )


def _stored(*readouts: ReadoutDefinition, status=ProtocolStatus.ACTIVE) -> Protocol:
    """A protocol as loaded from the database: no create-time checks."""
    return Protocol(
        workspace_id=uuid.uuid4(),
        name="DfrA inhibition",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        status=status,
        readout_definitions=list(readouts),
    )


def _cfg(protocol: Protocol, name: str = "IC50") -> DoseResponseConfig:
    rd = next(r for r in protocol.readout_definitions if r.name == name)
    assert rd.dose_response_config is not None
    return rd.dose_response_config


class TestCreateRefusesBrokenCurves:
    def test_accepts_a_curve_on_a_numeric_readout(self) -> None:
        protocol = _create(_numeric("Signal", INH), _curve())
        assert _cfg(protocol).y_readout_name == "Signal"

    def test_refuses_a_y_readout_that_does_not_exist(self) -> None:
        with pytest.raises(ValidationError, match="'IC50' fits 'Signal'"):
            _create(_numeric("THF Fluorescence Slope", INH), _curve())

    def test_refuses_a_y_readout_that_is_not_numeric(self) -> None:
        text = ReadoutDefinition(
            protocol_id=uuid.uuid4(), name="Signal", data_type=ReadoutDataType.TEXT
        )
        with pytest.raises(ValidationError, match="which is not a numeric readout"):
            _create(text, _curve())

    def test_refuses_an_x_readout_that_does_not_exist(self) -> None:
        with pytest.raises(ValidationError, match="'IC50' uses 'Conc'"):
            _create(_numeric("Signal", INH), _curve(x_readout_name="Conc"))

    def test_refuses_a_layer_the_y_readout_does_not_calculate(self) -> None:
        with pytest.raises(
            ValidationError, match="'IC50' fits the z_score layer, which 'Signal' does not"
        ):
            _create(_numeric("Signal", INH), _curve(y_normalization=Z))

    def test_refuses_an_unset_layer_over_two_layers(self) -> None:
        with pytest.raises(
            ValidationError, match=r"'IC50'.*'Signal'.*\(percent_inhibition, z_score\)"
        ):
            _create(_numeric("Signal", INH, Z), _curve())

    def test_accepts_a_chosen_layer_over_two_layers(self) -> None:
        protocol = _create(_numeric("Signal", INH, Z), _curve(y_normalization=Z))
        assert _cfg(protocol).y_normalization == Z


class TestPublish:
    def test_refuses_a_broken_curve_carried_into_a_draft(self) -> None:
        draft = _stored(_numeric("Slope", INH), _curve(), status=ProtocolStatus.DRAFT)
        with pytest.raises(ValidationError, match="'IC50' fits 'Signal'"):
            draft.publish()
        assert draft.status == ProtocolStatus.DRAFT


class TestStoredBrokenProtocol:
    def test_still_loads(self) -> None:
        protocol = _stored(_numeric("Slope", INH), _curve())
        assert _cfg(protocol).y_readout_name == "Signal"

    def test_an_unrelated_readout_can_still_be_added(self) -> None:
        protocol = _stored(_numeric("Slope", INH), _curve(), status=ProtocolStatus.DRAFT)
        protocol.add_readout_definition(_numeric("Hill"))
        assert [r.name for r in protocol.readout_definitions][-1] == "Hill"

    def test_fixing_the_curve_is_allowed(self) -> None:
        curve = _curve()
        protocol = _stored(_numeric("Slope", INH), curve, status=ProtocolStatus.DRAFT)
        protocol.update_readout_definition(
            curve.id,
            dose_response_config=DoseResponseConfig(
                curve_type=CurveType.IC50, y_readout_name="Slope"
            ),
        )
        assert _cfg(protocol).y_readout_name == "Slope"


class TestEditsRefuseToBreakACurve:
    def test_adding_a_broken_curve_is_refused(self) -> None:
        protocol = _create(_numeric("Signal", INH), _curve())
        with pytest.raises(ValidationError, match="'IC90' fits 'Missing'"):
            protocol.add_readout_definition(_curve("IC90", y="Missing"))

    def test_dropping_the_fitted_layer_is_refused(self) -> None:
        signal = _numeric("Signal", INH, Z)
        protocol = _create(signal, _curve(y_normalization=Z))
        with pytest.raises(ValidationError, match="'IC50' fits the z_score layer"):
            protocol.update_readout_definition(signal.id, normalizations=frozenset({INH}))

    def test_removing_the_y_readout_on_a_draft_is_refused(self) -> None:
        signal = _numeric("Signal", INH)
        protocol = _create(signal, _curve(), _numeric("Other"))
        with pytest.raises(ConflictError, match=r"'Signal'.*'IC50'"):
            protocol.remove_readout_definition(signal.id)


class TestDraftCarriesCurvesAlong:
    def test_renaming_the_y_readout_renames_the_curve_y(self) -> None:
        signal = _numeric("Signal", INH)
        protocol = _create(signal, _curve())
        protocol.update_readout_definition(signal.id, name="THF Fluorescence Slope")
        assert _cfg(protocol).y_readout_name == "THF Fluorescence Slope"

    def test_renaming_the_x_readout_renames_the_curve_x(self) -> None:
        conc = _numeric("Conc")
        protocol = _create(_numeric("Signal", INH), conc, _curve(x_readout_name="Conc"))
        protocol.update_readout_definition(conc.id, name="Inhibitor level")
        assert _cfg(protocol).x_readout_name == "Inhibitor level"

    def test_adding_a_second_layer_pins_the_layer_the_curve_was_fitting(self) -> None:
        signal = _numeric("Signal", INH)
        protocol = _create(signal, _curve())
        protocol.update_readout_definition(signal.id, normalizations=frozenset({INH, Z}))
        assert _cfg(protocol).y_normalization == INH
