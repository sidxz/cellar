"""Step 15 — Dose-response curves (fallback).

If the ReadoutCalculationEngine auto-fitted curves in s14, this is a no-op.
Otherwise, generates curves directly via LmfitCurveFitter as a fallback
to ensure the demo always has dose-response data to display.
"""

from __future__ import annotations

import random

import structlog
from returns.result import Failure

from ._context import WORKSPACE_ID, DemoContext

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
        DoseResponseCurveModel,
    )

    sf = ctx.container[async_sessionmaker]

    # Check if curves were already auto-created by the engine
    async with sf() as session:
        count_stmt = select(func.count()).select_from(DoseResponseCurveModel).where(
            DoseResponseCurveModel.workspace_id == WORKSPACE_ID
        )
        existing = (await session.execute(count_stmt)).scalar() or 0

    if existing > 0:
        logger.info("dose_response.already_fitted", count=existing)
        return 0

    # Fallback: generate curves directly via LmfitCurveFitter
    logger.info("dose_response.fallback_fitting")

    from cellar.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
    from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
    from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
    from cellar.domain.screening_assay.enums import CurveType, HillSlopeConstraint
    from cellar.infrastructure.lmfit.curve_fitter import LmfitCurveFitter
    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
        SQLAlchemyDoseResponseCurveRepository,
    )
    from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

    data = ctx.data("dose_response.json")
    fitter = LmfitCurveFitter()
    created = 0

    for key, config in data.items():
        if key.startswith("_"):
            continue

        mol_id = ctx.registry.get_optional(config["molecule_ref"])
        if mol_id is None:
            continue

        mol_name = config["molecule_ref"].removeprefix("mol_")
        batch_key = f"batch_{mol_name}_01"
        batch_id = ctx.registry.get_optional(batch_key)
        if batch_id is None:
            continue

        protocol_id = ctx.registry.get_optional(config["protocol_ref"])
        run_id = ctx.registry.get_optional(config["run_ref"])
        if protocol_id is None or run_id is None:
            continue

        ic50 = config["fitted_value"]
        hill_slope = abs(config.get("hill_slope", 1.0))
        top = config.get("top", 100.0)
        bottom = config.get("bottom", 0.0)

        rng = random.Random(hash(key))
        concentrations = [10000.0 / (3**i) for i in range(10)]
        points = [
            ConcentrationResponsePoint(
                concentration=conc,
                # % Inhibition convention: high inhibition at high conc, low at low conc
                response=max(0, bottom + (top - bottom) / (1 + (ic50 / conc) ** hill_slope) + rng.gauss(0, (top - bottom) * 0.03)),
            )
            for conc in concentrations
        ]

        dr_config = DoseResponseConfig(
            curve_type=CurveType(config.get("curve_type", "ic50")),
            x_readout_name="Concentration",
            y_readout_name="% Inhibition",
            hill_slope_constraint=HillSlopeConstraint.NEGATIVE_ONLY,
        )
        fit_result = fitter.fit(points, dr_config)

        if isinstance(fit_result, Failure):
            logger.warning("dose_response.fit_failed", key=key, error=str(fit_result.failure()))
            continue

        fitted = fit_result.unwrap()

        uow = AsyncUnitOfWork(sf)
        async with uow:
            repo = SQLAlchemyDoseResponseCurveRepository(uow)
            curve = DoseResponseCurve(
                workspace_id=WORKSPACE_ID,
                molecule_id=mol_id,
                batch_id=batch_id,
                protocol_id=protocol_id,
                run_id=run_id,
                curve_type=dr_config.curve_type,
                fitted_value=fitted.fitted_value,
                fitted_unit=config.get("fitted_unit", "nM"),
                hill_slope=fitted.hill_slope,
                top=fitted.top,
                bottom=fitted.bottom,
                r_squared=fitted.r_squared,
                confidence_interval_low=fitted.confidence_interval_low,
                confidence_interval_high=fitted.confidence_interval_high,
                num_points=fitted.num_points,
                curve_class=fitted.curve_class,
                raw_data=fitted.raw_data,
                excluded_points=fitted.excluded_points,
            )
            await repo.save(curve)
            await uow.commit()

        created += 1
        logger.info(
            "dose_response.created",
            key=key,
            ic50=round(fitted.fitted_value, 2),
            r2=round(fitted.r_squared, 3),
            curve_class=fitted.curve_class.value,
        )

    return created
