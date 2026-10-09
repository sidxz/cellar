"""Units are stored one way: spelling variants of the same unit collapse; nothing else changes."""

import uuid

import pytest

from cellar.domain.screening_assay.enums import ConditionDataType, ReadoutDataType
from cellar.domain.screening_assay.protocol import ConditionDefinition, ReadoutDefinition
from cellar.domain.shared.units import COMMON_UNITS, canonical_unit
from cellar.domain.workspace_config.protocol_form import (
    ProtocolFormCondition,
    ProtocolFormReadout,
)

MICRO = "µ"  # micro sign


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("uM", f"{MICRO}M"),
        ("μM", f"{MICRO}M"),  # Greek mu
        ("mcg/mL", f"{MICRO}g/mL"),
        ("ug/ml", f"{MICRO}g/mL"),
        ("uL/min/mg", f"{MICRO}L/min/mg"),
        ("ml", "mL"),
        ("dl", "dL"),
        ("umol/L", f"{MICRO}M"),
        ("nmol/L", "nM"),
        ("mol/L", "M"),
        ("mg/Kg", "mg/kg"),
        ("hr", "h"),
        ("Hours", "h"),
        ("mins", "min"),
        ("seconds", "s"),
        ("days", "d"),
        ("percent", "%"),
        ("deg C", "°C"),
        ("ng*h/mL", "ng·h/mL"),
        ("ng.h/mL", "ng·h/mL"),
        ("  µM  ", f"{MICRO}M"),
        ("ug.mL-1", f"{MICRO}g·mL-1"),
        ("ng.h.mL-1", "ng·h·mL-1"),
        ("10-6 cm/s", "×10⁻⁶ cm/s"),
        ("10^-6 cm/s", "×10⁻⁶ cm/s"),
        ("x10-6 cm/s", "×10⁻⁶ cm/s"),
        ("X 10^-6 cm/s", "×10⁻⁶ cm/s"),
        ("1e-6 cm/s", "×10⁻⁶ cm/s"),
        ("1E-6cm/sec", "×10⁻⁶ cm/s"),
    ],
)
def test_spelling_variants_collapse(raw, expected):
    assert canonical_unit(raw) == expected


@pytest.mark.parametrize(
    "unchanged",
    [
        "U/mL",
        "% remaining",
        "mm",
        "mM",
        "M",
        "mP",
        "log10 CFU",
        "RFU",
        "OD600",
        "mL/min/g liver",
        "fold",
        "Da",
        "1.5 h",
        "100 mL",
        "a.u.",  # dotted abbreviations are not products
        "A.U.",
        "O.D.",
        "um",  # µM in an assay, µm as a length: ambiguous, so left alone
        f"{MICRO}m",
    ],
)
def test_anything_else_is_left_as_typed(unchanged):
    assert canonical_unit(unchanged) == unchanged


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_is_none(blank):
    assert canonical_unit(blank) is None


def test_every_suggestion_is_already_canonical():
    for s in COMMON_UNITS:
        assert canonical_unit(s.unit) == s.unit


def test_readout_and_condition_definitions_store_the_canonical_spelling():
    pid = uuid.uuid4()
    rd = ReadoutDefinition(
        protocol_id=pid, name="IC50", data_type=ReadoutDataType.NUMERIC, unit="uM"
    )
    cd = ConditionDefinition(
        protocol_id=pid, name="Dose", data_type=ConditionDataType.NUMERIC, unit="mg/Kg"
    )
    assert rd.unit == f"{MICRO}M" and cd.unit == "mg/kg"


def test_form_templates_store_the_canonical_spelling():
    assert (
        ProtocolFormReadout(name="MIC", data_type="numeric", unit="ug/ml").unit == f"{MICRO}g/mL"
    )
    assert ProtocolFormCondition(name="Time", data_type="numeric", unit="hrs").unit == "h"
