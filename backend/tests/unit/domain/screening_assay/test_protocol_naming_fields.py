import uuid

import pytest

from cellar.domain.screening_assay.enums import AliasKind, NameFlag, ProtocolStatus, ProtocolType
from cellar.domain.screening_assay.events import ProtocolRenamed
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import ConflictError, ValidationError


def _protocol(name="PptT inhibition"):
    pid = uuid.uuid4()
    p = Protocol.create(
        workspace_id=uuid.uuid4(),
        name=name,
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        code="PRT-00001",
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="Signal", data_type="numeric")
        ],
    )
    p.clear_events()
    return p


def test_rename_records_former_alias_and_event():
    p = _protocol()
    assert p.apply_derived_name(
        name="PptT inhibition [FP]",
        base="PptT inhibition",
        flag=None,
        reason="Discriminator added",
    )
    assert p.name == "PptT inhibition [FP]" and p.name_base == "PptT inhibition"
    assert [(a.label, a.kind, a.reason) for a in p.aliases] == [
        ("PptT inhibition", AliasKind.FORMER, "Discriminator added")
    ]
    (event,) = p.collect_events()
    assert isinstance(event, ProtocolRenamed) and event.audit_changes() == [
        ("name", "PptT inhibition", "PptT inhibition [FP]")
    ]


def test_same_name_is_not_a_rename():
    p = _protocol()
    assert not p.apply_derived_name(
        name="PptT inhibition",
        base="PptT inhibition",
        flag=NameFlag.NEEDS_DISCRIMINATOR,
        reason="x",
    )
    assert (
        p.collect_events() == []
        and p.aliases == []
        and p.name_flag == NameFlag.NEEDS_DISCRIMINATOR
    )


def test_returning_to_a_former_name_drops_it_from_aliases():
    p = _protocol()
    p.apply_derived_name(name="B", base="B", flag=None, reason="r1")
    p.apply_derived_name(name="PptT inhibition", base="PptT inhibition", flag=None, reason="r2")
    assert [a.label for a in p.aliases] == ["B"]


def test_relabel_allowed_when_locked_or_retired():
    p = _protocol()
    p.publish()
    p.retire(reason="old")
    p.apply_derived_name(
        name="PptT inhibition [FP]", base="PptT inhibition", flag=None, reason="Registry rename"
    )
    assert p.name == "PptT inhibition [FP]"


def test_names_over_400_characters_refused():
    with pytest.raises(ValidationError):
        _protocol().apply_derived_name(name="x" * 401, base="x", flag=None, reason="r")


def test_correction_rules():
    p = _protocol()
    p.set_category("Binding")  # draft: no reason needed
    p.publish()
    with pytest.raises(ValidationError, match="reason"):
        p.set_category("Enzyme inhibition")
    p.set_category("Enzyme inhibition", reason="It was always an enzyme assay")
    assert p.category == "Enzyme inhibition"


def test_locked_protocol_refuses_corrections():
    p = _protocol()
    p.publish()
    p.lock(locked_by=uuid.uuid4(), reason="review")
    with pytest.raises(ConflictError):
        p.set_discriminator("FP", reason="r")


def test_discriminator_is_cleaned():
    p = _protocol()
    p.set_discriminator("  FP ")
    assert p.discriminator == "FP"
    with pytest.raises(ValidationError):
        p.set_discriminator("HTS")


def test_publish_refused_while_facts_missing():
    p = _protocol()
    p.flag_name(NameFlag.NEEDS_FACTS)
    with pytest.raises(ConflictError, match="name"):
        p.publish()
