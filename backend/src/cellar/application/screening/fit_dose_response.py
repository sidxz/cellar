"""FitDoseResponseCurves — auto-fit dose-response curves for a screening run."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.screening._dose_response_config_serde import (
    serialize_dose_response_config,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    CurveFittingService,
    FittedCurveResult,
)
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import (
    HillSlopeConstraint,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.excluded_point_detail import (
    ExcludedPointDetail,
    ExclusionReason,
    ExclusionSource,
)
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.repository import DoseResponseCurveRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import AuthorizationError, DomainError

_MIN_POINTS = 4


def _build_excluded_from_fitter(
    fitted: FittedCurveResult,
) -> list[ExcludedPointDetail] | list[dict]:
    """Translate a ``FittedCurveResult`` into the curve's ``excluded_points``.

    For the initial-fit path (auto-fit on run import) the fitter's input list
    has no pre-excluded points, so ``fitted.excluded_points`` is always empty.
    Any ``fitted.outlier_suggestions`` become ``ExcludedPointDetail`` entries
    with ``source=AUTO_3SIGMA`` and ``excluded=False`` — the FE renders them
    as yellow-halo "suggested for exclusion" markers; chemists accept or
    reject in edit mode.

    Returns ``[]`` when neither pre-excluded points nor suggestions exist.
    """
    if not fitted.outlier_suggestions:
        # Preserve the legacy dict-shape path for the (currently impossible)
        # case where the fitter wrote any pre-excluded entries — the repo
        # tolerates either shape.
        return list(fitted.excluded_points or [])

    now = datetime.now(UTC)
    out: list[ExcludedPointDetail] = []
    for s in fitted.outlier_suggestions:
        out.append(
            ExcludedPointDetail(
                idx=s.idx,
                source=ExclusionSource.AUTO_3SIGMA,
                excluded=False,  # SUGGESTION, not an exclusion
                reason=ExclusionReason.AUTO_3SIGMA,
                author_id=None,  # the fitter wrote this, no human author
                ts=now,
                concentration=s.concentration,
                response=s.response,
            )
        )
    return out


@dataclass(frozen=True)
class FitRunResult:
    """Outcome of fitting all dose-response curves for one run.

    ``warnings`` carries one entry per skipped fit — typically a fitter
    Failure that would otherwise have been silently swallowed. Each entry
    names the molecule/batch and the underlying error so the user can see
    which compounds didn't get curves.
    """

    curves: list[DoseResponseCurve]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class FitOverrides:
    """Transient per-fit constraint overrides.

    Used by Recompute to apply run-wide bounds without persisting them on
    the protocol or run. Mirrors the protocol's full Free/Range/Lock
    vocabulary so the popover UI matches the protocol-design surface.

    Each ``override_<param>`` flag, when True, makes the override the
    authoritative source for that param on this recompute (Free included).
    When False, the protocol's config carries through unchanged. The
    matching ``top``/``bottom``/``*_min``/``*_max``/``hill_slope`` fields
    are read only when the corresponding flag is True; their interpretation
    is the same as on the protocol:

      - ``top`` set + ``top_min``/``top_max`` unset → Lock
      - ``top_min`` and/or ``top_max`` set, ``top`` unset → Range
      - all three unset → Free
    """

    override_top: bool = False
    top: float | None = None
    top_min: float | None = None
    top_max: float | None = None
    override_bottom: bool = False
    bottom: float | None = None
    bottom_min: float | None = None
    bottom_max: float | None = None
    override_hill: bool = False
    hill_slope: HillSlopeConstraint | None = None
    hill_slope_min: float | None = None
    hill_slope_max: float | None = None

    def is_empty(self) -> bool:
        return not (self.override_top or self.override_bottom or self.override_hill)

    def apply(self, base: DoseResponseConfig) -> DoseResponseConfig:
        if self.is_empty():
            return base
        if self.override_top:
            top_lock = self.top
            top_min = self.top_min
            top_max = self.top_max
        else:
            top_lock = base.top_constraint
            top_min = base.top_constraint_min
            top_max = base.top_constraint_max

        if self.override_bottom:
            bottom_lock = self.bottom
            bottom_min = self.bottom_min
            bottom_max = self.bottom_max
        else:
            bottom_lock = base.bottom_constraint
            bottom_min = base.bottom_constraint_min
            bottom_max = base.bottom_constraint_max

        if self.override_hill:
            hill_enum = (
                self.hill_slope
                if self.hill_slope is not None
                else HillSlopeConstraint.UNCONSTRAINED
            )
            hill_min = self.hill_slope_min
            hill_max = self.hill_slope_max
        else:
            hill_enum = base.hill_slope_constraint
            hill_min = base.hill_slope_min
            hill_max = base.hill_slope_max

        return DoseResponseConfig(
            curve_type=base.curve_type,
            x_readout_name=base.x_readout_name,
            y_readout_name=base.y_readout_name,
            # Multi-emit + multi-intercept fields must flow through unchanged
            # — Recompute's contract is "tweak constraints, not what we
            # report." Dropping them silently turned protocol-level
            # IC50+IC90 into IC50-only after any refit.
            y_normalization=base.y_normalization,
            intercepts=base.intercepts,
            hill_slope_constraint=hill_enum,
            activity_threshold=base.activity_threshold,
            normalization_scope=base.normalization_scope,
            top_constraint=top_lock,
            bottom_constraint=bottom_lock,
            top_constraint_min=top_min,
            top_constraint_max=top_max,
            bottom_constraint_min=bottom_min,
            bottom_constraint_max=bottom_max,
            hill_slope_min=hill_min,
            hill_slope_max=hill_max,
            outlier_sigma=base.outlier_sigma,
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
        workspace_id: uuid.UUID,
        overrides: FitOverrides | None = None,
    ) -> Result[FitRunResult, DomainError]:
        """Fit curves for all DOSE_RESPONSE readout definitions in the protocol.

        ``workspace_id`` must match both ``run.workspace_id`` and
        ``protocol.workspace_id``; cross-workspace calls are rejected.
        """
        if run.workspace_id != workspace_id:
            return Failure(
                AuthorizationError(
                    "Run workspace mismatch — run does not belong to the caller's workspace"
                )
            )
        if protocol.workspace_id != workspace_id:
            return Failure(
                AuthorizationError(
                    "Protocol workspace mismatch — protocol does not belong to "
                    "the caller's workspace"
                )
            )

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
    ) -> Result[FitRunResult, DomainError]:
        dr_defs = [
            rd
            for rd in protocol.readout_definitions
            if rd.data_type == ReadoutDataType.DOSE_RESPONSE
            and rd.dose_response_config is not None
        ]
        if not dr_defs:
            return Success(FitRunResult(curves=[], warnings=[]))

        well_map = {w.id: w for w in run.wells}
        rd_by_name = {rd.name: rd for rd in protocol.readout_definitions}

        # Idempotent: remove previous auto-fitted curves
        await self._curve_repo.delete_by_run(run.workspace_id, run.id)

        all_curves: list[DoseResponseCurve] = []
        warnings: list[str] = []

        for dr_def in dr_defs:
            base_config = dr_def.dose_response_config
            config = overrides.apply(base_config) if overrides is not None else base_config
            y_readout_name = config.y_readout_name

            y_rd = rd_by_name.get(y_readout_name)
            if y_rd is None:
                warnings.append(
                    f"Readout '{dr_def.name}': Y readout '{y_readout_name}' not found "
                    f"on the protocol; skipping."
                )
                continue

            # Per readout def, exactly one value layer is the canonical fit input.
            # Selection key:
            #   * If the def is calculated, fit the computed (formula-output) layer.
            #   * Else if the def emits any normalization formulas, the fit consumes
            #     the formula named by ``config.y_normalization``. When that field
            #     is None, default to the def's first formula (back-compat with the
            #     pre-multi-emit single-value world).
            #   * Else (no normalizations on the def), fit the raw layer.
            target_formula: ReadoutNormalization | None
            if y_rd.is_calculated:
                target_formula = None  # filtered by is_computed below
                use_computed = True
            elif y_rd.normalizations:
                if config.y_normalization is not None:
                    target_formula = config.y_normalization
                else:
                    # Pre-multi-emit protocols set normalizations={X} and no
                    # y_normalization. Pick the (only) formula in the set.
                    target_formula = next(iter(y_rd.normalizations))
                use_computed = True
            else:
                target_formula = None
                use_computed = False

            # Group readout data by (molecule_id, batch_id)
            groups: dict[tuple[uuid.UUID, uuid.UUID], list[ConcentrationResponsePoint]] = (
                defaultdict(list)
            )

            for rd in readout_data:
                if rd.readout_definition_id != y_rd.id:
                    continue
                if rd.is_computed != use_computed:
                    continue
                # If we want a specific formula, the row must be tagged with it.
                # Calculated readouts are filtered by is_computed alone (no formula).
                if target_formula is not None and rd.normalization_applied != target_formula:
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
                    warnings.append(
                        f"Molecule {molecule_id} batch {batch_id} on '{dr_def.name}': "
                        f"only {len(points)} dose point(s) — need at least {_MIN_POINTS}."
                    )
                    continue

                fit_result = self._curve_fitter.fit(points, config)
                if isinstance(fit_result, Failure):
                    err = fit_result.failure()
                    warnings.append(
                        f"Molecule {molecule_id} batch {batch_id} on "
                        f"'{dr_def.name}': fit failed — {err}"
                    )
                    continue

                fitted = fit_result.unwrap()
                # Snapshot the *actual config used for this fit* (post-override)
                # so reproducibility doesn't depend on the readout-def's live
                # config staying unchanged.
                config_snapshot = serialize_dose_response_config(config)
                # The fitter no longer silently excludes auto-3σ outliers; it
                # nominates them on ``outlier_suggestions``. Persist them as
                # ExcludedPointDetail(source=AUTO_3SIGMA, excluded=False) so
                # the FE can render yellow-halo "suggested for exclusion"
                # markers (Sprint-2 FE Task 2.16) — the chemist explicitly
                # accepts or rejects in edit mode.
                excluded_points_payload = _build_excluded_from_fitter(fitted)
                curve = DoseResponseCurve(
                    workspace_id=run.workspace_id,
                    molecule_id=molecule_id,
                    batch_id=batch_id,
                    protocol_id=run.protocol_id,
                    run_id=run.id,
                    readout_definition_id=dr_def.id,
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
                    excluded_points=excluded_points_payload,
                    fit_quality_warnings=list(fitted.fit_quality_warnings),
                    intercept_values=list(fitted.intercept_values),
                    dose_response_config_snapshot=config_snapshot,
                )
                await self._curve_repo.save(curve)
                all_curves.append(curve)

        return Success(FitRunResult(curves=all_curves, warnings=warnings))
