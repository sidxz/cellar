"""CDD vault molecules through the registration mapping (CDD mapper spec 2026-11-18 §3).

Fixtures are synthetic, shaped like the real export (spec "Data scan").
"""

from __future__ import annotations

from typing import Any

from cellar.application.cdd_import.molecule_mapper import compute_labels, map_cdd_molecules
from cellar.application.cdd_import.registration_mapping import default_cdd_registration_mapping
from cellar.application.chemical_registration.bulk_column_mapping import ColumnMapping
from cellar.domain.workspace_config.data_source import get_default_template

MOL_IDS, BATCH_IDS = get_default_template("cdd_vault")[:2]

MAPPING = ColumnMapping.from_dict(
    {
        "columns": [
            *default_cdd_registration_mapping(),
            {
                "header": "molecule_fields.Alternate Names",
                "target": "compound_id",
                "source": "Alternate Names",
                "separator": ";",
            },
            {
                "header": "batch.batch_fields.LGCY Batch Name",
                "target": "batch_id",
                "source": "CDD legacy batch ID",
            },
        ]
    }
)


def batch(bid: int, cdd_name: str, *, lgcy: str | None = None, **over: Any) -> dict:
    return {
        "id": bid,
        "name": cdd_name.rsplit("-", 1)[-1],
        "molecule_batch_identifier": cdd_name,
        "batch_fields": {"LGCY Batch Name": lgcy, "Batch Synonym": "DDU201703", "Date": "2016"},
        "salt_name": "Unknown Salt",
        "formula_weight": 181.2,
        **over,
    }


def molecule(mid: int, name: str | None, smiles: str | None = None, **over: Any) -> dict:
    obj: dict[str, Any] = {
        "id": mid,
        "class": "compound",
        "name": name,
        "synonyms": [name] if name else [],
        "modified_at": "2026-05-18T10:00:00Z",
        "molecule_fields": {},
        "batches": [],
        **over,
    }
    if smiles:
        obj["smiles"] = smiles
    return obj


def map_one(obj: dict, labels: dict[str, int] | None = None):
    (mol,), warnings = map_cdd_molecules(
        [obj], MAPPING, id_mapping=MOL_IDS, batch_id_mapping=BATCH_IDS, labels=labels
    )
    return mol, warnings


def test_alternate_names_split_on_semicolon_are_stored_only_compound_ids() -> None:
    mol, _ = map_one(
        molecule(
            7,
            "SACC-0015124",
            "CCO",
            synonyms=["SACC-0015124", "JSF-1187"],
            molecule_fields={
                "Alternate Names": "LC:F3097-4245; NCGC00016229-01; Propylthiouracil; 51-52-5"
            },
        )
    )

    alt = {"identifier_type": "custom", "source": "Alternate Names", "decides": False}
    assert mol.external_ids == [
        {"identifier": "7", "identifier_type": "cdd_molecule_id"},  # vault id decides
        {
            "identifier": "JSF-1187",
            "identifier_type": "custom",
            "source": "CDD synonym",
            "decides": False,
        },
        {"identifier": "LC:F3097-4245", **alt},
        {"identifier": "NCGC00016229-01", **alt},
        {"identifier": "Propylthiouracil", **alt},
        {"identifier": "51-52-5", **alt, "identifier_type": "cas_number"},
    ]
    assert mol.name == "SACC-0015124"  # the synonym equal to the name is not repeated


def test_cdd_batch_name_and_vault_id_decide_lgcy_is_stored_only_synonym_ignored() -> None:
    mol, _ = map_one(
        molecule(
            7,
            "SACC-0436536",
            "CCO",
            batches=[
                batch(13250, "SACC-0436536-001", lgcy="MSD-946760565-001K001"),
                batch(13251, "SACC-0436536-002"),
            ],
        )
    )

    first, second = mol.batches
    assert first.cdd_batch_id == 13250
    vault_id = {"source": "CDD import", "identifier_type": "cdd_batch_id", "decides": True}
    assert first.batch_ids == [
        {"identifier": "SACC-0436536-001", "source": "CDD batch ID", "decides": True},
        {"identifier": "MSD-946760565-001K001", "source": "CDD legacy batch ID", "decides": False},
        {"identifier": "13250", **vault_id},
    ]
    assert second.batch_ids == [
        {"identifier": "SACC-0436536-002", "source": "CDD batch ID", "decides": True},
        {"identifier": "13251", **vault_id},
    ]
    # Batch Synonym ("DDU201703", a tag on 16,760 batches) is not mapped.
    assert all(b["identifier"] != "DDU201703" for m in mol.batches for b in m.batch_ids)


def test_cdd_defaults_unknown_salt_purchased_and_modified_at() -> None:
    mol, _ = map_one(
        molecule(
            7,
            "SACC-1",
            "CCO",
            modified_at="2026-05-19T08:00:00Z",
            batches=[batch(1, "SACC-1-001"), batch(2, "SACC-1-002", salt_name="HCl")],
        )
    )

    assert mol.cdd_modified_at == "2026-05-19T08:00:00Z"
    assert [b.salt_code for b in mol.batches] == [None, "HCl"]  # placeholder dropped
    assert [b.batch_source for b in mol.batches] == ["purchased", "purchased"]


def test_molecule_without_name_takes_its_vault_id() -> None:
    mol, warnings = map_one(molecule(42, None, "CCO"))

    assert mol.name == "EXT-42"
    assert [w.reason for w in warnings] == ["No name field; using external ID"]


def test_molecule_without_smiles_is_undisclosed() -> None:
    mol, warnings = map_one(molecule(8, "SACC-0132501", batches=[batch(9, "SACC-0132501-001")]))

    assert mol.smiles is None
    assert [w.reason for w in warnings] == ["No SMILES — registering as undisclosed"]
    assert len(mol.batches) == 1


def test_molecule_without_batches_has_none() -> None:
    mol, _ = map_one(molecule(8, "SACC-2", "CCO", batches=[]))
    assert mol.batches == []


def test_label_is_dropped_with_a_warning() -> None:
    mol, _ = map_one(
        molecule(
            7,
            "SACC-3",
            "CCO",
            molecule_fields={"Alternate Names": "Benzimidazole series; ABC-1"},
        ),
        labels={"benzimidazole series": 4},
    )

    assert [e["identifier"] for e in mol.external_ids] == ["7", "ABC-1"]
    assert mol.warnings == [
        "'Benzimidazole series' is on 4 compounds in the vault; not stored as an ID"
    ]


def test_labels_are_compound_ids_on_two_or_more_molecules() -> None:
    objects = [
        molecule(1, "SACC-A", molecule_fields={"Alternate Names": "Benzimidazole series; A-1"}),
        molecule(
            2,
            "SACC-B",
            molecule_fields={"Alternate Names": "benzimidazole series;B-1;Benzylpenicillin"},
        ),
        # The same name twice on one molecule counts once.
        molecule(3, "SACC-C", molecule_fields={"Alternate Names": "Benzylpenicillin; C-1; C-1"}),
        # A molecule's own name in its synonyms is not one of its IDs.
        molecule(4, "SACC-D", synonyms=["SACC-D", "D-1"]),
        molecule(5, "SACC-E", synonyms=["SACC-E", "SACC-D"]),
    ]

    assert compute_labels(objects, MAPPING) == {"benzimidazole series": 2, "benzylpenicillin": 2}
