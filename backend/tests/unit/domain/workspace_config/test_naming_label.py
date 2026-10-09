import uuid

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.naming_label import NamingLabel

MTB = "http://purl.bioontology.org/ontology/NCBITAXON/1773"


def _label(short="Mtb"):
    return NamingLabel.create(
        workspace_id=uuid.uuid4(), term_id=MTB, term_label="Mycobacterium tuberculosis",
        ontology_source="NCBITAXON", short_label=short,
    )


def test_create_and_update():
    label = _label()
    label.update(short_label="  M.  tb ")
    assert label.short_label == "M. tb"


@pytest.mark.parametrize("bad", ["", "  ", "Mtb · H37Rv", "x" * 61])
def test_short_label_rules(bad):
    with pytest.raises(ValidationError):
        _label(short=bad)
