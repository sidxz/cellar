import uuid

import pytest

from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)
from cellar.domain.shared.errors import ValidationError


def test_create_requires_name():
    with pytest.raises(ValidationError):
        CollectionImportTemplate.create(
            workspace_id=uuid.uuid4(),
            name="",
            column_mapping={"name": "Compound Name"},
            created_by=uuid.uuid4(),
        )


def test_create_requires_at_least_one_identifier_role():
    with pytest.raises(ValidationError):
        CollectionImportTemplate.create(
            workspace_id=uuid.uuid4(),
            name="Partner ACME",
            column_mapping={"notes": "Comments"},
            created_by=uuid.uuid4(),
        )


def test_update_changes_mapping_and_bumps_updated_at():
    tpl = CollectionImportTemplate.create(
        workspace_id=uuid.uuid4(),
        name="t1",
        column_mapping={"name": "Compound Name"},
        created_by=uuid.uuid4(),
    )
    original_updated = tpl.updated_at
    tpl.update(column_mapping={"name": "Compound", "smiles": "Structure"})
    assert tpl.column_mapping["smiles"] == "Structure"
    assert tpl.updated_at >= original_updated
