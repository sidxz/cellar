"""Unit tests for the scaffold criterion clause."""

from __future__ import annotations

import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)

_WS = uuid.UUID("00000000-0000-0000-0000-ffffffffffff")


def _compose(query: dict) -> object:
    return compose_criteria(query, workspace_id=_WS)


class TestScaffoldClause:
    def test_exact_match_emits_equality_on_bemis_murcko_smiles(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match",
                    "scaffold_smiles": "c1ccncc1",  # pyridine
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "bemis_murcko_smiles" in sql
        assert "=" in sql
        # Canonicalized form of pyridine should appear (RDKit canonical SMILES)
        assert "c1ccncc1" in sql or "c1cnccc1" in sql or "n1ccccc1" in sql

    def test_exact_match_canonicalizes_full_molecule_paste(self) -> None:
        """Pasting a full molecule should match against ITS scaffold."""
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match",
                    "scaffold_smiles": "Nc1ccccn1",  # 2-aminopyridine (full mol)
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # The amine nitrogen ("N") of the input should be GONE — only the
        # ring scaffold remains.
        assert "Nc1" not in sql
        assert "bemis_murcko_smiles" in sql

    def test_acyclic_only_emits_equality_against_empty_string(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "scaffold", "mode": "acyclic_only"}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "bemis_murcko_smiles" in sql
        assert "''" in sql or "= ''" in sql

    def test_negation_inverts_the_clause(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "acyclic_only",
                    "negate": True,
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "bemis_murcko_smiles" in sql
        assert "!=" in sql or "NOT" in sql.upper() or "<>" in sql

    def test_exact_match_without_scaffold_smiles_raises(self) -> None:
        with pytest.raises(ValueError):
            _compose({
                "criteria": [
                    {"type": "scaffold", "mode": "exact_match"}
                ],
                "logic": "and",
            })

    def test_exact_match_rejects_acyclic_smiles_with_helpful_message(self) -> None:
        """Pasting an acyclic SMILES into exact_match should refuse, not silently
        match the acyclic bucket — chemist gets a hint to use mode='acyclic_only'."""
        with pytest.raises(ValueError, match=r"no ring system"):
            _compose({
                "criteria": [
                    {
                        "type": "scaffold",
                        "mode": "exact_match",
                        "scaffold_smiles": "CCCC",  # acyclic
                    }
                ],
                "logic": "and",
            })

    def test_exact_match_with_unparseable_smiles_raises(self) -> None:
        with pytest.raises(ValueError):
            _compose({
                "criteria": [
                    {
                        "type": "scaffold",
                        "mode": "exact_match",
                        "scaffold_smiles": "not-a-smiles!!@@",
                    }
                ],
                "logic": "and",
            })

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            _compose({
                "criteria": [
                    {
                        "type": "scaffold",
                        "mode": "substructure",  # not supported in V1
                        "scaffold_smiles": "c1ccccc1",
                    }
                ],
                "logic": "and",
            })

    def test_exact_match_in_emits_in_clause(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    "scaffold_smiles_list": ["c1ccncc1", "c1ccccc1"],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "bemis_murcko_smiles" in sql
        # SQLAlchemy emits "IN (...)" (uppercase) by default.
        assert " IN " in sql.upper()

    def test_exact_match_in_canonicalizes_each_input(self) -> None:
        """Full-molecule SMILES inputs canonicalize to their scaffolds."""
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    # 2-aminopyridine + 4-aminopyridine: both should canonicalize
                    # to pyridine scaffold; result list should be DE-DUPED.
                    "scaffold_smiles_list": ["Nc1ccccn1", "Nc1ccncc1"],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # The input N atoms should be gone (canonicalized away).
        assert "Nc1" not in sql
        # Both inputs canonicalize to pyridine; only ONE literal should appear
        # in the IN clause (dedup). Count distinct pyridine-ish substrings.
        pyridine_literals = sum(
            sql.count(s) for s in ("'c1ccncc1'", "'c1ccccn1'", "'n1ccccc1'")
        )
        assert pyridine_literals == 1

    def test_exact_match_in_drops_acyclic_entries_silently(self) -> None:
        """Inputs that canonicalize to '' are dropped (caller uses acyclic_only mode for those)."""
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    "scaffold_smiles_list": ["CCCC", "c1ccccc1"],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # Acyclic dropped — only benzene survives. IN clause should have
        # exactly ONE literal.
        assert sql.count("'") == 2  # one literal = two single-quote chars

    def test_exact_match_in_empty_list_emits_false(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    "scaffold_smiles_list": [],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # SQLAlchemy false_() renders as "false" (or "0") depending on dialect.
        assert "false" in sql.lower() or " 0" in sql

    def test_exact_match_in_all_acyclic_emits_false(self) -> None:
        """When every input canonicalizes to '', the post-canonical list is empty."""
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    "scaffold_smiles_list": ["CCCC", "CCO"],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "false" in sql.lower() or " 0" in sql

    def test_exact_match_in_oversized_list_raises(self) -> None:
        """501 scaffolds → ValueError. Cap is 500."""
        with pytest.raises(ValueError, match=r"too many scaffolds"):
            _compose({
                "criteria": [
                    {
                        "type": "scaffold",
                        "mode": "exact_match_in",
                        "scaffold_smiles_list": ["c1ccccc1"] * 501,
                    }
                ],
                "logic": "and",
            })

    def test_exact_match_in_without_list_raises(self) -> None:
        with pytest.raises(ValueError, match=r"scaffold_smiles_list"):
            _compose({
                "criteria": [
                    {"type": "scaffold", "mode": "exact_match_in"}
                ],
                "logic": "and",
            })
