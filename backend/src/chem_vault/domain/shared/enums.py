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


class AssignmentType(StrEnum):
    """Synthesis request assignment target."""

    INTERNAL = "internal"
    CRO = "cro"
