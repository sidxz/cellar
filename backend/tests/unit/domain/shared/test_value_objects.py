"""Tests for all shared value objects — invariants, equality, frozen."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cellar.domain.shared.enums import (
    AmountUnit,
    AssignmentType,
    ConcentrationUnit,
    LightCondition,
)
from cellar.domain.shared.value_objects import (
    Amount,
    Barcode,
    BatchNumber,
    ChemicalStructure,
    Concentration,
    ComputedDescriptors,
    FormulationNumber,
    PredictedProperties,
    ReactionConditions,
    ReactionOutcome,
    RegistrationNumber,
    StorageCondition,
    SynthesisAssignment,
)


# ---------------------------------------------------------------------------
# ChemicalStructure
# ---------------------------------------------------------------------------


class TestChemicalStructure:
    _VALID = {
        "smiles": "c1ccccc1",
        "cxsmiles": "c1ccccc1",
        "inchi": "InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H",
        "inchi_key": "UHOVQNZJYSORNB-UHFFFAOYSA-N",
        "molfile": "\n  RDKit  2D\n\n",
    }

    def test_all_populated(self) -> None:
        cs = ChemicalStructure(**self._VALID)
        assert cs.is_disclosed is True

    def test_all_null(self) -> None:
        cs = ChemicalStructure()
        assert cs.is_disclosed is False

    def test_partial_raises(self) -> None:
        with pytest.raises(ValidationError, match="all-null or all-populated"):
            ChemicalStructure(smiles="C")

    def test_invalid_inchi_key(self) -> None:
        data = {**self._VALID, "inchi_key": "INVALID"}
        with pytest.raises(ValidationError, match="InChIKey"):
            ChemicalStructure(**data)

    def test_equality_by_inchi_key(self) -> None:
        a = ChemicalStructure(**self._VALID)
        b = ChemicalStructure(**{**self._VALID, "smiles": "C1=CC=CC=C1"})
        assert a == b

    def test_null_structures_equal(self) -> None:
        assert ChemicalStructure() == ChemicalStructure()

    def test_hash_by_inchi_key(self) -> None:
        a = ChemicalStructure(**self._VALID)
        b = ChemicalStructure(**self._VALID)
        assert hash(a) == hash(b)

    def test_frozen(self) -> None:
        cs = ChemicalStructure(**self._VALID)
        with pytest.raises(ValidationError):
            cs.smiles = "CC"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ComputedDescriptors
# ---------------------------------------------------------------------------

_FULL_DESCRIPTORS = {
    "molecular_formula": "C9H8O4",
    "molecular_weight": 180.16,
    "exact_mass": 180.042,
    "logp": 1.2,
    "tpsa": 63.6,
    "hbd": 1,
    "hba": 4,
    "rotatable_bonds": 3,
    "aromatic_rings": 1,
    "ring_count": 1,
    "heavy_atom_count": 13,
    "ro5_violations": 0,
}


class TestComputedDescriptors:
    def test_all_populated(self) -> None:
        cd = ComputedDescriptors(**_FULL_DESCRIPTORS)
        assert cd.molecular_weight == 180.16

    def test_all_null(self) -> None:
        ComputedDescriptors()

    def test_partial_raises(self) -> None:
        with pytest.raises(ValidationError, match="all-null or all-populated"):
            ComputedDescriptors(molecular_weight=100.0)

    def test_negative_mw_raises(self) -> None:
        with pytest.raises(ValidationError, match="positive"):
            ComputedDescriptors(**{**_FULL_DESCRIPTORS, "molecular_weight": -1.0})

    def test_ro5_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="ro5_violations"):
            ComputedDescriptors(**{**_FULL_DESCRIPTORS, "ro5_violations": 5})

    def test_negative_count_raises(self) -> None:
        with pytest.raises(ValidationError, match="non-negative"):
            ComputedDescriptors(**{**_FULL_DESCRIPTORS, "hbd": -1})


# ---------------------------------------------------------------------------
# PredictedProperties
# ---------------------------------------------------------------------------


class TestPredictedProperties:
    def test_all_null(self) -> None:
        PredictedProperties()

    def test_partial_ok(self) -> None:
        pp = PredictedProperties(logd=2.5)
        assert pp.logd == 2.5
        assert pp.pka is None

    def test_source_without_property_raises(self) -> None:
        with pytest.raises(ValidationError, match="prediction_source requires"):
            PredictedProperties(prediction_source="ChemAxon 24.3")

    def test_source_with_property_ok(self) -> None:
        pp = PredictedProperties(
            logd=2.5,
            prediction_source="ChemAxon 24.3",
            predicted_at=datetime.now(UTC),
        )
        assert pp.prediction_source == "ChemAxon 24.3"


# ---------------------------------------------------------------------------
# Registration / identification VOs
# ---------------------------------------------------------------------------


class TestRegistrationNumber:
    def test_valid(self) -> None:
        assert RegistrationNumber(value="CV-00001").value == "CV-00001"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            RegistrationNumber(value="  ")


class TestBatchNumber:
    def test_valid(self) -> None:
        assert BatchNumber(value="CV-00001-001").value == "CV-00001-001"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            BatchNumber(value="")


class TestBarcode:
    def test_valid(self) -> None:
        assert Barcode(value="BC-12345").value == "BC-12345"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            Barcode(value="  ")


class TestFormulationNumber:
    def test_valid(self) -> None:
        assert FormulationNumber(value="FRM-00001").value == "FRM-00001"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            FormulationNumber(value="")


# ---------------------------------------------------------------------------
# Measurement VOs
# ---------------------------------------------------------------------------


class TestAmount:
    def test_valid(self) -> None:
        a = Amount(value=10.5, unit=AmountUnit.MG)
        assert a.value == 10.5
        assert a.unit == AmountUnit.MG

    def test_zero_ok(self) -> None:
        Amount(value=0.0, unit=AmountUnit.G)

    def test_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match=">= 0"):
            Amount(value=-1.0, unit=AmountUnit.MG)

    def test_frozen(self) -> None:
        a = Amount(value=10.0, unit=AmountUnit.MG)
        with pytest.raises(ValidationError):
            a.value = 20.0  # type: ignore[misc]


class TestConcentration:
    def test_valid(self) -> None:
        c = Concentration(value=1.5, unit=ConcentrationUnit.UM)
        assert c.value == 1.5

    def test_zero_raises(self) -> None:
        with pytest.raises(ValidationError, match="> 0"):
            Concentration(value=0.0, unit=ConcentrationUnit.NM)

    def test_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="> 0"):
            Concentration(value=-1.0, unit=ConcentrationUnit.MM)



# ---------------------------------------------------------------------------
# Synthesis VOs
# ---------------------------------------------------------------------------


class TestReactionConditions:
    def test_valid(self) -> None:
        rc = ReactionConditions(solvent="THF", temperature="80C")
        assert rc.solvent == "THF"

    def test_all_null_raises(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            ReactionConditions()

    def test_additional_conditions_only(self) -> None:
        rc = ReactionConditions(additional_conditions={"pH": 7.0})
        assert rc.additional_conditions == {"pH": 7.0}


class TestReactionOutcome:
    def test_valid(self) -> None:
        ro = ReactionOutcome(yield_percent=85.0, purity_percent=99.0)
        assert ro.yield_percent == 85.0

    def test_yield_zero_raises(self) -> None:
        with pytest.raises(ValidationError, match="\\(0, 100\\]"):
            ReactionOutcome(yield_percent=0.0)

    def test_yield_over_100_raises(self) -> None:
        with pytest.raises(ValidationError, match="\\(0, 100\\]"):
            ReactionOutcome(yield_percent=101.0)

    def test_with_actual_scale(self) -> None:
        ro = ReactionOutcome(
            yield_percent=90.0,
            actual_scale=Amount(value=5.0, unit=AmountUnit.G),
        )
        assert ro.actual_scale is not None
        assert ro.actual_scale.value == 5.0


class TestSynthesisAssignment:
    def test_internal(self) -> None:
        user_id = uuid.uuid4()
        sa = SynthesisAssignment(
            assignment_type=AssignmentType.INTERNAL,
            assigned_to=user_id,
        )
        assert sa.assigned_to == user_id

    def test_cro(self) -> None:
        org_id = uuid.uuid4()
        sa = SynthesisAssignment(
            assignment_type=AssignmentType.CRO,
            assigned_org_id=org_id,
        )
        assert sa.assigned_org_id == org_id

    def test_internal_without_user_raises(self) -> None:
        with pytest.raises(ValidationError, match="assigned_to"):
            SynthesisAssignment(assignment_type=AssignmentType.INTERNAL)

    def test_cro_without_org_raises(self) -> None:
        with pytest.raises(ValidationError, match="assigned_org_id"):
            SynthesisAssignment(assignment_type=AssignmentType.CRO)


# ---------------------------------------------------------------------------
# Cross-context VOs
# ---------------------------------------------------------------------------



class TestStorageCondition:
    def test_valid(self) -> None:
        sc = StorageCondition(temperature_celsius=25.0, relative_humidity_percent=60.0)
        assert sc.temperature_celsius == 25.0

    def test_humidity_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="\\[0, 100\\]"):
            StorageCondition(temperature_celsius=25.0, relative_humidity_percent=101.0)

    def test_light_condition(self) -> None:
        sc = StorageCondition(
            temperature_celsius=40.0,
            light_condition=LightCondition.PROTECTED,
        )
        assert sc.light_condition == LightCondition.PROTECTED

    def test_temperature_only(self) -> None:
        sc = StorageCondition(temperature_celsius=5.0)
        assert sc.relative_humidity_percent is None


class TestConcentrationUnitMicromolarFactor:
    def test_molar_units_have_constant_factor(self) -> None:
        from cellar.domain.shared.enums import ConcentrationUnit

        assert ConcentrationUnit.MM.micromolar_factor == 1000.0
        assert ConcentrationUnit.UM.micromolar_factor == 1.0
        assert ConcentrationUnit.NM.micromolar_factor == 0.001

    def test_mass_unit_needs_molecular_weight(self) -> None:
        from cellar.domain.shared.enums import ConcentrationUnit

        assert ConcentrationUnit.MG_ML.micromolar_factor is None

    def test_every_member_is_classified(self) -> None:
        """Adding a unit without deciding its conversion must fail loudly."""
        from cellar.domain.shared.enums import ConcentrationUnit

        for u in ConcentrationUnit:
            u.micromolar_factor  # noqa: B018 — raises if unmapped
