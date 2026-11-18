"""The bulk file parsers apply a ColumnMapping (spec 2026-11-18 §3).

Files are built in the test with synthetic values shaped like a CDD Vault export.
"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook
from rdkit import Chem

from cellar.application.chemical_registration.bulk_column_mapping import (
    SDF_TITLE_HEADER,
    ColumnMapping,
    MappedColumn,
)
from cellar.application.chemical_registration.bulk_column_mapping import (
    ColumnTarget as T,
)
from cellar.domain.chemical_registration.enums import BulkRegistrationFileFormat
from cellar.domain.shared.errors import ValidationError
from cellar.infrastructure.parsers.chemical_file_parser import (
    BulkFileParserAdapter,
    SDFParser,
    TabularParser,
)

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

# The lab's saved "CDD export" mapping.
CDD_MAPPING = ColumnMapping(
    columns=(
        MappedColumn("Molecule Name", T.NAME),
        MappedColumn("CDD Number", T.IGNORE),
        MappedColumn("SMILES", T.SMILES),
        MappedColumn("Synonyms", T.COMPOUND_ID, "Synonyms"),
        MappedColumn("Alternate Names", T.COMPOUND_ID, "Alternate name"),
        MappedColumn("scientist", T.IGNORE),
        MappedColumn("Batch Name", T.IGNORE),
        MappedColumn("Batch Molecule-Batch ID", T.BATCH_ID, "CDD batch ID"),
        MappedColumn("LGCY Batch Name", T.BATCH_ID, "CDD legacy batch ID"),
    )
)

_SMILES = ["CCO", "CCN", "CCC", "c1ccccc1", "CC(=O)O", "CCOC", "CCCl", "OCCO", "NCCN"]


def _xlsx(rows: list[list[str | None]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(CDD_HEADERS)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cdd_rows() -> list[list[str | None]]:
    """20 rows: 17 compounds, 3 of them with two batches, 8 without a structure."""
    rows: list[list[str | None]] = []
    for i in range(17):
        name = f"SYN-{i:04d}"
        smiles = _SMILES[i] if i < 9 else None
        for b in (1, 2) if i in (0, 9, 16) else (1,):
            rows.append(
                [
                    name,
                    None,
                    smiles,
                    f"JX-{i}" if i % 2 else None,
                    f"ALT-{i}-A\nALT-{i}-B" if i == 3 else None,
                    None,
                    f"{b:03d}",
                    f"{name}-{b:03d}",
                    f"LG-{i:04d}-{b:03d}K001",
                ]
            )
    return rows


def test_cdd_export_parses_every_row() -> None:
    items = TabularParser().parse(_xlsx(_cdd_rows()), "export.xlsx", CDD_MAPPING)

    assert len(items) == 20
    assert [i.error for i in items if i.error] == []
    assert [i.file_row for i in items] == list(range(2, 22))  # header is row 1
    assert sum(1 for i in items if i.smiles is None) == 10  # 8 compounds, two of them twice
    assert {i.name for i in items} == {f"SYN-{i:04d}" for i in range(17)}


def test_row_with_name_and_no_smiles_parses() -> None:
    (item,) = TabularParser().parse(
        _xlsx([["SYN-0042", None, None, "JSF-1187", None, None, "001", None, "JSF-1187"]]),
        "export.xlsx",
        CDD_MAPPING,
    )
    assert item.error is None
    assert (item.name, item.smiles) == ("SYN-0042", None)
    assert item.external_ids == [
        {"identifier": "JSF-1187", "identifier_type": "custom", "source": "Synonyms"}
    ]
    assert item.batch_ids == [{"identifier": "JSF-1187", "source": "CDD legacy batch ID"}]


def test_two_batch_id_columns_give_two_batch_ids_with_their_sources() -> None:
    items = TabularParser().parse(
        _xlsx(
            [
                [
                    "SYN-0003",
                    "CDD-77",
                    "CCO",
                    "JX-3",
                    "ALT-3-A\nALT-3-B",
                    "Dr. Who",
                    "002",
                    "SYN-0003-002",
                    "LG-0003-002K001",
                ]
            ]
        ),
        "export.xlsx",
        CDD_MAPPING,
    )
    (item,) = items
    assert item.file_row == 2
    assert item.batch_ids == [
        {"identifier": "SYN-0003-002", "source": "CDD batch ID"},
        {"identifier": "LG-0003-002K001", "source": "CDD legacy batch ID"},
    ]
    # Compound IDs: every column with its own Source; a cell split on line breaks.
    assert item.external_ids == [
        {"identifier": "JX-3", "identifier_type": "custom", "source": "Synonyms"},
        {"identifier": "ALT-3-A", "identifier_type": "custom", "source": "Alternate name"},
        {"identifier": "ALT-3-B", "identifier_type": "custom", "source": "Alternate name"},
    ]
    # "Don't import" columns are not read anywhere.
    stored = {d["identifier"] for d in item.batch_ids + item.external_ids}
    assert not stored & {"CDD-77", "Dr. Who", "002"}


def test_blank_row_is_an_error_with_its_file_row() -> None:
    items = TabularParser().parse(
        _xlsx(
            [
                ["SYN-0001", None, "CCO", None, None, None, "001", "SYN-0001-001", None],
                ["SYN-0002", None, None, None, None, None, "001", "SYN-0002-001", None],
                [None] * 9,
                ["SYN-0004", None, "CCN", None, None, None, "001", "SYN-0004-001", None],
            ]
        ),
        "export.xlsx",
        CDD_MAPPING,
    )
    assert [i.file_row for i in items] == [2, 3, 4, 5]
    assert items[2].error == "Row 4: no name or structure"
    assert [i.error for i in (items[0], items[1], items[3])] == [None, None, None]


def test_row_with_only_ignored_values_is_an_error() -> None:
    """CDD Number and Batch Name are "Don't import": a row with only those is blank."""
    (item,) = TabularParser().parse(
        _xlsx([[None, "CDD-1", None, None, None, "Dr. Who", "001", None, None]]),
        "export.xlsx",
        CDD_MAPPING,
    )
    assert item.error == "Row 2: no name or structure"


def test_mapping_naming_a_missing_header_raises() -> None:
    mapping = ColumnMapping(
        columns=(
            MappedColumn("Molecule Name", T.NAME),
            MappedColumn("Lot Number", T.BATCH_ID, "Lot"),
        )
    )
    with pytest.raises(ValidationError, match="'Lot Number'"):
        TabularParser().parse(_xlsx([["SYN-1"] + [None] * 8]), "export.xlsx", mapping)
    with pytest.raises(ValidationError, match="'Lot Number'"):
        BulkFileParserAdapter().parse(
            content=_xlsx([["SYN-1"] + [None] * 8]),
            filename="export.xlsx",
            file_format=BulkRegistrationFileFormat.XLSX,
            column_mapping=mapping,
        )


def test_adapter_carries_file_row_and_batch_ids() -> None:
    (dto,) = BulkFileParserAdapter().parse(
        content=_xlsx([["SYN-1", None, "CCO", None, None, None, "001", "SYN-1-001", None]]),
        filename="export.xlsx",
        file_format=BulkRegistrationFileFormat.XLSX,
        column_mapping=CDD_MAPPING,
    )
    assert dto.file_row == 2
    assert dto.batch_ids == [{"identifier": "SYN-1-001", "source": "CDD batch ID"}]


def test_no_mapping_keeps_todays_headers_and_sources() -> None:
    csv = b"name,smiles,custom_id_1,custom_id_2,cas,batch_id\nA,CCO,X-1,X-2,50-78-2,B-1\n"
    (item,) = TabularParser().parse(csv, "rows.csv")
    # No Source key: RegisterMolecule keeps writing "Registration (<file>)".
    assert item.external_ids == [
        {"identifier": "X-1", "identifier_type": "custom"},
        {"identifier": "X-2", "identifier_type": "custom"},
        {"identifier": "50-78-2", "identifier_type": "cas_number"},
    ]
    assert item.batch_ids == [{"identifier": "B-1", "source": "Bulk registration"}]


# ---------------------------------------------------------------------------
# SDF
# ---------------------------------------------------------------------------


def _sdf(records: list[tuple[str, str, dict[str, str]]]) -> bytes:
    buf = io.StringIO()
    writer = Chem.SDWriter(buf)
    for name, smiles, props in records:
        mol = Chem.MolFromSmiles(smiles)
        mol.SetProp("_Name", name)
        for k, v in props.items():
            mol.SetProp(k, v)
        writer.write(mol)
    writer.close()
    return buf.getvalue().encode()


_SDF = [
    ("SYN-1", "CCO", {"Batch ID": "SYN-1-001", "Legacy": "LG-1\nLG-2", "CAS": "64-17-5"}),
    ("SYN-2", "CCN", {"Batch ID": "SYN-2-001"}),
]


def test_sdf_default_mapping_title_line_is_the_name() -> None:
    items = SDFParser().parse(_sdf(_SDF), "rows.sdf")
    assert [(i.file_row, i.name) for i in items] == [(1, "SYN-1"), (2, "SYN-2")]
    assert items[0].smiles == "CCO"
    assert items[0].external_ids == [{"identifier": "64-17-5", "identifier_type": "cas_number"}]
    assert items[0].batch_ids == [{"identifier": "SYN-1-001", "source": "Bulk registration"}]


def test_sdf_properties_mapped() -> None:
    mapping = ColumnMapping(
        columns=(
            MappedColumn(SDF_TITLE_HEADER, T.COMPOUND_ID, "Vault name"),
            MappedColumn("Legacy", T.BATCH_ID, "CDD legacy batch ID"),
            MappedColumn("Batch ID", T.BATCH_ID, "CDD batch ID"),
            MappedColumn("CAS", T.IGNORE),
        )
    )
    items = SDFParser().parse(_sdf(_SDF), "rows.sdf", mapping)

    first = items[0]
    assert first.error is None
    assert first.name is None  # title line went to Compound ID, not the name
    assert first.smiles == "CCO"  # the structure always comes from the record
    assert first.external_ids == [
        {"identifier": "SYN-1", "identifier_type": "custom", "source": "Vault name"}
    ]
    assert first.batch_ids == [
        {"identifier": "LG-1", "source": "CDD legacy batch ID"},
        {"identifier": "LG-2", "source": "CDD legacy batch ID"},
        {"identifier": "SYN-1-001", "source": "CDD batch ID"},
    ]
    assert items[1].batch_ids == [{"identifier": "SYN-2-001", "source": "CDD batch ID"}]


def test_sdf_mapping_naming_a_missing_property_raises() -> None:
    mapping = ColumnMapping(columns=(MappedColumn("Lot", T.BATCH_ID, "Lot"),))
    with pytest.raises(ValidationError, match="'Lot'"):
        SDFParser().parse(_sdf(_SDF), "rows.sdf", mapping)


# --- Final-review fixes -------------------------------------------------------


def test_batch_id_shared_by_two_compounds_is_a_batch_problem_on_each_row() -> None:
    rows = [
        ["CMP-1", None, "CCO", None, None, None, "001", "001", None],
        ["CMP-2", None, "CCN", None, None, None, "001", "001", None],
    ]
    items = TabularParser().parse(_xlsx(rows), "x.xlsx", CDD_MAPPING)
    assert [i.error for i in items] == [None, None]  # the compounds still register
    for i in items:
        assert i.batch_problem is not None
        assert i.batch_problem.startswith("001 is on 2 compounds.")


def test_same_batch_id_twice_for_one_compound_is_not_a_problem() -> None:
    rows = [
        ["CMP-1", None, "CCO", None, None, None, "001", "CMP-1-001", None],
        ["CMP-1", None, "CCO", None, None, None, "001", "CMP-1-001", None],
    ]
    items = TabularParser().parse(_xlsx(rows), "x.xlsx", CDD_MAPPING)
    assert [i.batch_problem for i in items] == [None, None]


def test_ids_longer_than_255_characters_are_not_stored_and_say_so() -> None:
    long = "X" * 300
    rows = [["CMP-1", None, "CCO", long, None, None, "001", long, "LEG-1"]]
    (item,) = TabularParser().parse(_xlsx(rows), "x.xlsx", CDD_MAPPING)
    assert item.error is None
    assert all(e["identifier"] != long for e in item.external_ids)
    assert [b["identifier"] for b in item.batch_ids] == ["LEG-1"]
    assert len(item.warnings) == 2
    assert all("longer than 255 characters" in w for w in item.warnings)


def test_a_source_label_longer_than_255_characters_is_refused() -> None:
    mapping = ColumnMapping(
        columns=(
            MappedColumn("Molecule Name", T.NAME),
            MappedColumn("Synonyms", T.COMPOUND_ID, "S" * 256),
        )
    )
    err = mapping.validate(["Molecule Name", "Synonyms"], structure_implied=False)
    assert err is not None
    assert "Synonyms" in str(err)


def test_headers_with_surrounding_spaces_match_the_trimmed_mapping() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Molecule Name ", " SMILES"])
    ws.append(["CMP-1", "CCO"])
    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    assert TabularParser().headers(content, "x.xlsx") == ["Molecule Name", "SMILES"]
    mapping = ColumnMapping(
        columns=(MappedColumn("Molecule Name", T.NAME), MappedColumn("SMILES", T.SMILES))
    )
    (item,) = TabularParser().parse(content, "x.xlsx", mapping)
    assert (item.name, item.smiles, item.error) == ("CMP-1", "CCO", None)


def test_an_ignored_column_the_file_lacks_does_not_reject_the_mapping() -> None:
    mapping = ColumnMapping(
        columns=(MappedColumn("Molecule Name", T.NAME), MappedColumn("Ghost", T.IGNORE))
    )
    assert mapping.validate(["Molecule Name"], structure_implied=False) is None


def test_semicolon_column_splits_through_the_parser() -> None:
    mapping = ColumnMapping(
        columns=(
            MappedColumn("Name", T.NAME),
            MappedColumn("Alt", T.COMPOUND_ID, "Alt", separator=";"),
        )
    )
    csv = b"Name,Alt\nX,A; B; 51-52-5\n"
    (item,) = TabularParser().parse(csv, "f.csv", mapping)
    assert [(e["identifier"], e["identifier_type"]) for e in item.external_ids] == [
        ("A", "custom"),
        ("B", "custom"),
        ("51-52-5", "cas_number"),
    ]
