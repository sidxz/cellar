from __future__ import annotations

import uuid

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.protocol_fingerprint import compute_protocol_fingerprint
from cellar.domain.shared.ontology import OntologyTerm


def _protocol(readout_names: list[str]) -> Protocol:
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=uuid.uuid4(),
        name="RNAP core IC50",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name=n, data_type=ReadoutDataType.NUMERIC)
            for n in readout_names
        ],
    )


def test_fingerprint_is_case_and_order_independent() -> None:
    a = compute_protocol_fingerprint(_protocol(["IC50", "Hill slope"]))
    b = compute_protocol_fingerprint(_protocol(["hill   slope", "ic50"]))
    assert a == b
    assert a["readout_kinds"] == ["hill slope", "ic50"]
    assert a["protocol_type"] == "biochemical"
    assert a["v"] == 2


def test_fingerprint_distinguishes_readout_schema() -> None:
    a = compute_protocol_fingerprint(_protocol(["IC50"]))
    b = compute_protocol_fingerprint(_protocol(["Tm"]))
    assert a["readout_kinds"] != b["readout_kinds"]


def test_fingerprint_has_empty_facets_without_annotations() -> None:
    fp = compute_protocol_fingerprint(_protocol(["IC50"]))
    assert fp["facets"] == {}
    assert fp["v"] == 2


def test_fingerprint_derives_facets_from_annotations() -> None:
    p = _protocol(["IC50"])
    p.set_ontology_annotation(
        "organism",
        [OntologyTerm(term_id="NCBITaxon:1773", label="M. tuberculosis", ontology_source="NCBITAXON")],
    )
    p.set_ontology_annotation(
        "detection",
        [OntologyTerm(term_id="free_text:Biomol  Green", label="Biomol  Green", ontology_source="free_text")],
    )
    fp = compute_protocol_fingerprint(p)
    assert fp["facets"]["organism"] == ["ncbitaxon:1773"]
    # free-text facet keys are normalized (lowercased, whitespace-collapsed) so
    # "Biomol  Green" and "biomol green" cluster together.
    assert fp["facets"]["detection"] == ["free_text:biomol green"]
