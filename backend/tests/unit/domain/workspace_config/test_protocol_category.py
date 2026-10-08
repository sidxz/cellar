import uuid

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.protocol_category import ProtocolCategory

WS = uuid.uuid4()


def test_create_uses_the_shipped_pattern():
    c = ProtocolCategory.create(workspace_id=WS, label="Cytotoxicity")
    assert c.name_pattern == "{cell_line} cytotoxicity" == c.default_pattern


def test_create_new_category_gets_the_generic_pattern():
    assert (
        ProtocolCategory.create(workspace_id=WS, label="Biofilm inhibition").name_pattern
        == "{subject?} biofilm inhibition"
    )


def test_update_validates_the_pattern():
    c = ProtocolCategory.create(workspace_id=WS, label="Cytotoxicity")
    with pytest.raises(ValidationError):
        c.update(name_pattern="{cellline} cytotoxicity")


@pytest.mark.parametrize("bad", ["", "  ", "Cyto · toxicity"])
def test_label_rules(bad):
    with pytest.raises(ValidationError):
        ProtocolCategory.create(workspace_id=WS, label=bad)


def test_events():
    c = ProtocolCategory.create(workspace_id=WS, label="Binding")
    assert [type(e).__name__ for e in c.collect_events()] == ["ProtocolCategoryCreated"]
