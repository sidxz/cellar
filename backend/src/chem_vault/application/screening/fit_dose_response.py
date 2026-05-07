"""FitDoseResponseCurves — auto-fit dose-response curves for a screening run."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    CurveFittingService,
)
from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.enums import (
    HillSlopeConstraint,
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.protocol import Protocol
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.repository import DoseResponseCurveRepository
from chem_vault.domain.screening_assay.run import Run
from chem_vault.domain.shared.errors import DomainError

_MIN_POINTS = 4


@dataclass(frozen=True, kw_only=True)
class FitOverrides:
    """Transient per-fit constraint overrides.

    Used by Recompute to apply run-wide bounds (e.g. Top=100 for % Inhibition
    assays whose top plateau wasn't observed) without persisting them on the
    protocol or run. Each field, when set, overrides the corresponding field
    on the protocol's DoseResponseConfig for this fit pass only.
    """

    top: float | None = None
    bottom: float | None = None
    hill_slope: HillSlopeConstraint | None = None

    def is_empty(self) -> bool:
        return self.top is None and self.bottom is None and self.hill_slope is None

    def apply(self, base: DoseResponseConfig) -> DoseResponseConfig:
        if self.is_empty():
            return base
        return DoseResponseConfig(
            curve_type=base.curve_type,
            x_readout_name=base.x_readout_name,
            y_readout_name=base.y_readout_name,
            hill_slope_constraint=(
                self.hill_slope
                if self.hill_slope is not None
                else base.hill_slope_constraint
            ),
            activity_threshold=base.activity_threshold,
            normalization_scope=base.normalization_scope,
            top_constraint=self.top if self.top is not None else base.top_constraint,
            bottom_constraint=(
                self.bottom if self.bottom is not None else base.bottom_constraint
            ),
        )


class FitDoseResponseCurves:
    """Auto-fit dose-response curves for all compounds in a screening run.

    For each DOSE_RESPONSE readout definition on the protocol, groups data
    by (molecule, batch), fits a 4PL curve, and persists the result.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        curve_repo: DoseResponseCurveRepository,
        curve_fitter: CurveFittingService,
    ) -> None:
        self._uow = uow
        self._curve_repo = curve_repo
        self._curve_fitter = curve_fitter

    async def fit_for_run(
        self,
        *,
        run: Run,
        protocol: Protocol,
        readout_data: list[ReadoutData],
        overrides: FitOverrides | None = None,
    ) -> Result[list[DoseResponseCurve], DomainError]:
        """Fit curves for all DOSE_RESPONSE readout definitions in the protocol."""
        if not self._uow.is_active:
            async with self._uow:
                result = await self._fit(
                    run=run,
                    protocol=protocol,
                    readout_data=readout_data,
                    overrides=overrides,
                )
                if isinstance(result, Success):
                    await self._uow.commit()
                return result
        return await self._fit(
            run=run,
            protocol=protocol,
            readout_data=readout_data,
            overrides=overrides,
        )

    async def _fit(
        self,
        *,
        run: Run,
        protocol: Protocol,
        readout_data: list[ReadoutData],
        overrides: FitOverrides | None = None,
    ) -> Result[list[DoseResponseCurve], DomainError]:
        dr_defs = [
            rd for rd in protocol.readout_definitions
            if rd.data_type == ReadoutDataType.DOSE_RESPONSE
            and rd.dose_response_config is not None
        ]
        if not dr_defs:
            return Success([])

        well_map = {w.id: w for w in run.wells}

        # Idempotent: remove previous auto-fitted curves
        await self._curve_repo.delete_by_run(run.workspace_id, run.id)

        all_curves: list[DoseResponseCurve] = []

        for dr_def in dr_defs:
            base_config = dr_def.dose_response_config
            config = (
                overrides.apply(base_config) if overrides is not None else base_config
            )
            y_readout_name = config.y_readout_name

            y_rd = next(
                (rd for rd in protocol.readout_definitions if rd.name == y_readout_name),
                None,
            )
            if y_rd is None:
                continue

            # Per readout def, exactly one value layer is the canonical fit input:
            # post-normalization for normalized readouts, the formula output for
            # calculated readouts, otherwise the raw values.
            use_computed = (
                y_rd.normalization != ReadoutNormalization.NONE
                or y_rd.is_calculated
            )

            # Group readout data by (molecule_id, batch_id)
            groups: dict[tuple[uuid.UUID, uuid.UUID], list[ConcentrationResponsePoint]] = defaultdict(list)

            for rd in readout_data:
                if rd.readout_definition_id != y_rd.id:
                    continue
                if rd.is_computed != use_computed:
                    continue
                if rd.value is None or rd.well_id is None:
                    continue
                well = well_map.get(rd.well_id)
                if well is None or well.dose is None:
                    continue
                key = (rd.molecule_id, rd.batch_id)
                groups[key].append(
                    ConcentrationResponsePoint(
                        concentration=well.dose,
                        response=rd.value.value,
                    )
                )

            for (molecule_id, batch_id), points in groups.items():
                if len(points) < _MIN_POINTS:
                    continue

                fit_result = self._curve_fitter.fit(points, config)
                if isinstance(fit_result, Failure):
                    continue

                fitted = fit_result.unwrap()
                curve = DoseResponseCurve(
                    workspace_id=run.workspace_id,
                    molecule_id=molecule_id,
                    batch_id=batch_id,
                    protocol_id=run.protocol_id,
                    run_id=run.id,
                    curve_type=config.curve_type,
                    fitted_value=fitted.fitted_value,
                    hill_slope=fitted.hill_slope,
                    top=fitted.top,
                    bottom=fitted.bottom,
                    r_squared=fitted.r_squared,
                    confidence_interval_low=fitted.confidence_interval_low,
                    confidence_interval_high=fitted.confidence_interval_high,
                    num_points=fitted.num_points,
                    curve_class=fitted.curve_class,
                    raw_data=fitted.raw_data,
                    excluded_points=fitted.excluded_points or [],
                    fit_quality_warnings=list(fitted.fit_quality_warnings),
                )
                await self._curve_repo.save(curve)
                all_curves.append(curve)

        return Success(all_curves)
