"""A pasted list of molecule identifiers: tidied, then matched against what the vault returned."""

from __future__ import annotations

from cellar.application.cdd_import.molecule_identifiers import (
    clean_identifiers,
    match_identifiers,
)

# Shape of a molecule from POST /molecules/query (see the vault API reference).
ASPIRIN = {"id": 11, "class": "molecule", "name": "SACC-0001", "synonyms": ["ASA", "Aspirin"]}
CAFFEINE = {"id": 12, "class": "molecule", "name": "SACC-0002", "synonyms": []}


class TestCleanIdentifiers:
    def test_trims_and_drops_blank_entries(self):
        assert clean_identifiers(["  SACC-0001 ", "", "   ", "SACC-0002\t"]) == [
            "SACC-0001",
            "SACC-0002",
        ]

    def test_drops_duplicates_ignoring_case_and_keeps_the_first_spelling(self):
        assert clean_identifiers(["SACC-0001", "sacc-0001", "SACC-0002", "SACC-0001"]) == [
            "SACC-0001",
            "SACC-0002",
        ]


class TestMatchIdentifiers:
    def test_name_and_synonym_are_found_and_the_rest_is_not(self):
        match = match_identifiers(["SACC-0001", "SACC-0002", "SACC-0099"], [ASPIRIN, CAFFEINE])
        assert match.found == ["SACC-0001", "SACC-0002"]
        assert match.not_found == ["SACC-0099"]
        assert match.molecule_ids == [11, 12]

    def test_matching_ignores_case(self):
        match = match_identifiers(["sacc-0001", "aspirin"], [ASPIRIN])
        assert match.found == ["sacc-0001", "aspirin"]
        assert match.not_found == []

    def test_a_name_and_its_synonym_are_one_molecule(self):
        match = match_identifiers(["SACC-0001", "ASA"], [ASPIRIN])
        assert match.found == ["SACC-0001", "ASA"]
        assert match.molecule_ids == [11]

    def test_a_molecule_the_vault_returned_on_a_looser_match_is_left_out(self):
        lookalike = {"id": 13, "name": "SACC-00010", "synonyms": None}
        match = match_identifiers(["SACC-0001"], [lookalike, ASPIRIN])
        assert match.found == ["SACC-0001"]
        assert match.molecule_ids == [11]

    def test_nothing_returned_means_nothing_found(self):
        match = match_identifiers(["SACC-0001"], [])
        assert match.found == []
        assert match.not_found == ["SACC-0001"]
        assert match.molecule_ids == []
