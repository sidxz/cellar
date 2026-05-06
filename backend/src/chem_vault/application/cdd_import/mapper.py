"""Pure mapper: CDD Vault protocol JSON -> domain-ready DTOs.

No I/O. No domain imports except enums and VOs needed for type mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.enums import (
    ConditionDataType,
    CurveType,
    HillSlopeConstraint,
    NormalizationScope,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)

__all__ = [
    "CddProtocolSummary",
    "MappedReadout",
    "MappedCondition",
    "MappingWarning",
    "CddProtocolMappingResult",
    "map_cdd_protocol_list",
    "map_cdd_protocol",
]


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
    data_type: ReadoutDataType
    unit: str | None
    aggregation: ReadoutAggregation
    normalization: ReadoutNormalization
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
    "Batch Link": ReadoutDataType.BATCH_LINK,
    "File": ReadoutDataType.FILE,
    "Date": ReadoutDataType.DATE,
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

    We create one DOSE_RESPONSE readout per calculation, named after the primary
    intercept output (user-defined name like "IC50calc"), with X/Y axis names
    from the input readout definitions.
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
        dose_rd = rd_by_id.get(dose_id, {}) if dose_id else {}
        response_rd = rd_by_id.get(response_id, {}) if response_id else {}

        x_name = dose_rd.get("name", "Dose")
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
                data_type=ReadoutDataType.DOSE_RESPONSE,
                unit=dr_unit,
                aggregation=ReadoutAggregation.NONE,
                normalization=ReadoutNormalization.NONE,
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

        # Conditions are marked with protocol_condition flag
        if rd.get("protocol_condition", False):
            src_type_str = rd.get("data_type", "Text")
            cd_type = _CONDITION_TYPE_MAP.get(src_type_str, ConditionDataType.TEXT)
            conditions.append(
                MappedCondition(
                    name=rd_name,
                    data_type=cd_type,
                    unit=rd.get("unit_label"),
                    pick_list_values=rd.get("pick_list_values") if cd_type == ConditionDataType.PICK_LIST else None,
                )
            )
            continue

        # Regular readout — map the data_type
        src_type = rd.get("data_type") or rd.get("type") or ""
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
            dr_config = DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name=rd.get("x_readout_name"),
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

        readouts.append(
            MappedReadout(
                name=rd_name,
                data_type=mapped_type,
                unit=rd.get("unit_label") or rd.get("unit"),
                aggregation=ReadoutAggregation.NONE,
                normalization=ReadoutNormalization.NONE,
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
