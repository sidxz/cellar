"""Screening & Assay context enums."""

from enum import StrEnum


class ProtocolType(StrEnum):
    """Classification of experimental protocol."""

    BIOCHEMICAL = "biochemical"
    CELL_BASED = "cell_based"
    ADMET = "admet"
    IN_VIVO = "in_vivo"
    ANALYTICAL = "analytical"
    PHYSICOCHEMICAL = "physicochemical"


class ProtocolStatus(StrEnum):
    """Lifecycle status of a protocol."""

    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class ReadoutDataType(StrEnum):
    """Data type of a readout measurement."""

    NUMERIC = "numeric"
    TEXT = "text"
    PICK_LIST = "pick_list"
    FILE = "file"
    DATE = "date"


class ReadoutAggregation(StrEnum):
    """How replicate readout values are aggregated."""

    NONE = "none"
    MEAN = "mean"
    MEDIAN = "median"
    GEOMETRIC_MEAN = "geometric_mean"
    MIN = "min"
    MAX = "max"


class ReadoutNormalization(StrEnum):
    """Normalization method applied to readout values."""

    NONE = "none"
    PERCENT_INHIBITION = "percent_inhibition"
    PERCENT_ACTIVATION = "percent_activation"
    PERCENT_CONTROL = "percent_control"
    Z_SCORE = "z_score"


class ConditionDataType(StrEnum):
    """Data type of a condition variable."""

    NUMERIC = "numeric"
    TEXT = "text"
    PICK_LIST = "pick_list"


class TargetType(StrEnum):
    """Classification of a biological target."""

    SINGLE_PROTEIN = "single_protein"
    PROTEIN_COMPLEX = "protein_complex"
    PROTEIN_FAMILY = "protein_family"
    NUCLEIC_ACID = "nucleic_acid"
    ORGANISM = "organism"
    CELL_LINE = "cell_line"
    TISSUE = "tissue"


class PlateFormat(StrEnum):
    """Microplate well count."""

    F6 = "6"
    F12 = "12"
    F24 = "24"
    F48 = "48"
    F96 = "96"
    F384 = "384"
    F1536 = "1536"


class WellType(StrEnum):
    """Role of a well on a plate."""

    SAMPLE = "sample"
    POSITIVE_CONTROL = "positive_control"
    NEGATIVE_CONTROL = "negative_control"
    BLANK = "blank"
    REFERENCE = "reference"


class RunStatus(StrEnum):
    """Lifecycle status of an assay run."""

    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    APPROVED = "approved"
    REJECTED = "rejected"


class RunRelationshipType(StrEnum):
    """How a child run relates to its parent."""

    CONFIRMATION_OF = "confirmation_of"
    REPEAT_OF = "repeat_of"
    FOLLOW_UP_TO = "follow_up_to"


class CurveType(StrEnum):
    """Type of dose-response curve measurement."""

    IC50 = "ic50"
    EC50 = "ec50"
    KI = "ki"
    KD = "kd"
    LD50 = "ld50"
    TD50 = "td50"


class CurveClass(StrEnum):
    """Shape classification of a dose-response curve."""

    FULL = "full"
    PARTIAL = "partial"
    BELL_SHAPED = "bell_shaped"
    INACTIVE = "inactive"
