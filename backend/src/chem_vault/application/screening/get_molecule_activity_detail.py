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

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.application.screening import _condense_raw_data
from chem_vault.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
)
from chem_vault.domain.shared.errors import DomainError


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
class CurveDetail:
    curve_id: uuid.UUID
    run_id: uuid.UUID
    batch_id: uuid.UUID
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

    @classmethod
    def from_domain(
        cls, curve: DoseResponseCurve, *, dose_unit: str
    ) -> CurveDetail:
        return cls(
            curve_id=curve.id,
            run_id=curve.run_id,
            batch_id=curve.batch_id,
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
            curves = await self._curve_repo.find_by_molecule(
                input.workspace_id, input.molecule_id
            )

            if not curves:
                return Success(
                    MoleculeActivityDetail(molecule_id=input.molecule_id, protocols=[])
                )

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
                sorted_curves = sorted(
                    protocol_curves, key=lambda c: c.r_squared, reverse=True
                )
                dose_unit = proto.dose_unit.value if proto else "uM"
                groups.append(
                    ProtocolCurveGroup(
                        protocol_id=protocol_id,
                        protocol_name=proto.name if proto else "Unknown",
                        protocol_type=proto.protocol_type.value if proto else "unknown",
                        target_id=proto.target_id if proto else None,
                        curves=[
                            CurveDetail.from_domain(c, dose_unit=dose_unit)
                            for c in sorted_curves
                        ],
                    )
                )

            return Success(
                MoleculeActivityDetail(molecule_id=input.molecule_id, protocols=groups)
            )
