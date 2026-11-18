"""ColumnMapping: header suggestions, validation, multi-value cells (spec 2026-11-18 §1-3)."""

from __future__ import annotations

import pytest

from cellar.application.chemical_registration.bulk_column_mapping import (
    LABELLED_TARGETS,
    ColumnMapping,
    MappedColumn,
    extract_row,
    is_cas_number,
    split_multi,
    suggest_column_mapping,
)
from cellar.application.chemical_registration.bulk_column_mapping import (
    ColumnTarget as T,
)
from cellar.domain.shared.errors import ValidationError

CDD_HEADERS = [
    "Molecule Name",
    "CDD Number",
    "SMILES",
    "Synonyms",
    "Alternate Names",
    "scientist",
    "Batch Name",
    "Batch Molecule-Batch ID",
    "LGCY Batch Name",
]


def _by_header(mapping: ColumnMapping) -> dict[str, tuple[T, str | None]]:
    return {c.header: (c.target, c.source) for c in mapping.columns}


def _mapping(*cols: tuple[str, T] | tuple[str, T, str]) -> ColumnMapping:
    return ColumnMapping(columns=tuple(MappedColumn(*c) for c in cols))


def test_suggest_cdd_style_headers() -> None:
    mapping = suggest_column_mapping(CDD_HEADERS)

    assert [c.header for c in mapping.columns] == CDD_HEADERS  # one per header, file order
    assert _by_header(mapping) == {
        "Molecule Name": (T.NAME, None),
        "CDD Number": (T.IGNORE, None),
        "SMILES": (T.SMILES, None),
        "Synonyms": (T.COMPOUND_ID, "Synonyms"),
        "Alternate Names": (T.COMPOUND_ID, "Alternate Names"),
        "scientist": (T.IGNORE, None),
        "Batch Name": (T.IGNORE, None),
        # exact normalised match only: "batchmoleculebatchid" is not "batchid"
        "Batch Molecule-Batch ID": (T.IGNORE, None),
        "LGCY Batch Name": (T.IGNORE, None),
    }


# Every header the parser accepted before the mapper (main's alias sets), matched
# case-insensitively as before.
_TODAYS_ALIASES = [
    *[(h, T.NAME) for h in ["name", "compound_name", "mol_name", "molecule_name", "title"]],
    *[(h, T.SMILES) for h in ["smiles", "canonical_smiles", "structure", "mol_smiles"]],
    *[(h, T.MOLECULE_TYPE) for h in ["molecule_type", "mol_type", "type"]],
    *[(h, T.CAS_NUMBER) for h in ["cas", "cas_number", "cas_no"]],
    *[(h, T.VENDOR_ID) for h in ["vendor_id", "vendor_code", "catalog_number", "catalog_no"]],
    *[(h, T.CHEMBL_ID) for h in ["chembl_id", "chembl"]],
    *[(h, T.PUBCHEM_CID) for h in ["pubchem_cid", "pubchem", "pubchem_id"]],
    *[(h, T.COMPOUND_ID) for h in ["custom_id", "custom_id_1", "custom_id_2"]],
    *[(h, T.AMOUNT_VALUE) for h in ["amount", "amount_value", "quantity"]],
    *[(h, T.AMOUNT_UNIT) for h in ["amount_unit", "unit"]],
    *[(h, T.SALT_CODE) for h in ["salt", "salt_code", "salt_form"]],
    *[(h, T.SALT_STOICHIOMETRY) for h in ["salt_stoichiometry", "stoichiometry"]],
    *[(h, T.PURITY) for h in ["purity", "purity_percent"]],
    *[(h, T.BATCH_SOURCE) for h in ["source", "batch_source"]],
    ("appearance", T.APPEARANCE),
    ("Name", T.NAME),
    (" SMILES ", T.SMILES),
]


@pytest.mark.parametrize(("header", "target"), _TODAYS_ALIASES)
def test_suggest_today_aliases_unchanged(header: str, target: T) -> None:
    (col,) = suggest_column_mapping([header]).columns
    assert col.target == target
    # labelled targets carry the header as their Source; others carry none
    assert col.source == (header if target in LABELLED_TARGETS else None)


@pytest.mark.parametrize(
    "header",
    ["batch_id", "Batch ID", "Lot ID", "lot_number", "External Batch ID", "Legacy Batch ID"],
)
def test_suggest_batch_id_headers(header: str) -> None:
    (col,) = suggest_column_mapping([header]).columns
    assert (col.target, col.source) == (T.BATCH_ID, header)


@pytest.mark.parametrize(
    "header", ["synonym", "Synonyms", "alias", "Aliases", "Alternate Name", "Other Names"]
)
def test_suggest_compound_id_synonyms(header: str) -> None:
    (col,) = suggest_column_mapping([header]).columns
    assert (col.target, col.source) == (T.COMPOUND_ID, header)


def test_template_headers_all_map_somewhere() -> None:
    """The wizard's download template (spec §8) uses only headers the table maps."""
    headers = [
        "name",
        "smiles",
        "molecule_type",
        "synonym",
        "cas_number",
        "batch_id",
        "amount_value",
        "amount_unit",
        "salt_code",
        "purity",
        "batch_source",
        "appearance",
    ]
    assert all(c.target != T.IGNORE for c in suggest_column_mapping(headers).columns)


def test_suggest_second_header_for_a_single_target_is_ignored() -> None:
    mapping = suggest_column_mapping(["name", "Molecule Name", "Synonyms", "alias"])
    assert _by_header(mapping) == {
        "name": (T.NAME, None),
        "Molecule Name": (T.IGNORE, None),
        "Synonyms": (T.COMPOUND_ID, "Synonyms"),
        "alias": (T.COMPOUND_ID, "alias"),  # multi target: both keep it
    }
    assert mapping.validate([c.header for c in mapping.columns], structure_implied=False) is None


def test_validate_missing_header() -> None:
    err = _mapping(("name", T.NAME), ("Batch Code", T.BATCH_ID, "Lab")).validate(
        ["name", "smiles"], structure_implied=False
    )
    assert isinstance(err, ValidationError)
    assert "'Batch Code'" in str(err)


def test_validate_single_target_twice() -> None:
    err = _mapping(("Molecule Name", T.NAME), ("Title", T.NAME)).validate(
        ["Molecule Name", "Title"], structure_implied=False
    )
    assert isinstance(err, ValidationError)
    assert "'Molecule Name'" in str(err) and "'Title'" in str(err)


def test_validate_many_columns_may_share_a_multi_target() -> None:
    mapping = _mapping(
        ("SMILES", T.SMILES),
        ("Synonyms", T.COMPOUND_ID, "Synonyms"),
        ("Alternate Names", T.COMPOUND_ID, "Alternate name"),
        ("Batch ID", T.BATCH_ID, "CDD batch ID"),
        ("LGCY Batch Name", T.BATCH_ID, "CDD legacy batch ID"),
        ("scientist", T.IGNORE),
        ("CDD Number", T.IGNORE),
    )
    assert mapping.validate([c.header for c in mapping.columns], structure_implied=False) is None


def test_validate_labelled_target_needs_a_source() -> None:
    err = _mapping(("name", T.NAME), ("LGCY", T.BATCH_ID)).validate(
        ["name", "LGCY"], structure_implied=False
    )
    assert isinstance(err, ValidationError)
    assert "'LGCY'" in str(err)


def test_validate_needs_name_or_structure() -> None:
    mapping = _mapping(("Batch ID", T.BATCH_ID, "Lab"))
    err = mapping.validate(["Batch ID"], structure_implied=False)
    assert isinstance(err, ValidationError)
    assert "name or the structure" in str(err)
    # SDF: the record carries the structure
    assert mapping.validate(["Batch ID"], structure_implied=True) is None
    assert (
        _mapping(("Molecule Name", T.NAME)).validate(["Molecule Name"], structure_implied=False)
        is None
    )
    assert _mapping(("SMILES", T.SMILES)).validate(["SMILES"], structure_implied=False) is None


def test_from_dict_round_trip_and_blank_source() -> None:
    mapping = ColumnMapping.from_dict(
        {
            "columns": [
                {"header": "Molecule Name", "target": "name"},
                {"header": "LGCY", "target": "batch_id", "source": "  CDD legacy batch ID  "},
                {"header": "Notes", "target": "ignore", "source": "   "},
            ]
        }
    )
    assert _by_header(mapping) == {
        "Molecule Name": (T.NAME, None),
        "LGCY": (T.BATCH_ID, "CDD legacy batch ID"),
        "Notes": (T.IGNORE, None),
    }
    assert ColumnMapping.from_dict(mapping.to_dict()) == mapping


def test_from_dict_unknown_target_names_the_column() -> None:
    with pytest.raises(ValidationError, match="'Weird Column'"):
        ColumnMapping.from_dict({"columns": [{"header": "Weird Column", "target": "nope"}]})


@pytest.mark.parametrize("bad", [{}, {"columns": "x"}, {"columns": [{"target": "name"}]}, []])
def test_from_dict_rejects_malformed(bad: object) -> None:
    with pytest.raises(ValidationError):
        ColumnMapping.from_dict(bad)  # type: ignore[arg-type]


def test_split_multi_line_breaks_only() -> None:
    assert split_multi("A, B\nC") == ["A, B", "C"]
    assert split_multi(" X \r\n\r\nY\rZ\n") == ["X", "Y", "Z"]
    assert split_multi("2-(4-chloro phenyl), 3 HCl") == ["2-(4-chloro phenyl), 3 HCl"]
    assert split_multi("\n \n") == []


def test_split_on_semicolon_only_when_asked() -> None:
    assert split_multi("A; B\nC", ";") == ["A", "B", "C"]
    assert split_multi("A; B\nC") == ["A; B", "C"]


def test_separator_only_on_id_columns() -> None:
    bad = ColumnMapping(columns=(MappedColumn("Name", T.NAME, separator=";"),))
    err = bad.validate(["Name"], structure_implied=False)
    assert err is not None and "'Name'" in str(err)
    odd = ColumnMapping(columns=(MappedColumn("Syn", T.COMPOUND_ID, "Syn", separator=","),))
    assert odd.validate(["Syn"], structure_implied=True) is not None
    ok = ColumnMapping(columns=(MappedColumn("Syn", T.COMPOUND_ID, "Syn", separator=";"),))
    assert ok.validate(["Syn"], structure_implied=True) is None
    assert ColumnMapping.from_dict(ok.to_dict()) == ok


def test_is_cas_number() -> None:
    assert is_cas_number("51-52-5")
    assert not is_cas_number("51-52-6")
    assert not is_cas_number("1234-56-7")  # checksum is 6, not 7
    assert is_cas_number("1234-56-6")
    assert not is_cas_number("abc")


def test_alternate_names_cell_splits_into_ids_and_a_cas() -> None:
    mapping = ColumnMapping(
        columns=(
            MappedColumn("Name", T.NAME),
            MappedColumn("Alt", T.COMPOUND_ID, "Alternate Names", separator=";"),
        )
    )
    cell = "LC:F3097-4245; NCGC00016229-01; Propylthiouracil; 51-52-5"
    row = extract_row({"Name": "X", "Alt": cell}.get, mapping)
    assert row is not None
    assert [(e["identifier"], e["identifier_type"]) for e in row.external_ids] == [
        ("LC:F3097-4245", "custom"),
        ("NCGC00016229-01", "custom"),
        ("Propylthiouracil", "custom"),
        ("51-52-5", "cas_number"),
    ]


def test_extract_row_list_values_and_none() -> None:
    mapping = ColumnMapping(
        columns=(
            MappedColumn("Name", T.NAME),
            MappedColumn("B", T.BATCH_ID, "Batch"),
        )
    )
    row = extract_row({"Name": "X", "B": ["b1", "b2"]}.get, mapping)
    assert row is not None and [b["identifier"] for b in row.batch_ids] == ["b1", "b2"]
    assert extract_row({"B": "b1"}.get, mapping) is None
