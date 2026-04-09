"""RefitDoseResponseCurve — re-fit an existing curve with modified exclusions/constraints."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    CurveFittingService,
)
from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.enums import CurveType, HillSlopeConstraint, ReadoutDataType
from chem_vault.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class RefitDoseResponseCurveCommand(Command):
    workspace_id: uuid.UUID
    curve_id: uuid.UUID
    excluded_point_indices: list[int] = field(default_factory=list)
    hill_slope_constraint: str | None = None
    top_constraint: float | None = None
    bottom_constraint: float | None = None


class RefitDoseResponseCurve:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        curve_repo: DoseResponseCurveRepository,
        protocol_repo: ProtocolRepository,
        curve_fitter: CurveFittingService,
    ) -> None:
        self._uow = uow
        self._curve_repo = curve_repo
        self._protocol_repo = protocol_repo
        self._curve_fitter = curve_fitter

    async def __call__(
        self, input: RefitDoseResponseCurveCommand, auth: AuthContext | None = None
    ) -> Result[DoseResponseCurve, DomainError]:
        require_editor(auth)

        async with self._uow:
            curve = await self._curve_repo.find_by_id_in_workspace(
                input.workspace_id, input.curve_id
            )
            if curve is None:
                return Failure(NotFoundError("DoseResponseCurve", str(input.curve_id)))

            # Reconstruct all points from raw_data + excluded_points
            all_points_raw = list(curve.raw_data or []) + list(curve.excluded_points or [])
            all_points_raw.sort(key=lambda p: p.get("concentration", 0), reverse=True)

            excluded_set = set(input.excluded_point_indices)
            points = [
                ConcentrationResponsePoint(
                    concentration=pt["concentration"],
                    response=pt["response"],
                    is_excluded=(i in excluded_set),
                )
                for i, pt in enumerate(all_points_raw)
            ]

            config = await self._resolve_config(input, curve)

            fit_result = self._curve_fitter.fit(points, config)
            if isinstance(fit_result, Failure):
                return fit_result

            fitted = fit_result.unwrap()

            curve.fitted_value = fitted.fitted_value
            curve.hill_slope = fitted.hill_slope
            curve.top = fitted.top
            curve.bottom = fitted.bottom
            curve.r_squared = fitted.r_squared
            curve.confidence_interval_low = fitted.confidence_interval_low
            curve.confidence_interval_high = fitted.confidence_interval_high
            curve.num_points = fitted.num_points
            curve.curve_class = fitted.curve_class
            curve.raw_data = fitted.raw_data
            curve.excluded_points = fitted.excluded_points

            await self._curve_repo.save(curve)
            await self._uow.commit()
            return Success(curve)

    async def _resolve_config(
        self, input: RefitDoseResponseCurveCommand, curve: DoseResponseCurve
    ) -> DoseResponseConfig:
        """Get protocol's DoseResponseConfig and merge user overrides."""
        protocol = await self._protocol_repo.find_by_id_in_workspace(
            input.workspace_id, curve.protocol_id
        )
        base_config = None
        if protocol:
            for rd in protocol.readout_definitions:
                if rd.data_type == ReadoutDataType.DOSE_RESPONSE and rd.dose_response_config:
                    base_config = rd.dose_response_config
                    break

        if base_config is None:
            base_config = DoseResponseConfig(
                curve_type=curve.curve_type if isinstance(curve.curve_type, CurveType) else CurveType(curve.curve_type),
                x_readout_name="Concentration",
                y_readout_name="Response",
            )

        hill = (
            HillSlopeConstraint(input.hill_slope_constraint)
            if input.hill_slope_constraint
            else base_config.hill_slope_constraint
        )
        top = input.top_constraint if input.top_constraint is not None else base_config.top_constraint
        bottom = input.bottom_constraint if input.bottom_constraint is not None else base_config.bottom_constraint

        return DoseResponseConfig(
            curve_type=base_config.curve_type,
            x_readout_name=base_config.x_readout_name,
            y_readout_name=base_config.y_readout_name,
            hill_slope_constraint=hill,
            activity_threshold=base_config.activity_threshold,
            normalization_scope=base_config.normalization_scope,
            top_constraint=top,
            bottom_constraint=bottom,
        )
