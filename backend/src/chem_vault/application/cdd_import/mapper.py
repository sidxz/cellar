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
    cdd_id: int
    name: str
    readout_count: int


@dataclass(frozen=True)
class MappingWarning:
    field_name: str
    cdd_type: str
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
    cdd_source_id: int


_CDD_READOUT_TYPE_MAP: dict[str, ReadoutDataType] = {
    "Number": ReadoutDataType.NUMERIC,
    "Text": ReadoutDataType.TEXT,
    "Pick List": ReadoutDataType.PICK_LIST,
    "Plot": ReadoutDataType.DOSE_RESPONSE,
    "Batch Link": ReadoutDataType.BATCH_LINK,
    "File": ReadoutDataType.FILE,
    "Date": ReadoutDataType.DATE,
}

_CDD_CONDITION_TYPE_MAP: dict[str, ConditionDataType] = {
    "Number": ConditionDataType.NUMERIC,
    "Text": ConditionDataType.TEXT,
    "Pick List": ConditionDataType.PICK_LIST,
}


def map_cdd_protocol_list(cdd_protocols: list[dict[str, Any]]) -> list[CddProtocolSummary]:
    """Map a list of raw CDD protocol dicts to summary DTOs."""
    return [
        CddProtocolSummary(
            cdd_id=p["id"],
            name=p.get("name", f"Protocol {p['id']}"),
            readout_count=len(p.get("readout_definitions", [])),
        )
        for p in cdd_protocols
    ]


def _collect_calculated_readout_ids(calculations: list[dict[str, Any]]) -> set[int]:
    """Extract all auto-generated readout_definition IDs from CDD calculations.

    CDD dose-response and percent inhibition calculations produce output
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


def map_cdd_protocol(cdd_protocol: dict[str, Any]) -> CddProtocolMappingResult:
    """Map a single CDD protocol dict to a full mapping result with warnings."""
    warnings: list[MappingWarning] = []
    readouts: list[MappedReadout] = []
    conditions: list[MappedCondition] = []

    # Collect IDs of auto-generated calculation outputs so we skip them
    calculated_ids = _collect_calculated_readout_ids(
        cdd_protocol.get("calculations", [])
    )

    # CDD readout_definitions includes both readouts and conditions.
    # Conditions have "protocol_condition": true.
    # CDD field names: "data_type" (not "type"), "unit_label" (not "unit"),
    # "precision_number" (not "precision").
    readout_idx = 0
    for rd in cdd_protocol.get("readout_definitions", []):
        # Skip auto-generated calculation outputs (Hill slope, R², CI, etc.)
        rd_id = rd.get("id")
        if rd_id and rd_id in calculated_ids:
            continue

        rd_name = rd.get("name", f"Readout {readout_idx + 1}")

        # CDD marks conditions with protocol_condition flag
        if rd.get("protocol_condition", False):
            cdd_type_str = rd.get("data_type", "Text")
            cd_type = _CDD_CONDITION_TYPE_MAP.get(cdd_type_str, ConditionDataType.TEXT)
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
        cdd_type = rd.get("data_type") or rd.get("type") or ""
        mapped_type = _CDD_READOUT_TYPE_MAP.get(cdd_type)
        if mapped_type is None:
            warnings.append(
                MappingWarning(
                    field_name=rd_name,
                    cdd_type=cdd_type,
                    reason=f"Unknown CDD readout type '{cdd_type}' — skipped",
                )
            )
            continue

        dr_config: DoseResponseConfig | None = None
        if mapped_type == ReadoutDataType.DOSE_RESPONSE:
            dr_config = DoseResponseConfig(
                curve_type=CurveType.IC50,
                x_readout_name=rd.get("x_readout_name", "Concentration"),
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
                        cdd_type=cdd_type,
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

    # CDD stores description and category in protocol_fields
    pf = cdd_protocol.get("protocol_fields") or {}
    description = pf.get("Description") or cdd_protocol.get("description")
    category = pf.get("Category") or cdd_protocol.get("category")

    return CddProtocolMappingResult(
        name=cdd_protocol.get("name", f"CDD Protocol {cdd_protocol['id']}"),
        description=description or None,
        category=category or None,
        readouts=readouts,
        conditions=conditions,
        warnings=warnings,
        cdd_source_id=cdd_protocol["id"],
    )
