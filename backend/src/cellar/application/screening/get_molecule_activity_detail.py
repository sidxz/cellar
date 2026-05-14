"""GetMoleculeActivityDetail — all DR curves for a molecule, grouped by protocol.

Powers the compound detail side panel in the search UI: when a user clicks a
compound in search results, the frontend calls this endpoint to render
interactive Plotly charts of every dose-response curve for that molecule.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.screening import _condense_raw_data
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
)
from cellar.domain.shared.errors import DomainError

# ---------------------------------------------------------------------------
# Query DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetMoleculeActivityDetailQuery(Query):
    workspace_id: uuid.UUID
    molecule_id: uuid.UUID


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InterceptSpecPayload:
    """Wire form of InterceptSpec for the activity-detail response."""

    kind: str  # "ic" | "ec"
    level: float
    basis: str  # "relative_percent" | "absolute"
    label: str | None


@dataclass(frozen=True)
class InterceptValuePayload:
    """Wire form of InterceptValue for the activity-detail response."""

    spec: InterceptSpecPayload
    value: float
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    at_bound: bool


@dataclass(frozen=True)
class CurveDetail:
    curve_id: uuid.UUID
    run_id: uuid.UUID
    batch_id: uuid.UUID
    readout_definition_id: uuid.UUID
    curve_type: str
    fitted_value: float
    fitted_unit: str  # protocol's dose_unit, set by caller from the protocol
    hill_slope: float
    r_squared: float
    curve_class: str | None
    top: float
    bottom: float
    num_points: int
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    raw_data: list[dict[str, Any]]
    # Mirrors the run-page DRC response so the search-detail panel can render
    # the same chemistry-quality signals (at-bound EC50 warnings, IC90/IC10
    # intercepts, auto-/manually-excluded replicate points). Without these
    # the panel was silently hiding fit-quality issues during hit triage.
    excluded_points: list[dict[str, Any]] | None
    fit_quality_warnings: list[str]
    intercept_values: list[InterceptValuePayload]

    @classmethod
    def from_domain(cls, curve: DoseResponseCurve, *, dose_unit: str) -> CurveDetail:
        return cls(
            curve_id=curve.id,
            run_id=curve.run_id,
            batch_id=curve.batch_id,
            readout_definition_id=curve.readout_definition_id,
            curve_type=curve.curve_type.value,
            fitted_value=curve.fitted_value,
            fitted_unit=dose_unit,
            hill_slope=curve.hill_slope,
            r_squared=curve.r_squared,
            curve_class=curve.curve_class.value if curve.curve_class else None,
            top=curve.top,
            bottom=curve.bottom,
            num_points=curve.num_points,
            confidence_interval_low=curve.confidence_interval_low,
            confidence_interval_high=curve.confidence_interval_high,
            raw_data=_condense_raw_data(curve.raw_data or []),
            excluded_points=curve.excluded_points,
            fit_quality_warnings=list(curve.fit_quality_warnings or []),
            intercept_values=[
                InterceptValuePayload(
                    spec=InterceptSpecPayload(
                        kind=iv.spec.kind.value,
                        level=iv.spec.level,
                        basis=iv.spec.basis.value,
                        label=iv.spec.label,
                    ),
                    value=iv.value,
                    confidence_interval_low=iv.confidence_interval_low,
                    confidence_interval_high=iv.confidence_interval_high,
                    at_bound=iv.at_bound,
                )
                for iv in (curve.intercept_values or [])
            ],
        )


@dataclass(frozen=True)
class ProtocolCurveGroup:
    protocol_id: uuid.UUID
    protocol_name: str
    protocol_type: str
    target_id: uuid.UUID | None
    curves: list[CurveDetail]


@dataclass(frozen=True)
class MoleculeActivityDetail:
    molecule_id: uuid.UUID
    protocols: list[ProtocolCurveGroup] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class GetMoleculeActivityDetail:
    """Return all dose-response curves for a molecule, grouped by protocol."""

    def __init__(
        self,
        uow: UnitOfWork,
        curve_repo: DoseResponseCurveRepository,
        protocol_repo: ProtocolRepository,
    ) -> None:
        self._uow = uow
        self._curve_repo = curve_repo
        self._protocol_repo = protocol_repo

    async def __call__(
        self,
        input: GetMoleculeActivityDetailQuery,
        auth: AuthContext | None = None,
    ) -> Result[MoleculeActivityDetail, DomainError]:
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            # 1. Fetch all curves for this molecule (sorted by r_squared DESC)
            curves = await self._curve_repo.find_by_molecule(input.workspace_id, input.molecule_id)

            if not curves:
                return Success(MoleculeActivityDetail(molecule_id=input.molecule_id, protocols=[]))

            # 2. Group curves by protocol_id
            by_protocol: dict[uuid.UUID, list[DoseResponseCurve]] = defaultdict(list)
            for curve in curves:
                by_protocol[curve.protocol_id].append(curve)

            # 3. Fetch protocol metadata in a single query
            protocols = await self._protocol_repo.find_by_ids(
                input.workspace_id, list(by_protocol.keys())
            )
            proto_map = {p.id: p for p in protocols}

            # 4. Build response, sorting curves within each group by r_squared DESC
            groups: list[ProtocolCurveGroup] = []
            for protocol_id, protocol_curves in by_protocol.items():
                proto = proto_map.get(protocol_id)
                sorted_curves = sorted(protocol_curves, key=lambda c: c.r_squared, reverse=True)
                dose_unit = proto.dose_unit.value if proto else "uM"
                groups.append(
                    ProtocolCurveGroup(
                        protocol_id=protocol_id,
                        protocol_name=proto.name if proto else "Unknown",
                        protocol_type=proto.protocol_type.value if proto else "unknown",
                        target_id=proto.target_id if proto else None,
                        curves=[
                            CurveDetail.from_domain(c, dose_unit=dose_unit) for c in sorted_curves
                        ],
                    )
                )

            return Success(MoleculeActivityDetail(molecule_id=input.molecule_id, protocols=groups))
