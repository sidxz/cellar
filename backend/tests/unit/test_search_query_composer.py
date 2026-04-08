"""Unit tests for SearchQueryComposer -- query dict -> SQLAlchemy clause."""

from __future__ import annotations

import uuid

import pytest

from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import compose_criteria

_WS = uuid.UUID("00000000-0000-0000-0000-ffffffffffff")


def _compose(query: dict) -> object:
    """Shorthand — always passes a dummy workspace_id."""
    return compose_criteria(query, workspace_id=_WS)


class TestComposeCriteria:
    def test_empty_criteria_returns_none(self) -> None:
        clause = _compose({"criteria": [], "logic": "and"})
        assert clause is None

    def test_text_contains(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "text", "field": "name", "operator": "contains", "value": "aspirin"}
            ],
            "logic": "and",
        })
        assert clause is not None
        compiled = clause.compile(compile_kwargs={"literal_binds": True})
        sql = str(compiled)
        assert "LIKE" in sql.upper()

    def test_text_equals(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "text", "field": "registration_number", "operator": "equals", "value": "CV-00001"}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_property_between(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "property", "field": "molecular_weight", "operator": "between", "min": 200, "max": 500}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_property_lte(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "property", "field": "logp", "operator": "lte", "value": 5.0}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_multiple_and(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "text", "field": "name", "operator": "contains", "value": "aspirin"},
                {"type": "property", "field": "molecular_weight", "operator": "lte", "value": 500},
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_multiple_or(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "text", "field": "name", "operator": "contains", "value": "aspirin"},
                {"type": "text", "field": "name", "operator": "contains", "value": "ibuprofen"},
            ],
            "logic": "or",
        })
        assert clause is not None

    def test_invalid_field_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown text field"):
            _compose({
                "criteria": [
                    {"type": "text", "field": "nonexistent", "operator": "contains", "value": "x"}
                ],
                "logic": "and",
            })

    def test_invalid_property_field_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown property field"):
            _compose({
                "criteria": [
                    {"type": "property", "field": "bad_field", "operator": "eq", "value": 1}
                ],
                "logic": "and",
            })

    def test_structure_substructure(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "structure", "search_type": "substructure", "smarts": "c1ccccc1"}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_structure_similarity(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "structure", "search_type": "similarity", "smiles": "c1ccccc1", "threshold": 0.7}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_structure_exact(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "structure", "search_type": "exact", "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"}
            ],
            "logic": "and",
        })
        assert clause is not None
