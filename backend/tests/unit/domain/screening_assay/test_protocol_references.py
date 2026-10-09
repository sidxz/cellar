"""Protocol references: typed, validated provenance (ChEMBL assay, PubChem AID, DOI, PMID, URL)."""

import uuid

import pytest

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType, ReferenceKind
from cellar.domain.screening_assay.events import ProtocolUpdated
from cellar.domain.screening_assay.protocol import Protocol, ProtocolReference, ReadoutDefinition
from cellar.domain.screening_assay.protocol_versioning_service import ProtocolVersioningService
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError


def _protocol(**kw) -> Protocol:
    pid = uuid.uuid4()
    p = Protocol.create(
        workspace_id=uuid.uuid4(),
        name="M. tuberculosis growth inhibition",
        protocol_type=ProtocolType.WHOLE_CELL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="MIC", data_type=ReadoutDataType.NUMERIC)
        ],
        **kw,
    )
    p.clear_events()
    return p


@pytest.mark.parametrize(
    ("kind", "raw", "value"),
    [
        ("chembl_assay", "CHEMBL1054500", "CHEMBL1054500"),
        ("pubchem_aid", "1851", "1851"),
        ("pubchem_aid", "AID 1851", "1851"),
        ("pubchem_aid", "aid1851", "1851"),
        ("doi", "10.1021/jm901137j", "10.1021/jm901137j"),
        ("doi", "https://doi.org/10.1021/JM901137J", "10.1021/JM901137J"),
        ("doi", "http://doi.org/10.1021/jm901137j", "10.1021/jm901137j"),
        ("doi", "doi:10.1021/jm901137j", "10.1021/jm901137j"),
        ("pmid", " 19919034 ", "19919034"),
        ("url", "https://example.org/assay?id=3", "https://example.org/assay?id=3"),
        ("url", "http://example.org", "http://example.org"),
    ],
)
def test_valid_references_normalize(kind, raw, value):
    ref = ProtocolReference(kind=kind, value=raw)
    assert (ref.kind, ref.value) == (ReferenceKind(kind), value)
    assert ref.key == f"{kind}:{value}"


@pytest.mark.parametrize(
    ("kind", "raw"),
    [
        ("url", "javascript:alert(1)"),
        ("url", "data:text/html,<script>alert(1)</script>"),
        ("url", "ftp://example.org"),
        ("url", "https://"),
        ("url", "https://exa mple.org"),
        ("chembl_assay", "1054500"),
        ("chembl_assay", "CHEMBL"),
        ("pubchem_aid", "AID"),
        ("pubchem_aid", "18a51"),
        ("doi", "11.1021/x"),
        ("doi", "10.12/x"),
        ("doi", "10.1021/"),
        ("pmid", "PMID19919034"),
        ("pmid", ""),
        ("isbn", "123"),
    ],
)
def test_invalid_references_rejected(kind, raw):
    with pytest.raises(ValidationError):
        ProtocolReference(kind=kind, value=raw)


def test_round_trips_through_a_dict():
    ref = ProtocolReference(kind="doi", value="doi:10.1021/jm901137j")
    assert ProtocolReference.from_stored(ref.to_dict()) == ref
    assert ref.to_dict() == {"kind": "doi", "value": "10.1021/jm901137j"}


def test_a_stored_value_loads_even_if_input_rules_now_refuse_it():
    ref = ProtocolReference.from_stored({"kind": "doi", "value": "doi-under-old-rules"})
    assert (ref.kind, ref.key) == (ReferenceKind.DOI, "doi:doi-under-old-rules")


def test_create_takes_references_and_refuses_duplicates():
    p = _protocol(references=[ProtocolReference(kind="pmid", value="19919034")])
    assert [r.key for r in p.references] == ["pmid:19919034"]
    with pytest.raises(ConflictError):
        _protocol(
            references=[
                ProtocolReference(kind="doi", value="10.1021/jm901137j"),
                ProtocolReference(kind="doi", value="https://doi.org/10.1021/jm901137j"),
            ]
        )


def test_add_on_a_draft_is_audited_with_the_reference():
    p = _protocol()
    p.add_reference(ProtocolReference(kind="chembl_assay", value="CHEMBL1054500"))
    assert [r.key for r in p.references] == ["chembl_assay:CHEMBL1054500"]
    (event,) = p.collect_events()
    assert isinstance(event, ProtocolUpdated)
    assert event.audit_changes() == [("references", None, "chembl_assay:CHEMBL1054500")]


def test_duplicate_after_normalization_conflicts():
    p = _protocol()
    p.add_reference(ProtocolReference(kind="pubchem_aid", value="1851"))
    with pytest.raises(ConflictError):
        p.add_reference(ProtocolReference(kind="pubchem_aid", value="AID 1851"))


def test_same_value_under_another_kind_is_not_a_duplicate():
    p = _protocol()
    p.add_reference(ProtocolReference(kind="pmid", value="1851"))
    p.add_reference(ProtocolReference(kind="pubchem_aid", value="1851"))
    assert len(p.references) == 2


def test_add_and_remove_on_an_active_protocol():
    p = _protocol()
    p.publish()
    p.clear_events()
    p.add_reference(ProtocolReference(kind="pmid", value="19919034"))
    p.remove_reference("pmid:19919034")
    assert p.references == []
    added, removed = p.collect_events()
    assert added.audit_changes() == [("references", None, "pmid:19919034")]
    assert removed.audit_changes() == [("references", "pmid:19919034", None)]


def test_remove_unknown_reference_is_not_found():
    with pytest.raises(NotFoundError):
        _protocol().remove_reference("pmid:1")


def test_locked_protocol_refuses_both():
    p = _protocol(references=[ProtocolReference(kind="pmid", value="1")])
    p.lock(locked_by=uuid.uuid4(), reason="review")
    with pytest.raises(ConflictError):
        p.add_reference(ProtocolReference(kind="pmid", value="2"))
    with pytest.raises(ConflictError):
        p.remove_reference("pmid:1")


def test_retired_protocol_refuses_both():
    p = _protocol(references=[ProtocolReference(kind="pmid", value="1")])
    p.publish()
    p.retire()
    with pytest.raises(ConflictError):
        p.add_reference(ProtocolReference(kind="pmid", value="2"))
    with pytest.raises(ConflictError):
        p.remove_reference("pmid:1")


def test_a_new_version_copies_the_references():
    p = _protocol(references=[ProtocolReference(kind="pmid", value="19919034")])
    p.publish()
    successor = ProtocolVersioningService().create_new_version(p)
    assert [r.key for r in successor.references] == ["pmid:19919034"]
