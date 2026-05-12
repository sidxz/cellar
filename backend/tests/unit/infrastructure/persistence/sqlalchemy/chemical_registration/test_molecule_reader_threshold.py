import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    _find_first_tanimoto_threshold,
)


def test_no_structure_criterion_returns_none():
    assert _find_first_tanimoto_threshold([]) is None
    assert _find_first_tanimoto_threshold([{"type": "text", "field": "name", "value": "x"}]) is None


def test_finds_top_level_legacy_similarity():
    crits = [{"type": "structure", "search_type": "similarity", "smiles": "CCO", "threshold": 0.42}]
    assert _find_first_tanimoto_threshold(crits) == 0.42


def test_finds_top_level_new_similarity_with_explicit_threshold():
    crits = [{"type": "structure", "kind": "similarity", "smiles": "CCO",
              "mode": "similar", "threshold": 0.55}]
    assert _find_first_tanimoto_threshold(crits) == 0.55


def test_resolves_threshold_from_mode_default_when_omitted():
    # SearchMode.SIMILAR default threshold is 0.7
    crits = [{"type": "structure", "kind": "similarity", "smiles": "CCO", "mode": "similar"}]
    assert _find_first_tanimoto_threshold(crits) == 0.7


def test_skips_fragment_in_target_mode_default_tversky():
    # fragment_in_target mode default is Tversky -> should not set Tanimoto GUC
    crits = [{"type": "structure", "kind": "similarity", "smiles": "CCO",
              "mode": "fragment_in_target"}]
    assert _find_first_tanimoto_threshold(crits) is None


def test_skips_explicit_tversky_metric():
    crits = [{"type": "structure", "kind": "similarity", "smiles": "CCO",
              "mode": "similar",  # mode would say tanimoto, but the explicit metric overrides
              "metric": {"kind": "tversky", "alpha": 1.0, "beta": 0.0},
              "threshold": 0.5}]
    assert _find_first_tanimoto_threshold(crits) is None


def test_walks_into_groups():
    crits = [
        {
            "type": "group",
            "logic": "and",
            "criteria": [
                {"type": "structure", "kind": "similarity", "smiles": "CCO",
                 "mode": "similar", "threshold": 0.42},
            ],
        }
    ]
    assert _find_first_tanimoto_threshold(crits) == 0.42


def test_walks_into_nested_groups():
    crits = [
        {"type": "group", "criteria": [
            {"type": "group", "criteria": [
                {"type": "structure", "kind": "similarity", "smiles": "CCO",
                 "mode": "similar", "threshold": 0.31},
            ]},
        ]}
    ]
    assert _find_first_tanimoto_threshold(crits) == 0.31


def test_first_match_wins_with_multiple_similarity_criteria():
    crits = [
        {"type": "structure", "kind": "similarity", "smiles": "CCO",
         "mode": "similar", "threshold": 0.65},
        {"type": "structure", "kind": "similarity", "smiles": "CCC",
         "mode": "similar", "threshold": 0.85},
    ]
    assert _find_first_tanimoto_threshold(crits) == 0.65
