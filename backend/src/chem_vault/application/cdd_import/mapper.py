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


def map_cdd_protocol(cdd_protocol: dict[str, Any]) -> CddProtocolMappingResult:
    """Map a single CDD protocol dict to a full mapping result with warnings."""
    warnings: list[MappingWarning] = []
    readouts: list[MappedReadout] = []
    conditions: list[MappedCondition] = []

    for idx, rd in enumerate(cdd_protocol.get("readout_definitions", [])):
        cdd_type = rd.get("type", "")
        rd_name = rd.get("name", f"Readout {idx + 1}")

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
                unit=rd.get("unit"),
                aggregation=ReadoutAggregation.NONE,
                normalization=ReadoutNormalization.NONE,
                precision=rd.get("precision"),
                pick_list_values=pick_list_values,
                dose_response_config=dr_config,
                display_order=idx,
            )
        )

    for cd in cdd_protocol.get("conditions", []):
        cd_type_str = cd.get("type", "Text")
        cd_type = _CDD_CONDITION_TYPE_MAP.get(cd_type_str, ConditionDataType.TEXT)
        conditions.append(
            MappedCondition(
                name=cd.get("name", "Condition"),
                data_type=cd_type,
                unit=cd.get("unit"),
                pick_list_values=cd.get("pick_list_values") if cd_type == ConditionDataType.PICK_LIST else None,
            )
        )

    return CddProtocolMappingResult(
        name=cdd_protocol.get("name", f"CDD Protocol {cdd_protocol['id']}"),
        readouts=readouts,
        conditions=conditions,
        warnings=warnings,
        cdd_source_id=cdd_protocol["id"],
    )
