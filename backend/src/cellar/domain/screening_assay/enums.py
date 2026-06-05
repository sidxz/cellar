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
    DOSE_RESPONSE = "dose_response"
    BATCH_LINK = "batch_link"


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


def unit_for_normalization(normalization_applied: str | None, raw_unit: str | None) -> str | None:
    """Display unit for a value that came through a given normalization layer.

    Normalization formulas have well-defined output units that override the
    raw readout's unit (a "Raw Data" readout in nM still produces "%" after
    PERCENT_INHIBITION). Unknown / future formulas fall back to the raw unit
    so display stays reasonable without code changes. Returns ``None`` for
    the unitless Z-score formula.
    """
    if normalization_applied is None:
        return raw_unit
    try:
        formula = ReadoutNormalization(normalization_applied)
    except ValueError:
        return raw_unit
    if formula in (
        ReadoutNormalization.PERCENT_INHIBITION,
        ReadoutNormalization.PERCENT_ACTIVATION,
        ReadoutNormalization.PERCENT_CONTROL,
    ):
        return "%"
    if formula == ReadoutNormalization.Z_SCORE:
        return None
    return raw_unit


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


# PlateFormat is shared across screening and inventory — canonical definition
# lives in domain.shared.enums. Re-exported here for backwards compatibility.
from cellar.domain.shared.enums import PlateFormat as PlateFormat  # noqa: E402

# WellType is shared across screening and inventory — canonical definition
# lives in domain.shared.enums. Re-exported here for backwards compatibility.
from cellar.domain.shared.enums import WellType as WellType  # noqa: E402


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


class HillSlopeConstraint(StrEnum):
    """How the Hill slope parameter is constrained during curve fitting."""

    UNCONSTRAINED = "unconstrained"
    FIXED_AT_ONE = "fixed_at_one"
    POSITIVE_ONLY = "positive_only"
    NEGATIVE_ONLY = "negative_only"


class NormalizationScope(StrEnum):
    """Scope for control-based normalization of readout values."""

    PER_PLATE = "per_plate"
    PER_RUN = "per_run"
    NONE = "none"


class CurveType(StrEnum):
    """Type of dose-response curve measurement."""

    IC50 = "ic50"
    EC50 = "ec50"
    KI = "ki"
    KD = "kd"
    LD50 = "ld50"
    TD50 = "td50"


class InterceptKind(StrEnum):
    """Direction language for an intercept on a dose-response curve.

    - ``IC`` (Inhibition concentration): for decreasing curves; ``ICN`` is the
      concentration at which the response has dropped N% below the upper
      plateau toward the lower plateau (e.g. IC50 = halfway down).
    - ``EC`` (Effective concentration): for increasing curves; ``ECN`` is the
      concentration at which the response has risen N% above the lower
      plateau toward the upper plateau.

    Industry standard: CDD, GraphPad Prism, Genedata. Both kinds resolve to
    the same Hill inverse — only the direction of measurement differs.
    """

    IC = "ic"
    EC = "ec"


class InterceptBasis(StrEnum):
    """How an intercept's ``level`` is interpreted on the curve.

    - ``RELATIVE_PERCENT``: ``level`` is a percent (0..100) of the response
      window between bottom and top — CDD's "relative (%)" mode. IC50 = 50,
      IC90 = 90.
    - ``ABSOLUTE``: ``level`` is an absolute Y value the curve must cross.
    """

    RELATIVE_PERCENT = "relative_percent"
    ABSOLUTE = "absolute"


class CurveClass(StrEnum):
    """Shape classification of a dose-response curve."""

    FULL = "full"
    PARTIAL = "partial"
    BELL_SHAPED = "bell_shaped"
    INACTIVE = "inactive"


class PosControlSignal(StrEnum):
    """What raw signal the POSITIVE_CONTROL wells produce.

    Resolves the convention slip between two wet-lab labelings of "POS":

    - ``HIGH``: POS = uninhibited / DMSO / max-activity reference (signal is
      high when there is no inhibitor). Standard convention for the
      built-in % Inhibition / % Activation formulas.
    - ``LOW``: POS = known-inhibitor / no-enzyme / blank reference (signal
      is low because the readout is suppressed). When set, the normalizer
      and Z' calculator swap POS/NEG roles in the formula inputs so the
      math reads correctly with the lab's convention.
    """

    HIGH = "high"
    LOW = "low"
