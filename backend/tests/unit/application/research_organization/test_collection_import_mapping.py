from cellar.application.research_organization.collection_import_mapping import (
    HeaderSuggestion,
    suggest_column_mapping,
)


def test_suggests_registration_number_for_canonical_synonyms():
    suggestions = suggest_column_mapping(
        ["Reg No.", "Compound Name", "Structure"]
    )
    by_header = {s.header: s for s in suggestions}
    assert by_header["Reg No."].role == "registration_number"
    assert by_header["Compound Name"].role == "name"
    assert by_header["Structure"].role == "smiles"


def test_unknown_header_yields_no_suggestion():
    suggestions = suggest_column_mapping(["Foo Bar Quux"])
    assert suggestions[0].role is None


def test_normalization_is_case_and_punctuation_insensitive():
    s = suggest_column_mapping(["INCHI_KEY"])[0]
    assert s.role == "inchi_key"
