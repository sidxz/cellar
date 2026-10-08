import uuid

import pytest

from cellar.domain.screening_assay.enums import AliasKind, ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError


def _protocol():
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=uuid.uuid4(),
        name="M. tuberculosis growth inhibition [resazurin]",
        protocol_type=ProtocolType.WHOLE_CELL,
        created_by=uuid.uuid4(),
        code="PRT-00001",
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="Signal", data_type=ReadoutDataType.NUMERIC)
        ],
    )


def test_add_nickname_normalizes_spacing():
    p = _protocol()
    p.add_nickname("  MABA   assay ")
    assert [(a.label, a.kind) for a in p.aliases] == [("MABA assay", AliasKind.NICKNAME)]


def test_duplicate_nickname_any_case_conflicts():
    p = _protocol()
    p.add_nickname("MABA")
    with pytest.raises(ConflictError):
        p.add_nickname("maba")


def test_nickname_equal_to_the_name_conflicts():
    with pytest.raises(ConflictError):
        _protocol().add_nickname("m. tuberculosis growth inhibition [resazurin]")


@pytest.mark.parametrize("bad", ["", "   ", "MABA · REMA", "x" * 401])
def test_bad_nicknames_rejected(bad):
    with pytest.raises(ValidationError):
        _protocol().add_nickname(bad)


def test_remove_nickname_any_case():
    p = _protocol()
    p.add_nickname("LORA")
    p.remove_nickname("lora")
    assert p.aliases == []


def test_remove_unknown_nickname_is_not_found():
    with pytest.raises(NotFoundError):
        _protocol().remove_nickname("REMA")
