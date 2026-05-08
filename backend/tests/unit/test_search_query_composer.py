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

    # ── Negate ─────────────────────────────────────────────────────────────

    def test_negate_text(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "text", "field": "name", "operator": "contains", "value": "aspirin", "negate": True}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # Negated LIKE becomes NOT (... LIKE ...)
        assert "NOT" in sql.upper()

    def test_negate_property(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "property", "field": "molecular_weight", "operator": "gt", "value": 500, "negate": True}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_negate_false_has_no_effect(self) -> None:
        normal = _compose({
            "criteria": [
                {"type": "text", "field": "name", "operator": "equals", "value": "test"}
            ],
            "logic": "and",
        })
        explicit_false = _compose({
            "criteria": [
                {"type": "text", "field": "name", "operator": "equals", "value": "test", "negate": False}
            ],
            "logic": "and",
        })
        assert str(normal.compile(compile_kwargs={"literal_binds": True})) == str(
            explicit_false.compile(compile_kwargs={"literal_binds": True})
        )

    def test_negate_activity(self) -> None:
        proto = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {
                    "type": "activity",
                    "protocol_id": proto,
                    "curve_type": "ic50",
                    "operator": "lt",
                    "value": 100,
                    "negate": True,
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        assert "NOT" in sql.upper()

    def test_negate_collection(self) -> None:
        coll = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "collection", "collection_id": coll, "negate": True}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        assert "NOT" in sql.upper()

    # ── Selectivity ────────────────────────────────────────────────────────

    def test_selectivity_basic(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "selectivity",
                    "target_protocol_id": str(uuid.uuid4()),
                    "target_curve_type": "ic50",
                    "counter_protocol_id": str(uuid.uuid4()),
                    "counter_curve_type": "ic50",
                    "ratio_operator": "gte",
                    "ratio_value": 100,
                }
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_selectivity_different_curve_types(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "selectivity",
                    "target_protocol_id": str(uuid.uuid4()),
                    "target_curve_type": "ic50",
                    "counter_protocol_id": str(uuid.uuid4()),
                    "counter_curve_type": "ec50",
                    "ratio_operator": "gt",
                    "ratio_value": 50,
                }
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_selectivity_invalid_operator(self) -> None:
        with pytest.raises(ValueError, match="Unknown selectivity ratio operator"):
            _compose({
                "criteria": [
                    {
                        "type": "selectivity",
                        "target_protocol_id": str(uuid.uuid4()),
                        "target_curve_type": "ic50",
                        "counter_protocol_id": str(uuid.uuid4()),
                        "counter_curve_type": "ic50",
                        "ratio_operator": "like",
                        "ratio_value": 100,
                    }
                ],
                "logic": "and",
            })

    def test_selectivity_with_negate(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "selectivity",
                    "target_protocol_id": str(uuid.uuid4()),
                    "target_curve_type": "ic50",
                    "counter_protocol_id": str(uuid.uuid4()),
                    "counter_curve_type": "ic50",
                    "ratio_operator": "gte",
                    "ratio_value": 100,
                    "negate": True,
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        assert "NOT" in sql.upper()

    # ── Nested boolean groups ──────────────────────────────────────────────

    def test_group_flat_or(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "group",
                    "logic": "or",
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "aspirin"},
                        {"type": "text", "field": "name", "operator": "contains", "value": "ibuprofen"},
                    ],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True})).upper()
        assert "OR" in sql

    def test_group_nested(self) -> None:
        """(name contains aspirin OR name contains ibuprofen) AND MW < 500."""
        clause = _compose({
            "criteria": [
                {
                    "type": "group",
                    "logic": "or",
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "aspirin"},
                        {"type": "text", "field": "name", "operator": "contains", "value": "ibuprofen"},
                    ],
                },
                {"type": "property", "field": "molecular_weight", "operator": "lt", "value": 500},
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True})).upper()
        assert "OR" in sql
        assert "AND" in sql

    def test_group_double_nested(self) -> None:
        """((A OR B) AND (C OR D))."""
        clause = _compose({
            "criteria": [
                {
                    "type": "group",
                    "logic": "and",
                    "criteria": [
                        {
                            "type": "group",
                            "logic": "or",
                            "criteria": [
                                {"type": "text", "field": "name", "operator": "equals", "value": "A"},
                                {"type": "text", "field": "name", "operator": "equals", "value": "B"},
                            ],
                        },
                        {
                            "type": "group",
                            "logic": "or",
                            "criteria": [
                                {"type": "property", "field": "logp", "operator": "gt", "value": 2},
                                {"type": "property", "field": "logp", "operator": "lt", "value": -1},
                            ],
                        },
                    ],
                }
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_group_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one sub-criterion"):
            _compose({
                "criteria": [{"type": "group", "logic": "or", "criteria": []}],
                "logic": "and",
            })

    def test_group_max_depth_raises(self) -> None:
        # Build 5-deep nesting (limit is 4)
        inner: dict = {"type": "text", "field": "name", "operator": "equals", "value": "x"}
        for _ in range(5):
            inner = {"type": "group", "logic": "and", "criteria": [inner]}
        with pytest.raises(ValueError, match="max depth"):
            _compose({"criteria": [inner], "logic": "and"})

    def test_group_with_negate_on_sub(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "group",
                    "logic": "and",
                    "criteria": [
                        {"type": "text", "field": "name", "operator": "contains", "value": "aspirin"},
                        {"type": "text", "field": "name", "operator": "contains", "value": "toxic", "negate": True},
                    ],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True})).upper()
        assert "NOT" in sql

    # ── Custom field search ────────────────────────────────────────────────

    def test_custom_field_text_contains(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "custom_field", "field": "project_code", "mode": "text", "operator": "contains", "value": "ABC"}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_custom_field_text_equals(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "custom_field", "field": "source", "mode": "text", "operator": "equals", "value": "CRO-1"}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_custom_field_numeric_gt(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "custom_field", "field": "solubility", "mode": "numeric", "operator": "gt", "value": 0.5}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_custom_field_numeric_between(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "custom_field", "field": "score", "mode": "numeric", "operator": "between", "min": 1, "max": 10}
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_custom_field_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown custom_field mode"):
            _compose({
                "criteria": [
                    {"type": "custom_field", "field": "x", "mode": "boolean", "value": True}
                ],
                "logic": "and",
            })

    def test_custom_field_invalid_operator_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown custom_field text operator"):
            _compose({
                "criteria": [
                    {"type": "custom_field", "field": "x", "mode": "text", "operator": "regex", "value": ".*"}
                ],
                "logic": "and",
            })


# ── New discriminated-union structure tests ────────────────────────────────


class TestStructureClauseNewShape:
    """Tests for the new kind-discriminated structure criterion shape."""

    def test_similarity_morgan_tanimoto_compiles(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "structure",
                    "kind": "similarity",
                    "smiles": "CCO",
                    "algorithm": "morgan",
                    "metric": {"kind": "tanimoto"},
                    "threshold": 0.7,
                }
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "morgan_bfp" in sql
        assert "morganbv_fp" in sql
        assert "mol_from_smiles" in sql

    def test_similarity_fcfp_tanimoto_compiles(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "structure",
                    "kind": "similarity",
                    "smiles": "CCO",
                    "algorithm": "fcfp",
                    "metric": {"kind": "tanimoto"},
                    "threshold": 0.55,
                }
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "fcfp_bfp" in sql
        assert "featmorganbv_fp" in sql

    def test_similarity_tversky_uses_function_form(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "structure",
                    "kind": "similarity",
                    "smiles": "c1ccccc1",
                    "algorithm": "morgan",
                    "metric": {"kind": "tversky", "alpha": 1.0, "beta": 0.0},
                    "threshold": 0.7,
                }
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "tversky_sml" in sql
        assert "1.0" in sql and "0.0" in sql

    def test_similarity_with_mode_resolves_defaults(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "structure",
                    "kind": "similarity",
                    "smiles": "CCO",
                    "mode": "scaffold_hop",
                }
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # scaffold_hop -> fcfp + tanimoto
        assert "fcfp_bfp" in sql
        assert "featmorganbv_fp" in sql

    def test_similarity_with_fragment_in_target_mode_uses_tversky(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "structure",
                    "kind": "similarity",
                    "smiles": "CCO",
                    "mode": "fragment_in_target",
                }
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "tversky_sml" in sql

    def test_substructure_passes_through_mol_adjust_query_properties(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "structure",
                    "kind": "substructure",
                    "smiles_or_smarts": "c1ccccc1",
                }
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "mol_adjust_query_properties" in sql

    def test_substructure_generalized_uses_xqmol_and_double_arrow(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "structure",
                    "kind": "substructure",
                    "smiles_or_smarts": "OC1=CC=CC=N1",
                    "generalized": True,
                }
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "@>>" in sql
        assert "mol_to_xqmol" in sql

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown structure"):
            _compose({
                "criteria": [
                    {"type": "structure", "kind": "fancy"}
                ],
                "logic": "and",
            })

    def test_exact_match_inchi_key_unchanged(self) -> None:
        """The exact path didn't change — assert backwards compat with InChIKey."""
        clause = _compose({
            "criteria": [
                {
                    "type": "structure",
                    "kind": "exact",
                    "inchi_key": "ABCDEFGHIJKLMN-OPQRSTUVWX-Y",
                }
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "ABCDEFGHIJKLMN-OPQRSTUVWX-Y" in sql

    def test_legacy_search_type_substructure_still_works(self) -> None:
        """Legacy search_type alias must continue to route correctly."""
        clause = _compose({
            "criteria": [
                {"type": "structure", "search_type": "substructure", "smarts": "c1ccccc1"}
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "mol_adjust_query_properties" in sql

    def test_legacy_search_type_exact_still_works(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "structure", "search_type": "exact", "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"}
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "BSYNRYMUTXBXSQ-UHFFFAOYSA-N" in sql
