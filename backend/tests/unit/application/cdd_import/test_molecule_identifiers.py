"""A pasted list of molecule identifiers: parsed, tidied, then matched to the vault's answer."""

from __future__ import annotations

from cellar.application.cdd_import.molecule_identifiers import (
    clean_identifiers,
    match_identifiers,
    parse_identifiers,
)

# Shape of a molecule from POST /molecules/query (see the vault API reference).
ASPIRIN = {"id": 11, "class": "molecule", "name": "SACC-0001", "synonyms": ["ASA", "Aspirin"]}
CAFFEINE = {"id": 12, "class": "molecule", "name": "SACC-0002", "synonyms": []}
PALMITOYL_COA = {"id": 14, "name": "16:0 CoA", "synonyms": ["Palmitoyl CoA"]}


class TestParseIdentifiers:
    def test_new_lines_commas_semicolons_and_tabs_separate(self):
        assert parse_identifiers("SACC-1\nSACC-2,SACC-3;SACC-4\tSACC-5\r\nSACC-6") == [
            "SACC-1",
            "SACC-2",
            "SACC-3",
            "SACC-4",
            "SACC-5",
            "SACC-6",
        ]

    def test_a_name_with_spaces_on_its_own_line_stays_whole(self):
        assert parse_identifiers("SACC-0001\n16:0 CoA\nPalmitoyl CoA") == [
            "SACC-0001",
            "16:0 CoA",
            "Palmitoyl CoA",
        ]

    def test_spaces_never_separate(self):
        assert parse_identifiers("16:0 CoA, Palmitoyl CoA; Acetyl CoA") == [
            "16:0 CoA",
            "Palmitoyl CoA",
            "Acetyl CoA",
        ]

    def test_a_pasted_spreadsheet_column(self):
        # Excel puts CRLF between cells of a column and after the last one.
        column = "Compound\r\nSACC-0001\r\n  16:0  CoA \r\n\r\nSACC-0002\r\nsacc-0001\r\n"
        assert parse_identifiers(column) == ["Compound", "SACC-0001", "16:0 CoA", "SACC-0002"]

    def test_a_pasted_spreadsheet_row(self):
        assert parse_identifiers("SACC-0001\t16:0 CoA\t\tSACC-0002\n") == [
            "SACC-0001",
            "16:0 CoA",
            "SACC-0002",
        ]

    def test_entries_are_trimmed_and_inner_white_space_is_one_space(self):
        assert parse_identifiers("  Palmitoyl    CoA  ,\tSACC-1  ") == ["Palmitoyl CoA", "SACC-1"]

    def test_blank_entries_are_ignored(self):
        assert parse_identifiers("\n\n SACC-1 ,, ; ,\n\t\nSACC-2\n") == ["SACC-1", "SACC-2"]
        assert parse_identifiers("") == []
        assert parse_identifiers("  \n ,;\t") == []

    def test_duplicates_are_ignored_whatever_their_case_or_spacing(self):
        assert parse_identifiers("16:0 CoA\n16:0  coa\nSACC-1\n16:0 CoA") == ["16:0 CoA", "SACC-1"]


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

    def test_an_entry_is_one_identifier_whatever_it_contains(self):
        # Already a list: a comma inside an entry is part of the name.
        assert clean_identifiers(["2,4-DNP", "16:0  CoA"]) == ["2,4-DNP", "16:0 CoA"]


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

    def test_a_name_with_spaces_matches_whole(self):
        match = match_identifiers(["16:0 CoA", "Palmitoyl CoA", "CoA"], [PALMITOYL_COA])
        assert match.found == ["16:0 CoA", "Palmitoyl CoA"]
        assert match.not_found == ["CoA"]
        assert match.molecule_ids == [14]

    def test_matching_ignores_how_the_vault_spaced_a_name(self):
        spaced = {"id": 15, "name": " 18:1  CoA ", "synonyms": []}
        assert match_identifiers(["18:1 CoA"], [spaced]).molecule_ids == [15]

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
