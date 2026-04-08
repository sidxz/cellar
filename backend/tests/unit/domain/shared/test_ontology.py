"""Tests for OntologyTerm value object."""

from __future__ import annotations

import pytest

from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.ontology import OntologyTerm


class TestOntologyTermCreation:
    def test_valid_creation(self):
        term = OntologyTerm(
            term_id="BAO:0000142",
            label="biosensor method",
            ontology_source="BAO",
            uri="http://www.bioassayontology.org/bao#BAO_0000142",
        )
        assert term.term_id == "BAO:0000142"
        assert term.label == "biosensor method"
        assert term.ontology_source == "BAO"
        assert term.uri == "http://www.bioassayontology.org/bao#BAO_0000142"

    def test_valid_creation_without_uri(self):
        term = OntologyTerm(
            term_id="GO:0008150",
            label="biological_process",
            ontology_source="GO",
        )
        assert term.uri is None

    def test_empty_term_id_raises(self):
        with pytest.raises(ValidationError, match="term_id"):
            OntologyTerm(term_id="", label="test", ontology_source="BAO")

    def test_whitespace_term_id_raises(self):
        with pytest.raises(ValidationError, match="term_id"):
            OntologyTerm(term_id="   ", label="test", ontology_source="BAO")

    def test_empty_label_raises(self):
        with pytest.raises(ValidationError, match="label"):
            OntologyTerm(term_id="BAO:001", label="", ontology_source="BAO")

    def test_whitespace_label_raises(self):
        with pytest.raises(ValidationError, match="label"):
            OntologyTerm(term_id="BAO:001", label="  ", ontology_source="BAO")

    def test_empty_ontology_source_raises(self):
        with pytest.raises(ValidationError, match="ontology_source"):
            OntologyTerm(term_id="BAO:001", label="test", ontology_source="")

    def test_whitespace_ontology_source_raises(self):
        with pytest.raises(ValidationError, match="ontology_source"):
            OntologyTerm(term_id="BAO:001", label="test", ontology_source="   ")


class TestOntologyTermFrozen:
    def test_is_frozen(self):
        term = OntologyTerm(
            term_id="BAO:0000142",
            label="biosensor method",
            ontology_source="BAO",
        )
        with pytest.raises(AttributeError):
            term.term_id = "changed"  # type: ignore[misc]

    def test_is_frozen_label(self):
        term = OntologyTerm(
            term_id="BAO:0000142",
            label="biosensor method",
            ontology_source="BAO",
        )
        with pytest.raises(AttributeError):
            term.label = "changed"  # type: ignore[misc]


class TestOntologyTermEquality:
    def test_equal_terms(self):
        a = OntologyTerm(term_id="BAO:001", label="test", ontology_source="BAO")
        b = OntologyTerm(term_id="BAO:001", label="test", ontology_source="BAO")
        assert a == b

    def test_unequal_terms(self):
        a = OntologyTerm(term_id="BAO:001", label="test", ontology_source="BAO")
        b = OntologyTerm(term_id="BAO:002", label="other", ontology_source="BAO")
        assert a != b

    def test_hashable(self):
        term = OntologyTerm(term_id="BAO:001", label="test", ontology_source="BAO")
        # Frozen dataclasses are hashable
        assert hash(term) is not None
        s = {term}
        assert term in s
