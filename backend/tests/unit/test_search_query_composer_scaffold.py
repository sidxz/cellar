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
