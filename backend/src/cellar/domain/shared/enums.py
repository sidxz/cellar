"""Shared enums used across bounded contexts."""

from enum import StrEnum


class AmountUnit(StrEnum):
    """Units of material quantity."""

    MG = "mg"
    G = "g"
    KG = "kg"
    ML = "mL"
    L = "L"
    UMOL = "umol"


class ConcentrationUnit(StrEnum):
    """Units of solution concentration."""

    MM = "mM"
    UM = "uM"
    NM = "nM"
    MG_ML = "mg/mL"

    @property
    def micromolar_factor(self) -> float | None:
        """Multiply a value in this unit by the factor to get µM.

        ``None`` means the unit is mass-based and needs the compound's
        molecular weight (µM = mg/mL × 1e6 / MW). Every member must be
        classified here — a new unit without an entry raises at first use.
        """
        factors: dict[ConcentrationUnit, float | None] = {
            ConcentrationUnit.MM: 1000.0,
            ConcentrationUnit.UM: 1.0,
            ConcentrationUnit.NM: 0.001,
            ConcentrationUnit.MG_ML: None,
        }
        return factors[self]


class Qualifier(StrEnum):
    """Qualifiers for assay measurements."""

    EQUAL = "="
    LESS_THAN = "<"
    GREATER_THAN = ">"
    APPROXIMATE = "~"
    LESS_EQUAL = "<="
    GREATER_EQUAL = ">="


class LightCondition(StrEnum):
    """ICH-aligned light exposure conditions for stability studies."""

    AMBIENT = "ambient"
    PROTECTED = "protected"
    EXPOSED_ICH = "exposed_ich"


class LinkedEntityType(StrEnum):
    """Entity types that can be linked from ELN entries."""

    MOLECULE = "molecule"
    BATCH = "batch"
    PROTOCOL = "protocol"
    RUN = "run"
    SYNTHESIS_ROUTE = "synthesis_route"
    SYNTHESIS_REQUEST = "synthesis_request"
    FORMULATION = "formulation"
    FORMULATION_BATCH = "formulation_batch"


class PlateFormat(StrEnum):
    """Microplate well count — shared across screening and inventory contexts."""

    F6 = "6"
    F12 = "12"
    F24 = "24"
    F48 = "48"
    F96 = "96"
    F384 = "384"
    F1536 = "1536"


class WellType(StrEnum):
    """Role of a well on a plate — shared across screening and inventory contexts."""

    SAMPLE = "sample"
    POSITIVE_CONTROL = "positive_control"
    NEGATIVE_CONTROL = "negative_control"
    BLANK = "blank"
    REFERENCE = "reference"


class AssignmentType(StrEnum):
    """Synthesis request assignment target."""

    INTERNAL = "internal"
    CRO = "cro"
