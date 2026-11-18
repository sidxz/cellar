import pytest

from cellar.domain.research_organization.measurement_facts import (
    TEST_CONCENTRATION,
    Concentration,
    parse_concentration,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("10 µM", Concentration(10, "µM")),
        ("10 uM", Concentration(10, "µM")),
        ("500 nM", Concentration(500, "nM")),
        ("0.01 mM", Concentration(0.01, "mM")),
        (10, Concentration(10, "µM")),
        ("10", Concentration(10, "µM")),
        ({"value": 5, "unit": "nM"}, Concentration(5, "nM")),
    ],
)
def test_parse_accepted_forms(raw, expected):
    assert parse_concentration(raw) == expected


@pytest.mark.parametrize("raw", ["10 um", "ATP", "10 mg/mL", None, True, {"value": "x"}, ""])
def test_parse_rejects(raw):
    assert parse_concentration(raw) is None


def test_bare_number_uses_default_unit():
    assert parse_concentration(3, "nM") == Concentration(3, "nM")


def test_same_as_across_units():
    assert Concentration(1, "µM").same_as(Concentration(1000, "nM"))
    assert not Concentration(1, "µM").same_as(Concentration(2, "µM"))


def test_label_constant():
    assert TEST_CONCENTRATION == "Test concentration"
