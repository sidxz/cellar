"""Tests for holder vocabulary: row letters and position/holder labels."""

from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.holder import holder_label, position_label, row_letters


def test_row_letters():
    assert [row_letters(n) for n in (1, 2, 26, 27, 52)] == ["A", "B", "Z", "AA", "AZ"]


def test_position_label_by_holder_kind():
    assert position_label(HolderKind.CASSETTE, "A", 7) == "Capillary 7"
    assert position_label(HolderKind.CASSETTE, "A", 31) == "Capillary 31"
    assert position_label(HolderKind.PLATE, "B", 3) == "B3"


def test_holder_label():
    assert holder_label(HolderKind.CASSETTE, 1, 24) == "Cassette, 24 capillaries"
    assert holder_label(HolderKind.PLATE, 8, 12) == "Plate, 8 × 12"
    assert holder_label(HolderKind.PLATE, None, None) == "Plate"


def test_holder_label_without_a_size_is_the_holder_word_alone():
    assert holder_label(HolderKind.CASSETTE, None, None) == "Cassette"
