"""A published protocol's readout may be renamed, restructured or removed while unused."""

import uuid

import pytest

from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    CurveType,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition, ReadoutUsage
from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.domain.shared.hit_criterion import HitCriterion

UNUSED = ReadoutUsage()
USED = ReadoutUsage(reasons=("has values in 3 runs", "used by a column of 2 campaigns"))


def _rd(name: str, **kwargs) -> ReadoutDefinition:
    kwargs.setdefault("data_type", ReadoutDataType.NUMERIC)
    return ReadoutDefinition(protocol_id=uuid.uuid4(), name=name, **kwargs)


def _published(*readouts: ReadoutDefinition) -> Protocol:
    protocol = Protocol.create(
        workspace_id=uuid.uuid4(),
        name="Kinase inhibition",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=list(readouts),
    )
    protocol.publish()
    return protocol


class TestReadoutUsage:
    def test_no_reasons_means_unused(self) -> None:
        assert not UNUSED.in_use
        assert USED.in_use


class TestUnusedReadoutOnPublishedProtocol:
    def test_can_be_removed(self) -> None:
        raw, typo = _rd("Raw"), _rd("Rwa")
        protocol = _published(raw, typo)
        protocol.remove_readout_definition(typo.id, UNUSED)
        assert [rd.name for rd in protocol.readout_definitions] == ["Raw"]

    def test_can_be_renamed(self) -> None:
        raw, typo = _rd("Raw"), _rd("Rwa")
        protocol = _published(raw, typo)
        protocol.update_readout_definition(typo.id, name="Ratio", usage=UNUSED)
        assert protocol.readout_definitions[1].name == "Ratio"

    def test_can_be_structurally_changed(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        protocol.update_readout_definition(
            other.id,
            data_type=ReadoutDataType.TEXT,
            aggregation=ReadoutAggregation.MEAN,
            usage=UNUSED,
        )
        changed = protocol.readout_definitions[1]
        assert changed.data_type == ReadoutDataType.TEXT
        assert changed.aggregation == ReadoutAggregation.MEAN

    def test_last_readout_still_cannot_be_removed(self) -> None:
        raw = _rd("Raw")
        protocol = _published(raw)
        with pytest.raises(ValidationError, match="at least one"):
            protocol.remove_readout_definition(raw.id, UNUSED)


class TestUsedReadoutOnPublishedProtocol:
    def test_remove_is_refused_with_the_reasons(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        with pytest.raises(ConflictError) as exc:
            protocol.remove_readout_definition(other.id, USED)
        message = str(exc.value)
        assert "create a new version" in message
        assert "has values in 3 runs; used by a column of 2 campaigns" in message
        assert len(protocol.readout_definitions) == 2

    def test_rename_is_refused_with_the_reasons(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        with pytest.raises(ConflictError) as exc:
            protocol.update_readout_definition(other.id, name="Renamed", usage=USED)
        message = str(exc.value)
        assert "create a new version" in message
        assert "has values in 3 runs; used by a column of 2 campaigns" in message
        assert protocol.readout_definitions[1].name == "Signal"

    def test_structural_change_is_refused(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        with pytest.raises(ConflictError, match="aggregation"):
            protocol.update_readout_definition(
                other.id, aggregation=ReadoutAggregation.MEAN, usage=USED
            )

    def test_cosmetic_edit_is_still_allowed(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        protocol.update_readout_definition(other.id, precision=2, usage=USED)
        assert protocol.readout_definitions[1].precision == 2

    def test_without_a_usage_answer_the_readout_counts_as_used(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        with pytest.raises(ConflictError):
            protocol.remove_readout_definition(other.id)
        with pytest.raises(ConflictError, match="create a new version"):
            protocol.update_readout_definition(other.id, name="Renamed")


class TestReferencesInsideTheProtocol:
    """In use with no stored values: the aggregate sees these itself."""

    def _refused(self, protocol: Protocol, rd: ReadoutDefinition, reason: str) -> None:
        assert reason in protocol.readout_usage(rd.id).reasons
        with pytest.raises(ConflictError, match="create a new version") as exc:
            protocol.remove_readout_definition(rd.id, UNUSED)
        assert reason in str(exc.value)
        with pytest.raises(ConflictError, match="create a new version") as exc:
            protocol.update_readout_definition(rd.id, name="Renamed", usage=UNUSED)
        assert reason in str(exc.value)

    def test_named_by_another_readouts_formula(self) -> None:
        raw = _rd("Raw")
        ratio = _rd("Ratio", is_calculated=True, calculation_formula="Raw / 2")
        self._refused(_published(raw, ratio), raw, "named by the formula of 'Ratio'")

    def test_named_in_brackets_by_another_readouts_formula(self) -> None:
        raw = _rd("Raw AU")
        ratio = _rd("Ratio", is_calculated=True, calculation_formula="[ Raw AU ] / 2")
        self._refused(_published(raw, ratio), raw, "named by the formula of 'Ratio'")

    def test_a_longer_or_foreign_name_in_a_formula_does_not_count(self) -> None:
        raw, raw2 = _rd("Raw"), _rd("Raw2")
        ratio = _rd(
            "Ratio", is_calculated=True, calculation_formula="Raw2 / @PRT-00001.Raw + [Raw 3]"
        )
        protocol = _published(raw, raw2, ratio)
        assert not protocol.readout_usage(raw.id).in_use
        assert protocol.readout_usage(raw2.id).in_use

    def test_its_own_formula_does_not_count(self) -> None:
        raw = _rd("Raw")
        ratio = _rd("Ratio", is_calculated=True, calculation_formula="Raw / 2")
        protocol = _published(raw, ratio)
        assert not protocol.readout_usage(ratio.id).in_use
        protocol.remove_readout_definition(ratio.id, UNUSED)

    def test_axis_of_a_dose_response_readout(self) -> None:
        dose, response = _rd("Dose"), _rd("Response")
        ic50 = _rd(
            "IC50",
            data_type=ReadoutDataType.DOSE_RESPONSE,
            dose_response_config=DoseResponseConfig(
                curve_type=CurveType.IC50, x_readout_name="Dose", y_readout_name="Response"
            ),
        )
        protocol = _published(dose, response, ic50)
        self._refused(protocol, dose, "an axis of the dose-response readout 'IC50'")
        self._refused(protocol, response, "an axis of the dose-response readout 'IC50'")
        assert not protocol.readout_usage(ic50.id).in_use

    def test_named_by_the_recommended_hit_rule(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        protocol.set_recommended_hit_criteria([HitCriterion("Signal", "gt", 50.0)])
        self._refused(protocol, other, "named by the protocol's recommended hit rule")
        assert not protocol.readout_usage(raw.id).in_use

    def test_stored_reasons_come_after_the_protocols_own(self) -> None:
        raw = _rd("Raw")
        ratio = _rd("Ratio", is_calculated=True, calculation_formula="Raw / 2")
        usage = _published(raw, ratio).readout_usage(raw.id, USED)
        assert usage.reasons == ("named by the formula of 'Ratio'", *USED.reasons)


class TestOtherStatesAreUnchanged:
    def test_locked_refuses_even_an_unused_readout(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        protocol.lock(locked_by=uuid.uuid4(), reason="review")
        with pytest.raises(ConflictError, match="locked"):
            protocol.remove_readout_definition(other.id, UNUSED)
        with pytest.raises(ConflictError, match="locked"):
            protocol.update_readout_definition(other.id, name="Renamed", usage=UNUSED)

    def test_retired_refuses_even_an_unused_readout(self) -> None:
        raw, other = _rd("Raw"), _rd("Signal")
        protocol = _published(raw, other)
        protocol.retire()
        with pytest.raises(ConflictError, match="only DRAFT"):
            protocol.remove_readout_definition(other.id, UNUSED)
        with pytest.raises(ConflictError, match="retired"):
            protocol.update_readout_definition(other.id, name="Renamed", usage=UNUSED)

    def test_draft_needs_no_usage_and_ignores_it(self) -> None:
        raw = _rd("Raw")
        ratio = _rd("Ratio", is_calculated=True, calculation_formula="Raw / 2")
        other = _rd("Signal")
        protocol = Protocol.create(
            workspace_id=uuid.uuid4(),
            name="Draft",
            protocol_type=ProtocolType.BIOCHEMICAL,
            created_by=uuid.uuid4(),
            readout_definitions=[raw, ratio, other],
        )
        protocol.update_readout_definition(other.id, name="Renamed", usage=USED)
        protocol.remove_readout_definition(other.id, USED)
        protocol.remove_readout_definition(raw.id)  # a draft may break its own formulas, as before
        assert [rd.name for rd in protocol.readout_definitions] == ["Ratio"]
