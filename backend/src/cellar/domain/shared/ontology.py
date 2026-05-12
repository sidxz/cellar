"""OntologyTerm value object — a reference to a concept in an external ontology."""

from __future__ import annotations

from dataclasses import dataclass

from cellar.domain.shared.errors import ValidationError


@dataclass(frozen=True)
class OntologyTerm:
    """A reference to a concept in an external ontology. Value Object.

    Examples:
        OntologyTerm(term_id="BAO:0000142", label="biosensor method",
                     ontology_source="BAO",
                     uri="http://www.bioassayontology.org/bao#BAO_0000142")
    """

    term_id: str  # "BAO:0000142"
    label: str  # "biosensor method"
    ontology_source: str  # "BAO", "GO", "CLO", "free_text"
    uri: str | None = None  # "http://www.bioassayontology.org/bao#BAO_0000142"

    def __post_init__(self) -> None:
        if not self.term_id or not self.term_id.strip():
            raise ValidationError("OntologyTerm term_id must not be empty")
        if not self.label or not self.label.strip():
            raise ValidationError("OntologyTerm label must not be empty")
        if not self.ontology_source or not self.ontology_source.strip():
            raise ValidationError("OntologyTerm ontology_source must not be empty")
