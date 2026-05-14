"""Unit tests for SearchQueryComposer -- query dict -> SQLAlchemy clause."""

from __future__ import annotations

import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import compose_criteria

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

    # ── Activity multi-where (where[] list of conditions ANDed) ──────────

    def test_activity_legacy_single_where_still_works(self) -> None:
        """Inline source+readout_definition_id (single-where shape) works."""
        proto = str(uuid.uuid4())
        rd = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve", "readout_definition_id": rd,
                 "operator": "lt", "value": 1.0}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        assert "fitted_value" in sql

    def test_activity_where_list_two_conditions_anded(self) -> None:
        """where=[{DR<1}, {readout>50}] → two subqueries AND'd."""
        proto = str(uuid.uuid4())
        dr_rd = str(uuid.uuid4())
        readout = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "where": [
                     {"source": "dr_curve", "readout_definition_id": dr_rd,
                      "operator": "lt", "value": 1.0},
                     {"source": "readout_data", "readout_definition_id": readout,
                      "operator": "gte", "value": 50.0},
                 ]}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        # Both data tables referenced
        assert "fitted_value" in sql
        assert "value_numeric" in sql
        # Two subqueries combined under one AND
        assert sql.lower().count("molecules.id in") == 2

    def test_activity_where_between_operator(self) -> None:
        """between requires min+max instead of value."""
        proto = str(uuid.uuid4())
        rd = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "where": [
                     {"source": "dr_curve", "readout_definition_id": rd,
                      "operator": "between", "min": 0.1, "max": 10.0}
                 ]}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        assert "between" in sql.lower()

    def test_activity_where_between_inline_legacy(self) -> None:
        """between also accepted on the single-where shape."""
        proto = str(uuid.uuid4())
        rd = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve", "readout_definition_id": rd,
                 "operator": "between", "min": 0.1, "max": 10.0}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        assert "between" in sql.lower()

    def test_activity_where_empty_list_is_presence_only(self) -> None:
        """where=[] (no conditions) is equivalent to no where at all."""
        proto = str(uuid.uuid4())
        without = _compose({
            "criteria": [{"type": "activity", "protocol_id": proto}],
            "logic": "and",
        })
        with_empty = _compose({
            "criteria": [{"type": "activity", "protocol_id": proto, "where": []}],
            "logic": "and",
        })
        assert str(without.compile()) == str(with_empty.compile())

    def test_activity_where_run_scope_applied_to_each_condition(self) -> None:
        """run_scope must be honored on every where-row."""
        proto = str(uuid.uuid4())
        dr_rd = str(uuid.uuid4())
        readout = str(uuid.uuid4())
        run = "11111111-2222-3333-4444-555555555555"
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "run_scope": {"mode": "specific", "run_id": run},
                 "where": [
                     {"source": "dr_curve", "readout_definition_id": dr_rd,
                      "operator": "lt", "value": 1.0},
                     {"source": "readout_data", "readout_definition_id": readout,
                      "operator": "gte", "value": 50.0},
                 ]}
            ],
            "logic": "and",
        })
        sql = str(clause.compile())
        # run_id constraint should appear in BOTH subqueries (curves and readouts)
        assert sql.lower().count("run_id") >= 2

    def test_activity_where_missing_field_raises(self) -> None:
        """A where-row needs readout_definition_id."""
        proto = str(uuid.uuid4())
        with pytest.raises(ValueError, match="readout_definition_id"):
            _compose({
                "criteria": [
                    {"type": "activity", "protocol_id": proto,
                     "where": [{"operator": "lt", "value": 1.0}]}
                ],
                "logic": "and",
            })

    def test_activity_between_missing_min_max_raises(self) -> None:
        proto = str(uuid.uuid4())
        rd = str(uuid.uuid4())
        with pytest.raises(ValueError, match="between"):
            _compose({
                "criteria": [
                    {"type": "activity", "protocol_id": proto,
                     "where": [
                         {"source": "dr_curve", "readout_definition_id": rd,
                          "operator": "between"}
                     ]}
                ],
                "logic": "and",
            })

    # ── Activity presence-only (no readout_definition_id) ────────────────

    def test_activity_presence_only_matches_any_data(self) -> None:
        """An activity criterion without readout_definition_id is a
        'tested-in-protocol' presence filter — no value comparison."""
        proto = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        # Must reference run table to scope by protocol; should not require
        # value_numeric or fitted_value comparison.
        assert "run" in sql.lower()

    def test_activity_presence_only_with_run_scope(self) -> None:
        proto = str(uuid.uuid4())
        run = "11111111-2222-3333-4444-555555555555"
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "run_scope": {"mode": "specific", "run_id": run}}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile())
        assert "run_id" in sql

    # ── Activity run_scope (per-protocol run scoping) ─────────────────────

    def test_activity_run_scope_any_omits_run_filter(self) -> None:
        """run_scope: any (or absent) leaves the existing un-scoped activity SQL intact."""
        proto = str(uuid.uuid4())
        without = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve",
                 "readout_definition_id": str(uuid.uuid4()),
                 "operator": "lt", "value": 1.0}
            ],
            "logic": "and",
        })
        with_any = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve",
                 "readout_definition_id": str(uuid.uuid4()),
                 "operator": "lt", "value": 1.0,
                 "run_scope": {"mode": "any"}}
            ],
            "logic": "and",
        })
        # Both compile to identical SQL — "any" is the no-op default.
        assert str(without.compile()) == str(with_any.compile())

    def test_activity_run_scope_specific_filters_by_run_id(self) -> None:
        proto = str(uuid.uuid4())
        run = "11111111-2222-3333-4444-555555555555"
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve",
                 "readout_definition_id": str(uuid.uuid4()),
                 "operator": "lt", "value": 1.0,
                 "run_scope": {"mode": "specific", "run_id": run}}
            ],
            "logic": "and",
        })
        sql = str(clause.compile())
        assert "run_id" in sql

    def test_activity_run_scope_date_range_filters_by_run_date(self) -> None:
        proto = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve",
                 "readout_definition_id": str(uuid.uuid4()),
                 "operator": "lt", "value": 1.0,
                 "run_scope": {"mode": "date_range",
                               "date_from": "2026-01-01",
                               "date_to": "2026-03-31"}}
            ],
            "logic": "and",
        })
        sql = str(clause.compile())
        assert "run_date" in sql

    def test_activity_run_scope_past_n_days_filters_recent_runs(self) -> None:
        proto = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve",
                 "readout_definition_id": str(uuid.uuid4()),
                 "operator": "lt", "value": 1.0,
                 "run_scope": {"mode": "past_n_days", "days": 30}}
            ],
            "logic": "and",
        })
        sql = str(clause.compile())
        assert "run_date" in sql

    def test_activity_run_scope_latest_picks_most_recent_run(self) -> None:
        proto = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve",
                 "readout_definition_id": str(uuid.uuid4()),
                 "operator": "lt", "value": 1.0,
                 "run_scope": {"mode": "latest"}}
            ],
            "logic": "and",
        })
        sql = str(clause.compile())
        # Latest = scope to a single run id chosen by max(created_at) for the
        # (workspace, protocol). The compiled SQL should reference both.
        assert "run_id" in sql
        assert "created_at" in sql.lower() or "max" in sql.lower()

    def test_activity_run_scope_all_excludes_violating_runs(self) -> None:
        proto = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve",
                 "readout_definition_id": str(uuid.uuid4()),
                 "operator": "lt", "value": 1.0,
                 "run_scope": {"mode": "all"}}
            ],
            "logic": "and",
        })
        sql = str(clause.compile())
        # "all" semantics: molecule has at least one satisfying value AND no
        # non-satisfying value -> SQL contains a NOT IN guarding against
        # violations.
        assert "not in" in sql.lower()

    def test_activity_run_scope_specific_works_for_readout(self) -> None:
        """run_scope must also apply to raw-readout activity criteria."""
        proto = str(uuid.uuid4())
        readout = str(uuid.uuid4())
        run = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        clause = _compose({
            "criteria": [
                {"type": "activity", "protocol_id": proto,
                 "readout_definition_id": readout,
                 "operator": "gte", "value": 50.0,
                 "run_scope": {"mode": "specific", "run_id": run}}
            ],
            "logic": "and",
        })
        sql = str(clause.compile())
        assert "run_id" in sql

    def test_activity_run_scope_unknown_mode_raises(self) -> None:
        proto = str(uuid.uuid4())
        with pytest.raises(ValueError, match="run_scope"):
            _compose({
                "criteria": [
                    {"type": "activity", "protocol_id": proto,
                 "source": "dr_curve",
                 "readout_definition_id": str(uuid.uuid4()),
                     "operator": "lt", "value": 1.0,
                     "run_scope": {"mode": "wat"}}
                ],
                "logic": "and",
            })

    def test_negate_activity(self) -> None:
        proto = str(uuid.uuid4())
        clause = _compose({
            "criteria": [
                {
                    "type": "activity",
                    "protocol_id": proto,
                    "source": "dr_curve",
                    "readout_definition_id": str(uuid.uuid4()),
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
                    "target_readout_definition_id": str(uuid.uuid4()),
                    "counter_readout_definition_id": str(uuid.uuid4()),
                    "ratio_operator": "gte",
                    "ratio_value": 100,
                }
            ],
            "logic": "and",
        })
        assert clause is not None

    def test_selectivity_different_curve_types(self) -> None:
        """Each side names a DR readout-def; mismatched curve_types (e.g.
        IC50 target vs EC50 counter-screen) are valid by virtue of pointing
        at different readout-defs."""
        clause = _compose({
            "criteria": [
                {
                    "type": "selectivity",
                    "target_readout_definition_id": str(uuid.uuid4()),
                    "counter_readout_definition_id": str(uuid.uuid4()),
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
                        "target_readout_definition_id": str(uuid.uuid4()),
                        "counter_readout_definition_id": str(uuid.uuid4()),
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
                    "target_readout_definition_id": str(uuid.uuid4()),
                    "counter_readout_definition_id": str(uuid.uuid4()),
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
        # Compile without literal_binds — the LargeBinary bindparam cannot be
        # rendered as a SQL literal; we only care about the SQL template shape.
        sql = str(clause.compile())
        assert "morgan_bfp" in sql
        # Morgan path must use bfp_from_binary_text (Python-computed bytes),
        # NOT morganbv_fp(mol_from_smiles(...)) which produces an incompatible format.
        assert "bfp_from_binary_text" in sql
        assert "morganbv_fp" not in sql

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
        # Compile without literal_binds — the LargeBinary bindparam cannot be
        # rendered as a SQL literal; we only care about the SQL template shape.
        sql = str(clause.compile())
        assert "tversky_sml" in sql
        assert "1.0" in sql and "0.0" in sql
        # Morgan Tversky must also use bfp_from_binary_text, not the cartridge fn.
        assert "bfp_from_binary_text" in sql
        assert "morganbv_fp" not in sql

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
        # fragment_in_target -> morgan + tversky. Compile without literal_binds
        # because the Morgan path uses a LargeBinary bindparam.
        sql = str(clause.compile())
        assert "tversky_sml" in sql
        assert "bfp_from_binary_text" in sql

    def test_substructure_uses_qmol_from_smarts(self) -> None:
        """Substructure SMARTS goes through qmol_from_smarts directly.

        Note: mol_adjust_query_properties was originally wrapped here per the
        literature recommendation, but with this cartridge build it stripped
        legitimate aromatic matches (benzene SMARTS hit 2/719 instead of 535/719
        on a real corpus). The cartridge's qmol_from_smarts already handles
        aromaticity perception correctly for the @> operator path.
        """
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
        assert "qmol_from_smarts" in sql
        assert "mol_adjust_query_properties" not in sql

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
        assert "qmol_from_smarts" in sql

    def test_legacy_search_type_exact_still_works(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "structure", "search_type": "exact", "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"}
            ],
            "logic": "and",
        })
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "BSYNRYMUTXBXSQ-UHFFFAOYSA-N" in sql
