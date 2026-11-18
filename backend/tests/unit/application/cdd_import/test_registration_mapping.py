"""Registration mapping on a CDD data source: defaults, validation, vault fields."""

from __future__ import annotations

from cellar.application.cdd_import.list_vault_fields import build_vault_fields
from cellar.application.cdd_import.registration_mapping import (
    default_cdd_registration_mapping,
    validate_registration_mapping,
)
from cellar.domain.workspace_config.data_source import DataSource


def _col(header: str, target: str, source: str | None = None) -> dict:
    return {"header": header, "target": target, "source": source}


def test_default_mapping_has_no_batch_synonym() -> None:
    cols = default_cdd_registration_mapping()
    assert not any("Batch Synonym" in c["header"] for c in cols)
    assert validate_registration_mapping(cols) is None


def test_level_rule_names_the_field() -> None:
    err = validate_registration_mapping(
        [_col("batch.batch_fields.LGCY Batch Name", "compound_id", "LGCY")]
    )
    assert err is not None
    assert "batch.batch_fields.LGCY Batch Name" in str(err)


def test_level_rule_refuses_a_compound_path_for_a_batch_target() -> None:
    err = validate_registration_mapping([_col("molecule_fields.Alternate Names", "batch_id", "X")])
    assert err is not None
    assert "molecule_fields.Alternate Names" in str(err)


def test_admin_added_mappings_validate() -> None:
    cols = [
        *default_cdd_registration_mapping(),
        {
            **_col("molecule_fields.Alternate Names", "compound_id", "Alternate Names"),
            "separator": ";",
        },
        _col("batch.batch_fields.LGCY Batch Name", "batch_id", "CDD legacy batch ID"),
        _col("batch.batch_fields.Amount", "amount_value"),
    ]
    assert validate_registration_mapping(cols) is None


def test_phase_one_rules_still_apply() -> None:
    err = validate_registration_mapping([_col("synonyms", "compound_id")])  # no Source
    assert err is not None


def test_new_cdd_source_molecule_and_batch_keep_wiring_only() -> None:
    import uuid

    ds = DataSource.create_cdd_vault(
        workspace_id=uuid.uuid4(),
        name="v",
        vault_id="1",
        api_key_name="k",
        created_by=uuid.uuid4(),
    )
    for kind in ("molecule", "batch"):
        em = ds.get_entity_mapping(kind)
        assert em is not None and em.field_mappings == []
        assert em.id_storage.custom_field_name
    plate = ds.get_entity_mapping("plate")
    assert plate is not None and plate.field_mappings


def test_vault_fields_from_objects_and_strings() -> None:
    f = build_vault_fields(
        {
            "molecule": [{"name": "Alternate Names"}, {"name": "scientist"}],
            "batch": ["LGCY Batch Name"],
            "protocol": [{"name": "ignored"}],
        }
    )
    assert "molecule_fields.Alternate Names" in [x.path for x in f.molecule]
    assert "batch.batch_fields.LGCY Batch Name" in [x.path for x in f.batch]
    assert "smiles|cxsmiles" in [x.path for x in f.molecule]


def test_unknown_vault_fields_shape_falls_back_to_built_ins() -> None:
    f = build_vault_fields({"molecule": "oops", "batch": [{"id": 3}]})
    assert f.molecule[0].path == "name"
    assert len(f.molecule) == 4 and len(f.batch) == 4
    assert len(build_vault_fields(["x"]).molecule) == 4
