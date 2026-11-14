"""The protocol's method (its description): edited freely on a draft, corrected with a reason
once published, frozen while locked or retired."""

import uuid

import pytest

from cellar.domain.screening_assay.enums import ProtocolType
from cellar.domain.screening_assay.events import ProtocolCorrected
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import ConflictError, ValidationError

METHOD = "Materials: InhA 50 nM\n\nProcedure:\n1. Preincubate 10 min\n2. Read A340"


def _protocol(description=None):
    p = Protocol.create(
        workspace_id=uuid.uuid4(),
        name="InhA inhibition",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        code="PRT-00001",
        description=description,
        readout_definitions=[
            ReadoutDefinition(protocol_id=uuid.uuid4(), name="Signal", data_type="numeric")
        ],
    )
    p.clear_events()
    return p


def _corrections(p):
    return [e for e in p.collect_events() if isinstance(e, ProtocolCorrected)]


def test_a_draft_method_changes_without_a_reason_and_keeps_its_line_breaks():
    p = _protocol()
    p.set_description(f"  {METHOD}\n ")
    assert p.description == METHOD
    assert not _corrections(p)


def test_a_blank_method_clears_it():
    p = _protocol(description="old")
    p.set_description("   ")
    assert p.description is None


def test_a_published_method_needs_a_reason_and_is_audited_with_it():
    p = _protocol(description="old")
    p.publish()
    p.clear_events()
    with pytest.raises(ValidationError, match="reason"):
        p.set_description(METHOD)
    p.set_description(METHOD, reason="Added the read wavelength")
    assert p.description == METHOD
    (event,) = _corrections(p)
    assert event.audit_reason == "Added the read wavelength"
    assert event.audit_changes() == [("description", "old", METHOD)]


def test_an_unchanged_method_records_nothing():
    p = _protocol(description=METHOD)
    p.publish()
    p.clear_events()
    p.set_description(METHOD, reason="no-op")
    assert not _corrections(p)


def test_locked_and_retired_protocols_refuse_method_changes():
    locked = _protocol()
    locked.publish()
    locked.lock(locked_by=uuid.uuid4(), reason="review")
    with pytest.raises(ConflictError):
        locked.set_description(METHOD, reason="r")

    retired = _protocol()
    retired.publish()
    retired.retire(reason="superseded")
    with pytest.raises(ConflictError):
        retired.set_description(METHOD, reason="r")
