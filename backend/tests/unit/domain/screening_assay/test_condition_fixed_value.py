"""A condition's fixed value: the protocol-level value that defines it (Hypoxia: yes, 72 h)."""

import uuid

import pytest

from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    ProtocolStatus,
    ProtocolType,
    ReadoutDataType,
)
from cellar.domain.screening_assay.events import ProtocolCorrected
from cellar.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from cellar.domain.screening_assay.protocol_versioning_service import ProtocolVersioningService
from cellar.domain.shared.errors import ConflictError, ValidationError

_PID = uuid.UUID(int=0)


def _cd(data_type=ConditionDataType.NUMERIC, fixed_value=None, **kw) -> ConditionDefinition:
    return ConditionDefinition(
        protocol_id=_PID,
        name=kw.pop("name", "Incubation time"),
        data_type=data_type,
        fixed_value=fixed_value,
        **kw,
    )


def _protocol(*conditions: ConditionDefinition) -> Protocol:
    return Protocol.create(
        workspace_id=uuid.uuid4(),
        name="p",
        protocol_type=ProtocolType.WHOLE_CELL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(protocol_id=_PID, name="MIC", data_type=ReadoutDataType.NUMERIC)
        ],
        condition_definitions=list(conditions),
    )


class TestValidation:
    def test_absent_by_default(self) -> None:
        assert _cd().fixed_value is None

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_is_none(self, raw: str) -> None:
        assert _cd(fixed_value=raw).fixed_value is None

    def test_numeric_keeps_the_trimmed_string(self) -> None:
        assert _cd(fixed_value=" 72 ", unit="h").fixed_value == "72"
        assert _cd(fixed_value="1e-3").fixed_value == "1e-3"

    @pytest.mark.parametrize("raw", ["72h", "abc", "nan", "inf"])
    def test_numeric_must_be_a_number(self, raw: str) -> None:
        with pytest.raises(ValidationError, match="number"):
            _cd(fixed_value=raw)

    def test_pick_list_value_must_be_one_of_the_values(self) -> None:
        cd = _cd(
            ConditionDataType.PICK_LIST, "yes", name="Hypoxia", pick_list_values=["yes", "no"]
        )
        assert cd.fixed_value == "yes"
        with pytest.raises(ValidationError, match="one of"):
            _cd(
                ConditionDataType.PICK_LIST,
                "maybe",
                name="Hypoxia",
                pick_list_values=["yes", "no"],
            )

    def test_text_takes_any_non_empty_string(self) -> None:
        assert _cd(ConditionDataType.TEXT, " HepG2 ", name="Cell line").fixed_value == "HepG2"

    def test_run_value_carries_the_unit(self) -> None:
        assert _cd(fixed_value="72", unit="h").fixed_run_value == "72 h"
        assert _cd(ConditionDataType.TEXT, "yes", name="Hypoxia").fixed_run_value == "yes"
        assert _cd().fixed_run_value is None


class TestMutability:
    def test_draft_update_sets_and_clears_freely(self) -> None:
        cd = _cd(unit="h")
        p = _protocol(cd)
        p.update_condition_definition(cd.id, fixed_value="72")
        assert p.condition_definitions[0].fixed_value == "72"
        p.update_condition_definition(cd.id, fixed_value=None)
        assert p.condition_definitions[0].fixed_value is None

    def test_draft_update_revalidates_against_a_new_type(self) -> None:
        cd = _cd(ConditionDataType.TEXT, "yes", name="Hypoxia")
        p = _protocol(cd)
        with pytest.raises(ValidationError):
            p.update_condition_definition(cd.id, data_type=ConditionDataType.NUMERIC)

    def test_draft_set_needs_no_reason_and_records_nothing(self) -> None:
        cd = _cd()
        p = _protocol(cd)
        p.clear_events()
        p.set_condition_fixed_value(cd.id, "72")
        assert p.condition_definitions[0].fixed_value == "72"
        assert p.collect_events() == []

    def test_active_needs_a_correction_with_a_reason(self) -> None:
        cd = _cd(fixed_value="72")
        p = _protocol(cd)
        p.publish()
        with pytest.raises(ConflictError):
            p.update_condition_definition(cd.id, fixed_value="48")
        with pytest.raises(ValidationError, match="reason"):
            p.set_condition_fixed_value(cd.id, "48")
        p.clear_events()
        p.set_condition_fixed_value(cd.id, " 48 ", reason="It was always 48 h")
        assert p.condition_definitions[0].fixed_value == "48"
        [event] = p.collect_events()
        assert isinstance(event, ProtocolCorrected)
        assert (event.field, event.old_value, event.new_value) == (
            "condition:Incubation time",
            "72",
            "48",
        )

    def test_active_correction_still_validates(self) -> None:
        cd = _cd()
        p = _protocol(cd)
        p.publish()
        with pytest.raises(ValidationError, match="number"):
            p.set_condition_fixed_value(cd.id, "long", reason="x")

    def test_locked_is_refused(self) -> None:
        cd = _cd()
        p = _protocol(cd)
        p.publish()
        p.lock(locked_by=uuid.uuid4(), reason="review")
        with pytest.raises(ConflictError, match="locked"):
            p.set_condition_fixed_value(cd.id, "72", reason="x")

    def test_retired_is_refused(self) -> None:
        cd = _cd()
        p = _protocol(cd)
        p.publish()
        p.retire()
        assert p.status == ProtocolStatus.RETIRED
        with pytest.raises(ConflictError):
            p.set_condition_fixed_value(cd.id, "72", reason="x")


def test_a_new_version_copies_the_fixed_value() -> None:
    p = _protocol(_cd(fixed_value="72", unit="h"))
    p.publish()
    successor = ProtocolVersioningService().create_new_version(p)
    assert successor.condition_definitions[0].fixed_value == "72"
