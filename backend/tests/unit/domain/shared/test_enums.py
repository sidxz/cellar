"""Tests for shared enums."""

from chem_vault.domain.shared.enums import (
    AmountUnit,
    AssignmentType,
    ConcentrationUnit,
    LightCondition,
    LinkedEntityType,
    Qualifier,
)


class TestAmountUnit:
    def test_values(self) -> None:
        assert set(AmountUnit) == {"mg", "g", "kg", "mL", "L", "umol"}

    def test_str_enum(self) -> None:
        assert str(AmountUnit.MG) == "mg"
        assert AmountUnit("mg") is AmountUnit.MG


class TestConcentrationUnit:
    def test_values(self) -> None:
        assert set(ConcentrationUnit) == {"mM", "uM", "nM", "mg/mL"}


class TestQualifier:
    def test_values(self) -> None:
        assert set(Qualifier) == {"=", "<", ">", "~", "<=", ">="}


class TestLightCondition:
    def test_values(self) -> None:
        assert set(LightCondition) == {"ambient", "protected", "exposed_ich"}


class TestLinkedEntityType:
    def test_all_types(self) -> None:
        assert len(LinkedEntityType) == 8
        assert "molecule" in set(LinkedEntityType)
        assert "formulation_batch" in set(LinkedEntityType)


class TestAssignmentType:
    def test_values(self) -> None:
        assert set(AssignmentType) == {"internal", "cro"}
