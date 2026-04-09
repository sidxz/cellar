"""Step 15 — Generate dose-response curves using LmfitCurveFitter."""

from __future__ import annotations

import random

import structlog
from returns.result import Failure

from ._context import WORKSPACE_ID, DemoContext

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from chem_vault.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
    from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
    from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
    from chem_vault.domain.screening_assay.enums import CurveType, HillSlopeConstraint
    from chem_vault.infrastructure.lmfit.curve_fitter import LmfitCurveFitter
    from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
        SQLAlchemyDoseResponseCurveRepository,
    )
    from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

    data = ctx.data("dose_response.json")
    fitter = LmfitCurveFitter()
    session_factory = ctx.container[async_sessionmaker]
    created = 0

    for key, config in data.items():
        if key.startswith("_"):
            continue

        mol_id = ctx.registry.get_optional(config["molecule_ref"])
        if mol_id is None:
            logger.warning("dose_response.molecule_missing", key=key, ref=config["molecule_ref"])
            continue

        # Derive batch key: "mol_gefitinib" -> "batch_gefitinib_01"
        mol_name = config["molecule_ref"].removeprefix("mol_")
        batch_key = f"batch_{mol_name}_01"
        batch_id = ctx.registry.get_optional(batch_key)
        if batch_id is None:
            logger.warning("dose_response.batch_missing", key=key, batch_key=batch_key)
            continue

        protocol_id = ctx.registry.get_optional(config["protocol_ref"])
        run_id = ctx.registry.get_optional(config["run_ref"])
        if protocol_id is None or run_id is None:
            logger.warning("dose_response.refs_missing", key=key)
            continue

        # Generate synthetic dose-response data using the Hill equation + noise
        ic50 = config["fitted_value"]
        hill_slope = abs(config.get("hill_slope", 1.0))
        top = config.get("top", 100.0)
        bottom = config.get("bottom", 0.0)

        rng = random.Random(hash(key))
        concentrations = [10000.0 / (3 ** i) for i in range(10)]
        points = []
        for conc in concentrations:
            response = bottom + (top - bottom) / (1 + (conc / ic50) ** hill_slope)
            noise = rng.gauss(0, (top - bottom) * 0.03)
            points.append(ConcentrationResponsePoint(
                concentration=conc,
                response=max(0, response + noise),
            ))

        # Fit using the real fitter
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

        # Save via UoW + repository
        uow = AsyncUnitOfWork(session_factory)
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
