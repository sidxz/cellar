"""ColumnSplit — how a search splits one protocol's columns into groups."""

import pytest

from cellar.domain.screening_assay.column_split import ColumnSplit
from cellar.domain.shared.errors import ValidationError


@pytest.mark.parametrize("raw", [None, {}, {"by": "none"}])
def test_absent_or_none_is_no_split(raw):
    split = ColumnSplit.from_wire(raw)
    assert split == ColumnSplit()
    assert split.is_split() is False


def test_by_run():
    split = ColumnSplit.from_wire({"by": "run"})
    assert split == ColumnSplit(by="run")
    assert split.is_split() is True


def test_by_condition_carries_trimmed_name():
    split = ColumnSplit.from_wire({"by": "condition", "condition": "  ATP Concentration "})
    assert split == ColumnSplit(by="condition", condition="ATP Concentration")


@pytest.mark.parametrize(
    "raw",
    [
        "run",
        {"by": "plate"},
        {"by": "condition"},
        {"by": "condition", "condition": "  "},
        {"by": "run", "condition": "ATP"},
    ],
)
def test_malformed_raises(raw):
    with pytest.raises(ValidationError):
        ColumnSplit.from_wire(raw)
