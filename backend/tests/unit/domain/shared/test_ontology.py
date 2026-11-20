"""Tests for OntologyTerm value object."""

from __future__ import annotations

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.ontology import OntologyTerm


class TestOntologyTermCreation:
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
