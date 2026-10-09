"""The BAO assay format a target-based assay has, from its registry target type."""

from __future__ import annotations

from collections.abc import Iterable

from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.shared.ontology import OntologyTerm

BAO = "http://www.bioassayontology.org/bao#"


def _bao(code: str, label: str) -> OntologyTerm:
    return OntologyTerm(
        term_id=f"{BAO}{code}", label=label, ontology_source="BAO", uri=f"{BAO}{code}"
    )


_SINGLE = _bao("BAO_0000357", "single protein format")
_COMPLEX = _bao("BAO_0000223", "protein complex format")

ASSAY_FORMAT_BY_TARGET_TYPE: dict[TargetType, OntologyTerm | None] = {
    TargetType.SINGLE_PROTEIN: _SINGLE,
    TargetType.DOMAIN: _SINGLE,
    TargetType.PROTEIN_COMPLEX: _COMPLEX,
    TargetType.PROTEIN_PROTEIN_INTERACTION: _COMPLEX,
    TargetType.PROTEIN_FAMILY: _bao("BAO_0000224", "protein format"),
    TargetType.NUCLEIC_ACID: _bao("BAO_0000225", "nucleic acid format"),
    TargetType.ORGANISM: _bao("BAO_0000218", "organism-based format"),
    TargetType.CELL_LINE: _bao("BAO_0000219", "cell based format"),
    TargetType.TISSUE: _bao("BAO_0000221", "tissue-based format"),
    TargetType.UNKNOWN: None,
}


def assay_format_for_targets(types: Iterable[TargetType]) -> OntologyTerm | None:
    """One format when every target maps to the same one; otherwise none."""
    formats = {ASSAY_FORMAT_BY_TARGET_TYPE.get(t) for t in types}
    if len(formats) != 1:
        return None
    return formats.pop()
