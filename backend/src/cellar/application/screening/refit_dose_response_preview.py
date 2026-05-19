"""RefitDoseResponseCurvePreview — compute-only refit, no persistence, no audit.

Used by the FE during point-editing sessions to render the candidate 4PL fit
on every draft toggle. The commit path (``RefitDoseResponseCurve``) handles
persistence + audit + data-lock guard on Save.

Key differences from the commit use case:
- No UnitOfWork, no save, no audit trail emission.
- No DataLockGuard check — preview is a pure read on the curve.
- ``outlier_sigma`` is UNCONDITIONALLY None: the chemist owns the exclusion
  set during point editing; cascading auto-3σ exclusions would defeat the
  purpose of the manual-edit mode.
- No constraint overrides (top/bottom/hill/range). Preview reflects what
  Save would produce with the current protocol config + the candidate
  excluded set only. If chemists ever need preview-with-constraints, extend
  ``PreviewRefitCommand`` symmetrically with the commit command.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    CurveFittingService,
    FittedCurveResult,
)
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveType, ReadoutDataType
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class PreviewRefitCommand(Command):
    workspace_id: uuid.UUID
    curve_id: uuid.UUID
    excluded_point_indices: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class PreviewRefitResult:
    """Compute-only preview of a 4PL fit.

    Mirrors the subset of ``FittedCurveResult`` the FE needs to redraw the
    candidate curve on every draft toggle. Does NOT include the persisted
    fields (``intercept_values`` snapshot, ``fit_quality_warnings``, etc.) —
    add them here if the FE later needs them in preview.
    """

    fitted_value: float
    hill_slope: float
    top: float
    bottom: float
    r_squared: float
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    curve_class: str
    points_in_fit: int
    points_total: int


class RefitDoseResponseCurvePreview:
    """Compute-only preview refit; no DB write, no audit, no auto-outlier."""

    def __init__(
        self,
        *,
        curve_repo: DoseResponseCurveRepository,
        protocol_repo: ProtocolRepository,
        curve_fitter: CurveFittingService,
    ) -> None:
        self._curve_repo = curve_repo
        self._protocol_repo = protocol_repo
        self._curve_fitter = curve_fitter

    async def __call__(
        self,
        input: PreviewRefitCommand,
        auth: AuthContext | None = None,
    ) -> Result[PreviewRefitResult, DomainError]:
        require_editor(auth)

        curve = await self._curve_repo.find_by_id_in_workspace(
            input.workspace_id, input.curve_id
        )
        if curve is None:
            return Failure(NotFoundError("DoseResponseCurve", str(input.curve_id)))

        # Point reconstruction mirrors RefitDoseResponseCurve exactly — ascending
        # by concentration so client-supplied indices line up with the UI's
        # display order. Task 2.7 may lift this helper to a shared module.
        points = _build_points_with_exclusions(curve, input.excluded_point_indices)

        config = await self._build_preview_config(curve)

        fit_result = self._curve_fitter.fit(points, config)
        if isinstance(fit_result, Failure):
            return fit_result

        fitted = fit_result.unwrap()
        return Success(_to_preview_result(fitted, points))

    async def _build_preview_config(self, curve: DoseResponseCurve) -> DoseResponseConfig:
        """Resolve protocol's DoseResponseConfig but force ``outlier_sigma=None``.

        Preview NEVER runs the fitter's auto-3σ outlier pass — the chemist is
        in control of the exclusion set during point editing.
        """
        protocol = await self._protocol_repo.find_by_id_in_workspace(
            curve.workspace_id, curve.protocol_id
        )
        base_config: DoseResponseConfig | None = None
        if protocol:
            for rd in protocol.readout_definitions:
                if rd.data_type == ReadoutDataType.DOSE_RESPONSE and rd.dose_response_config:
                    base_config = rd.dose_response_config
                    break

        if base_config is None:
            base_config = DoseResponseConfig(
                curve_type=curve.curve_type
                if isinstance(curve.curve_type, CurveType)
                else CurveType(curve.curve_type),
                x_readout_name="Concentration",
                y_readout_name="Response",
            )

        return DoseResponseConfig(
            curve_type=base_config.curve_type,
            x_readout_name=base_config.x_readout_name,
            y_readout_name=base_config.y_readout_name,
            hill_slope_constraint=base_config.hill_slope_constraint,
            activity_threshold=base_config.activity_threshold,
            normalization_scope=base_config.normalization_scope,
            top_constraint=base_config.top_constraint,
            bottom_constraint=base_config.bottom_constraint,
            top_constraint_min=base_config.top_constraint_min,
            top_constraint_max=base_config.top_constraint_max,
            bottom_constraint_min=base_config.bottom_constraint_min,
            bottom_constraint_max=base_config.bottom_constraint_max,
            hill_slope_min=base_config.hill_slope_min,
            hill_slope_max=base_config.hill_slope_max,
            # CRITICAL: never run auto-outlier detection during preview.
            outlier_sigma=None,
        )


def _build_points_with_exclusions(
    curve: DoseResponseCurve, excluded_indices: list[int]
) -> list[ConcentrationResponsePoint]:
    """Reconstruct ascending-by-concentration points from raw_data + flag exclusions.

    Duplicated from ``RefitDoseResponseCurve.__call__`` body for Sprint 2; Task
    2.7 may lift this to a shared module. Keep the two in sync — index→dose
    semantics must match between preview and commit or the FE will see a
    different fit on Save than during edit.
    """
    all_points_raw = list(curve.raw_data or []) + list(curve.excluded_points or [])
    all_points_raw.sort(key=lambda p: p.get("concentration", 0))

    excluded_set = set(excluded_indices)
    return [
        ConcentrationResponsePoint(
            concentration=pt["concentration"],
            response=pt["response"],
            is_excluded=(i in excluded_set),
        )
        for i, pt in enumerate(all_points_raw)
    ]


def _to_preview_result(
    fitted: FittedCurveResult, points: list[ConcentrationResponsePoint]
) -> PreviewRefitResult:
    return PreviewRefitResult(
        fitted_value=fitted.fitted_value,
        hill_slope=fitted.hill_slope,
        top=fitted.top,
        bottom=fitted.bottom,
        r_squared=fitted.r_squared,
        confidence_interval_low=fitted.confidence_interval_low,
        confidence_interval_high=fitted.confidence_interval_high,
        curve_class=fitted.curve_class.value
        if hasattr(fitted.curve_class, "value")
        else str(fitted.curve_class),
        points_in_fit=sum(1 for p in points if not p.is_excluded),
        points_total=len(points),
    )
