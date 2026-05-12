"""Pure mapper: CDD Vault protocol JSON -> domain-ready DTOs.

No I/O. No domain imports except enums and VOs needed for type mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    CurveType,
    HillSlopeConstraint,
    NormalizationScope,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import is_reserved_readout_name

__all__ = [
    "CddProtocolSummary",
    "MappedReadout",
    "MappedCondition",
    "MappingWarning",
    "CddProtocolMappingResult",
    "map_cdd_protocol_list",
    "map_cdd_protocol",
]


# CDD users frequently name a column "Concentration", "Dose", "Compound Conc",
# etc. and reference it as the X axis of an IC50 calculation. Chem-vault
# stores concentration on `wells.dose` (the experimental setpoint, not a
# measurement), so importing those columns as readouts would create dead
# readout-defs that never have data and break the IC50 fit's X-source
# contract. We detect them in two ways:
#   1. Their name matches a cellar reserved well-metadata name
#      (canonical set lives in domain.screening_assay.protocol —
#      `is_reserved_readout_name`).
#   2. They're referenced as the X (dose) readout of a CDD dose-response
#      calculation, regardless of name.
# Skipped readouts produce a `MappingWarning` so the chemist sees them in
# the import preview, and any DR config that pointed at one gets
# `x_readout_name=None` (= use well.dose implicitly).


def _collect_dose_readout_names(
    protocol_data: dict[str, Any],
    rd_by_id: dict[int, dict[str, Any]],
) -> set[str]:
    """Return names of readouts that are 'the dose column' for any DR config.

    CDD has two ways of declaring a dose-response: a `Plot` readout with
    `x_readout_name`, or a `class: dose response calculation` with an
    input `dose_readout_definition` (an int ID).
    """
    names: set[str] = set()
    for rd in protocol_data.get("readout_definitions", []):
        if rd.get("data_type") == "Plot":
            x = rd.get("x_readout_name")
            if x:
                names.add(x)
    for calc in protocol_data.get("calculations", []) or []:
        if calc.get("class") != "dose response calculation":
            continue
        inputs = calc.get("inputs", {}) or {}
        dose_id = inputs.get("dose_readout_definition")
        if isinstance(dose_id, int):
            dose_rd = rd_by_id.get(dose_id, {})
            n = dose_rd.get("name")
            if n:
                names.add(n)
    return names


@dataclass(frozen=True)
class CddProtocolSummary:
    external_id: int
    name: str
    readout_count: int


@dataclass(frozen=True)
class MappingWarning:
    field_name: str
    source_type: str
    reason: str


@dataclass(frozen=True)
class MappedReadout:
    name: str
    description: str | None
    data_type: ReadoutDataType
    unit: str | None
    aggregation: ReadoutAggregation
    # Plural for parity with the domain model and the API response surface.
    # CDD's protocol JSON typically declares a single (or zero) normalization
    # per readout, but a frozenset preserves room for multi-emit readouts
    # without another schema migration on the import side.
    normalizations: frozenset[ReadoutNormalization]
    precision: int | None
    pick_list_values: list[str] | None
    dose_response_config: DoseResponseConfig | None
    display_order: int


@dataclass(frozen=True)
class MappedCondition:
    name: str
    data_type: ConditionDataType
    unit: str | None
    pick_list_values: list[str] | None


@dataclass(frozen=True)
class CddProtocolMappingResult:
    name: str
    description: str | None
    category: str | None
    readouts: list[MappedReadout]
    conditions: list[MappedCondition]
    warnings: list[MappingWarning]
    external_source_id: int


_READOUT_TYPE_MAP: dict[str, ReadoutDataType] = {
    "Number": ReadoutDataType.NUMERIC,
    "Text": ReadoutDataType.TEXT,
    "Pick List": ReadoutDataType.PICK_LIST,
    "Plot": ReadoutDataType.DOSE_RESPONSE,
}

# CDD-only readout types that don't fit cellar's model — surfaced as
# warnings + dropped on import. Rationale per the design audit:
#   - "File": cellar models attachments at the run / molecule level,
#     not per-readout-cell. Per-data-point file attachment is a Phase-3
#     feature requiring a real lifecycle (upload, ZIP-bulk match, etc.).
#   - "Date": run.run_date is the canonical "when measured." Per-readout
#     dates are time-course territory, which needs a richer model than
#     a single column.
#   - "Batch Link": well.batch_id is canonical. A Batch Link readout
#     would duplicate it.
_DROPPED_READOUT_TYPES: dict[str, str] = {
    "File": (
        "'File' readout type isn't supported in cellar — files attach "
        "to the run, not to individual data points. Skipped."
    ),
    "Date": (
        "'Date' readout type isn't supported — cellar uses "
        "run.run_date for measurement timing. Skipped."
    ),
    "Batch Link": (
        "'Batch Link' readout type isn't supported — cellar stores "
        "the batch reference on the well (well.batch_id). Skipped."
    ),
}

_CONDITION_TYPE_MAP: dict[str, ConditionDataType] = {
    "Number": ConditionDataType.NUMERIC,
    "Text": ConditionDataType.TEXT,
    "Pick List": ConditionDataType.PICK_LIST,
}


def map_cdd_protocol_list(protocols: list[dict[str, Any]]) -> list[CddProtocolSummary]:
    """Map a list of raw CDD protocol dicts to summary DTOs."""
    return [
        CddProtocolSummary(
            external_id=p["id"],
            name=p.get("name", f"Protocol {p['id']}"),
            readout_count=len(p.get("readout_definitions", [])),
        )
        for p in protocols
    ]


def _collect_calculated_readout_ids(calculations: list[dict[str, Any]]) -> set[int]:
    """Extract all auto-generated readout_definition IDs from calculations.

    Dose-response and percent inhibition calculations produce output
    readout definitions (Hill slope, R squared, CI bounds, etc.) that appear
    in the flat readout_definitions list but are not user-defined readouts.
    """
    ids: set[int] = set()

    def _collect(obj: Any) -> None:
        if isinstance(obj, int):
            ids.add(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect(v)
        elif isinstance(obj, list):
            for item in obj:
                _collect(item)

    for calc in calculations:
        outputs = calc.get("outputs", {})
        _collect(outputs)

    return ids


# CDD's normalization-style calculations live as separate `calculations`
# entries that point at an input readout and emit one or more output
# readouts. Chem-vault's model collapses this into a single ReadoutDefinition
# whose `normalizations` set declares which formula layers it emits — the
# calc engine produces them at runtime. Map CDD's calculation classes onto
# our normalization vocabulary so an imported protocol declares the same
# computed layers the source vault was producing.
#
# Calc classes NOT listed here (notably "dose response calculation") are
# handled by their own dedicated synthesis path and ignored here.
_NORMALIZATION_CALC_CLASSES: dict[str, ReadoutNormalization] = {
    "percent inhibition calculation": ReadoutNormalization.PERCENT_INHIBITION,
    "percent activation calculation": ReadoutNormalization.PERCENT_ACTIVATION,
    "percent control calculation": ReadoutNormalization.PERCENT_CONTROL,
    "z score calculation": ReadoutNormalization.Z_SCORE,
}


def _collect_normalizations_by_input_id(
    calculations: list[dict[str, Any]],
) -> dict[int, set[ReadoutNormalization]]:
    """Map input readout id → set of normalizations CDD computes from it.

    For each normalization-style calculation, look up its
    ``inputs.input_readout_definition`` and bucket its calc-class
    normalization under that input readout's id. The main loop reads this
    map when emitting MappedReadout so the imported readout declares the
    same computed layers CDD was producing.
    """
    by_input: dict[int, set[ReadoutNormalization]] = {}
    for calc in calculations:
        norm = _NORMALIZATION_CALC_CLASSES.get(calc.get("class") or "")
        if norm is None:
            continue
        inputs = calc.get("inputs", {}) or {}
        input_id = inputs.get("input_readout_definition")
        if not isinstance(input_id, int):
            continue
        by_input.setdefault(input_id, set()).add(norm)
    return by_input


def _build_dose_response_readouts(
    calculations: list[dict[str, Any]],
    rd_by_id: dict[int, dict[str, Any]],
    start_order: int,
) -> list[MappedReadout]:
    """Synthesize DOSE_RESPONSE readouts from dose-response calculations.

    CDD Vault represents dose-response curves as calculations
    (not readout data types). Each dose-response calculation has:
      - inputs: dose_readout_definition (X axis), response_readout_definition (Y axis)
      - outputs: intercept_readout_definitions (primary IC50/EC50 value + CI bounds + stats)

    We emit one DOSE_RESPONSE readout per calculation, named after the
    primary intercept output (e.g. "IC50calc"). The Y axis is the response
    readout name. The X axis is always `None` — cellar stores doses on
    `well.dose` (per protocol-design contract), so the 4PL fitter sources X
    from the well, not from a separate dose readout.
    """
    dr_readouts: list[MappedReadout] = []
    order = start_order

    for calc in calculations:
        if calc.get("class") != "dose response calculation":
            continue

        inputs = calc.get("inputs", {})
        outputs = calc.get("outputs", {})

        # Resolve input readout names
        dose_id = inputs.get("dose_readout_definition")
        response_id = inputs.get("response_readout_definition")
        response_rd = rd_by_id.get(response_id, {}) if response_id else {}

        # CDD's dose readout (referenced by `dose_id`) is the dose column —
        # cellar stores that on `well.dose`, so x_readout_name=None
        # tells the 4PL fitter to source X from the well implicitly. The
        # main loop will already have skipped this readout from the
        # protocol's readout list.
        _ = dose_id  # intentionally unused — the well owns the X axis
        x_name = None
        y_name = response_rd.get("name", "Response")

        # Primary output name + unit from the intercept readout definition
        intercept_defs = outputs.get("intercept_readout_definitions", [])
        intercept_id: int | None = None
        if intercept_defs and isinstance(intercept_defs[0], list) and intercept_defs[0]:
            intercept_id = intercept_defs[0][0] if isinstance(intercept_defs[0][0], int) else None

        intercept_rd = rd_by_id.get(intercept_id, {}) if intercept_id else {}
        dr_name = intercept_rd.get("name", "Dose Response")
        dr_unit = intercept_rd.get("unit_label")

        dr_readouts.append(
            MappedReadout(
                name=dr_name,
                description=intercept_rd.get("description"),
                data_type=ReadoutDataType.DOSE_RESPONSE,
                unit=dr_unit,
                aggregation=ReadoutAggregation.NONE,
                normalizations=frozenset(),
                precision=None,
                pick_list_values=None,
                dose_response_config=DoseResponseConfig(
                    curve_type=CurveType.IC50,
                    x_readout_name=x_name,
                    y_readout_name=y_name,
                    hill_slope_constraint=HillSlopeConstraint.UNCONSTRAINED,
                    normalization_scope=NormalizationScope.PER_PLATE,
                ),
                display_order=order,
            )
        )
        order += 1

    return dr_readouts


def map_cdd_protocol(protocol_data: dict[str, Any]) -> CddProtocolMappingResult:
    """Map a single CDD protocol dict to a full mapping result with warnings."""
    warnings: list[MappingWarning] = []
    readouts: list[MappedReadout] = []
    conditions: list[MappedCondition] = []

    calculations = protocol_data.get("calculations", [])

    # Collect IDs of auto-generated calculation outputs so we skip them
    calculated_ids = _collect_calculated_readout_ids(calculations)

    # Build ID->readout lookup for resolving calculation input/output names
    rd_by_id: dict[int, dict[str, Any]] = {
        rd["id"]: rd for rd in protocol_data.get("readout_definitions", []) if "id" in rd
    }

    # Names of readouts that are dose columns for any DR config — skipped
    # below and used to null `x_readout_name` on emitted DR configs so the
    # 4PL fitter reads X from `well.dose` implicitly.
    dose_referenced_names = _collect_dose_readout_names(protocol_data, rd_by_id)

    # CDD calculation outputs (e.g. "Raw Data % inhibition") are skipped
    # via `calculated_ids`, but the *normalization formula* they represent
    # must be lifted onto their input readout — otherwise an imported
    # protocol forgets which computed layers CDD was producing and the
    # screen runs without them.
    normalizations_by_input_id = _collect_normalizations_by_input_id(calculations)

    # readout_definitions includes both readouts and conditions.
    # Conditions have "protocol_condition": true.
    # Field names: "data_type" (not "type"), "unit_label" (not "unit"),
    # "precision_number" (not "precision").
    readout_idx = 0
    for rd in protocol_data.get("readout_definitions", []):
        # Skip auto-generated calculation outputs (Hill slope, R-squared, CI, etc.)
        rd_id = rd.get("id")
        if rd_id and rd_id in calculated_ids:
            continue

        rd_name = rd.get("name", f"Readout {readout_idx + 1}")

        # Skip dose-column readouts (named-reserved or referenced as DR X axis).
        # Concentration is well metadata, not a measurement — modeling it as a
        # readout def would produce em-dash-only columns and a broken fit.
        if is_reserved_readout_name(rd_name) or rd_name in dose_referenced_names:
            warnings.append(
                MappingWarning(
                    field_name=rd_name,
                    source_type=rd.get("data_type", "") or "",
                    reason=(
                        f"'{rd_name}' is a dose/concentration column — "
                        "cellar stores well concentrations on the well "
                        "itself (well.dose + protocol.dose_unit), not as a "
                        "readout. Skipped; IC50 fits read X from well.dose."
                    ),
                )
            )
            continue

        # Conditions are marked with protocol_condition flag
        if rd.get("protocol_condition", False):
            src_type_str = rd.get("data_type", "Text")
            cd_type = _CONDITION_TYPE_MAP.get(src_type_str, ConditionDataType.TEXT)
            conditions.append(
                MappedCondition(
                    name=rd_name,
                    data_type=cd_type,
                    unit=rd.get("unit_label"),
                    pick_list_values=rd.get("pick_list_values")
                    if cd_type == ConditionDataType.PICK_LIST
                    else None,
                )
            )
            continue

        # Regular readout — map the data_type
        src_type = rd.get("data_type") or rd.get("type") or ""

        # CDD types we explicitly don't support — drop with a clear
        # explanation so the chemist sees what was filtered.
        if src_type in _DROPPED_READOUT_TYPES:
            warnings.append(
                MappingWarning(
                    field_name=rd_name,
                    source_type=src_type,
                    reason=_DROPPED_READOUT_TYPES[src_type],
                )
            )
            continue

        mapped_type = _READOUT_TYPE_MAP.get(src_type)
        if mapped_type is None:
            warnings.append(
                MappingWarning(
                    field_name=rd_name,
                    source_type=src_type,
                    reason=f"Unknown readout type '{src_type}' — skipped",
                )
            )
            continue

        dr_config: DoseResponseConfig | None = None
        if mapped_type == ReadoutDataType.DOSE_RESPONSE:
            x_name = rd.get("x_readout_name")
            # If CDD's X readout was a dose column (which we just skipped),
            # null it out so the fitter uses well.dose implicitly.
            if x_name and (x_name in dose_referenced_names or is_reserved_readout_name(x_name)):
                x_name = None
            dr_config = DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name=x_name,
                y_readout_name=rd.get("y_readout_name", rd_name),
                hill_slope_constraint=HillSlopeConstraint.UNCONSTRAINED,
                normalization_scope=NormalizationScope.PER_PLATE,
            )

        pick_list_values: list[str] | None = None
        if mapped_type == ReadoutDataType.PICK_LIST:
            pick_list_values = rd.get("pick_list_values") or rd.get("options") or []
            if not pick_list_values:
                warnings.append(
                    MappingWarning(
                        field_name=rd_name,
                        source_type=src_type,
                        reason="Pick list type but no values found — using empty list",
                    )
                )
                pick_list_values = ["(empty)"]

        # Pick up any normalization-style calculations that point at this
        # readout as their input. CDD models these as separate output rows;
        # cellar collapses them into a normalizations set on the input.
        lifted_norms = (
            frozenset(normalizations_by_input_id.get(rd_id, set()))
            if rd_id is not None
            else frozenset()
        )

        readouts.append(
            MappedReadout(
                name=rd_name,
                description=rd.get("description"),
                data_type=mapped_type,
                unit=rd.get("unit_label") or rd.get("unit"),
                aggregation=ReadoutAggregation.NONE,
                normalizations=lifted_norms,
                precision=rd.get("precision_number") or rd.get("precision"),
                pick_list_values=pick_list_values,
                dose_response_config=dr_config,
                display_order=readout_idx,
            )
        )
        readout_idx += 1

    # Synthesize DOSE_RESPONSE readouts from dose-response calculations
    dr_readouts = _build_dose_response_readouts(calculations, rd_by_id, readout_idx)
    readouts.extend(dr_readouts)

    # Description and category stored in protocol_fields
    pf = protocol_data.get("protocol_fields") or {}
    description = pf.get("Description") or protocol_data.get("description")
    category = pf.get("Category") or protocol_data.get("category")

    return CddProtocolMappingResult(
        name=protocol_data.get("name", f"Protocol {protocol_data['id']}"),
        description=description or None,
        category=category or None,
        readouts=readouts,
        conditions=conditions,
        warnings=warnings,
        external_source_id=protocol_data["id"],
    )
