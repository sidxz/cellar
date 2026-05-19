"""RefitDoseResponseCurve — re-fit an existing curve with modified exclusions/constraints."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.application.auth import AuthContext, require_editor
from cellar.application.screening._dose_response_config_serde import (
    serialize_dose_response_config,
)
from cellar.application.screening._dr_point_reconstruction import (
    build_points_with_exclusions,
)
from cellar.application.shared.command import Command
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.screening_assay.curve_fitting import CurveFittingService
from cellar.domain.screening_assay.data_lock_guard import DataLockGuard
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveType, HillSlopeConstraint, ReadoutDataType
from cellar.domain.screening_assay.excluded_point_detail import (
    ExcludedPointDetail,
    ExclusionReason,
    ExclusionSource,
)
from cellar.domain.screening_assay.repository import (
    DoseResponseCurveRepository,
    ProtocolRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ExclusionPayloadEntry:
    """One entry in the rich Sprint-2 exclusion payload.

    Sprint 1 callers used ``excluded_point_indices: list[int]`` — a bare list
    of indices. Sprint 2 carries full audit-grade context per point so the
    persisted ``ExcludedPointDetail`` can distinguish manual exclusions from
    auto-3σ suggestions (and so the AuditOperation captures the before/after
    for every point).

    ``idx`` is ``None`` for legacy entries with no positional anchor; modern
    Sprint-2 entries always carry their ascending-by-dose index.
    """

    idx: int | None
    source: ExclusionSource
    excluded: bool
    reason: ExclusionReason
    note: str | None = None
    concentration: float | None = None
    response: float | None = None


@dataclass(frozen=True, kw_only=True)
class RefitDoseResponseCurveCommand(Command):
    workspace_id: uuid.UUID
    curve_id: uuid.UUID
    # ---- Sprint 1 legacy path (bare index list) -------------------------
    excluded_point_indices: list[int] = field(default_factory=list)
    hill_slope_constraint: str | None = None
    top_constraint: float | None = None
    bottom_constraint: float | None = None
    # Per-curve range overrides — bidirectional with respect to the protocol's
    # config: protocol Range → per-curve Lock or per-curve Range, and vice
    # versa. ``override_top``/``bottom``/``hill`` is True when the field block
    # below is the authoritative source for that param on this refit.
    override_top: bool = False
    top_constraint_min: float | None = None
    top_constraint_max: float | None = None
    override_bottom: bool = False
    bottom_constraint_min: float | None = None
    bottom_constraint_max: float | None = None
    override_hill: bool = False
    hill_slope_min: float | None = None
    hill_slope_max: float | None = None
    # When True, the use case forces ``DoseResponseConfig.outlier_sigma=None``
    # so the fitter does NOT run its auto-3σ outlier pass on top of the
    # user-supplied ``excluded_point_indices``. The FE sets this during
    # point-editing sessions to prevent the cascade where excluding one point
    # by hand triggers additional auto-exclusions.
    disable_auto_outliers: bool = False
    # ---- Sprint 2 rich payload + audit context --------------------------
    # When ``exclusions`` is provided the use case:
    #   * persists ``ExcludedPointDetail`` entries on the curve (manual
    #     exclusions get ``author_id``+timestamp; AUTO_3SIGMA suggestions are
    #     preserved as ``excluded=False``);
    #   * forces ``outlier_sigma=None`` unconditionally (Sprint 2 chemists
    #     control selection — no silent cascade);
    #   * creates an ``AuditOperation`` of type ``CURVE_POINT_EXCLUSION``;
    #   * REQUIRES ``auth`` (the audit row has no defensible author otherwise).
    exclusions: list[ExclusionPayloadEntry] | None = None
    save_reason: ExclusionReason | None = None
    save_note: str | None = None


def _build_excluded_points_from_payload(
    payload: list[ExclusionPayloadEntry],
    *,
    author_id: uuid.UUID,
    now: datetime,
) -> list[ExcludedPointDetail]:
    """Translate Sprint-2 wire entries to ``ExcludedPointDetail`` for persistence.

    Manual rows get ``author_id``+``ts`` stamped here (the wire shape doesn't
    carry these — the BE is the trusted source for who/when). AUTO_3SIGMA
    rows have no author_id (the fitter wrote them).
    """
    out: list[ExcludedPointDetail] = []
    for entry in payload:
        if entry.source == ExclusionSource.MANUAL:
            stamped_author: uuid.UUID | None = author_id
        else:
            stamped_author = None
        out.append(
            ExcludedPointDetail(
                idx=entry.idx,
                source=entry.source,
                excluded=entry.excluded,
                reason=entry.reason,
                author_id=stamped_author,
                ts=now,
                note=entry.note,
                concentration=entry.concentration,
                response=entry.response,
            )
        )
    return out


def _serialize_excluded_points_for_audit(
    points: list[ExcludedPointDetail] | None,
) -> str:
    """Serialize an excluded-points list to a stable JSON string for audit storage.

    AuditEntry.old_value/new_value are typed ``str | None``; we render the
    list as JSON-stable text so diffs in the audit log are diff-friendly.
    """
    if not points:
        return json.dumps([])
    return json.dumps(
        [p.to_jsonb() for p in points],
        sort_keys=True,
        default=str,
    )


class RefitDoseResponseCurve:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        curve_repo: DoseResponseCurveRepository,
        protocol_repo: ProtocolRepository,
        curve_fitter: CurveFittingService,
        guard: DataLockGuard,
        audit: AuditRecordingService,
    ) -> None:
        self._uow = uow
        self._curve_repo = curve_repo
        self._protocol_repo = protocol_repo
        self._curve_fitter = curve_fitter
        self._guard = guard
        self._audit = audit

    async def __call__(
        self, input: RefitDoseResponseCurveCommand, auth: AuthContext | None = None
    ) -> Result[DoseResponseCurve, DomainError]:
        require_editor(auth)

        # Sprint 2 path REQUIRES an authenticated user — the AuditOperation
        # has no defensible author otherwise. Sprint 1 path is unchanged
        # (workers / system calls may still legitimately pass ``auth=None``).
        if input.exclusions is not None and auth is None:
            return Failure(
                ValidationError(
                    "rich exclusions payload requires an authenticated user"
                )
            )

        async with self._uow:
            curve = await self._curve_repo.find_by_id_in_workspace(
                input.workspace_id, input.curve_id
            )
            if curve is None:
                return Failure(NotFoundError("DoseResponseCurve", str(input.curve_id)))

            try:
                await self._guard.guard_write(input.workspace_id, curve.run_id)
            except DomainError as exc:
                return Failure(exc)

            # Capture the pre-edit ``excluded_points`` for audit diff (only
            # used on the Sprint-2 path; cheap to capture either way).
            old_excluded_points = list(curve.excluded_points or [])

            # Derive ``excluded_indices`` for point reconstruction. Sprint 2
            # callers list every point's state (excluded + reason); we keep
            # only the actually-excluded indices for the fitter.
            if input.exclusions is not None:
                excluded_indices = [
                    e.idx
                    for e in input.exclusions
                    if e.excluded and e.idx is not None
                ]
            else:
                excluded_indices = input.excluded_point_indices

            # Reconstruct all points from raw_data + excluded_points via the
            # shared helper. Preview and commit MUST use the same reconstruction
            # — otherwise the FE sees a different fit on Save than during edit.
            points = build_points_with_exclusions(curve, excluded_indices)

            config = await self._resolve_config(input, curve)

            fit_result = self._curve_fitter.fit(points, config)
            if isinstance(fit_result, Failure):
                return fit_result

            fitted = fit_result.unwrap()

            # Decide which ``excluded_points`` shape goes on the curve. On
            # the Sprint-2 path we trust the chemist's full payload (with
            # audit metadata); on Sprint-1 we fall back to whatever the
            # fitter wrote (legacy dict shape).
            new_excluded_points: list[ExcludedPointDetail] | None
            if input.exclusions is not None:
                assert auth is not None  # checked above
                new_excluded_points = _build_excluded_points_from_payload(
                    input.exclusions,
                    author_id=auth.user_id,
                    now=datetime.now(UTC),
                )
            else:
                new_excluded_points = fitted.excluded_points  # legacy dict shape

            curve.update_fit(
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
                excluded_points=new_excluded_points,
                fit_quality_warnings=fitted.fit_quality_warnings,
                intercept_values=fitted.intercept_values,
                dose_response_config_snapshot=serialize_dose_response_config(config),
            )

            await self._curve_repo.save(curve)

            # Sprint-2 path: append an AuditOperation atomically to the same
            # transaction so audit failure rolls back the refit. Sprint-1
            # callers don't audit (their contract is unchanged).
            if input.exclusions is not None:
                assert auth is not None
                save_reason = (
                    input.save_reason.value if input.save_reason else "unspecified"
                )
                save_note = input.save_note or ""
                await self._audit.record(
                    workspace_id=input.workspace_id,
                    operation_type=OperationType.CURVE_POINT_EXCLUSION,
                    entity_type="DoseResponseCurve",
                    entity_id=curve.id,
                    user_id=auth.user_id,
                    entries=[
                        AuditEntry(
                            entity_type="DoseResponseCurve",
                            entity_id=curve.id,
                            field_name="excluded_points",
                            action=AuditAction.UPDATE,
                            old_value=_serialize_excluded_points_for_audit(
                                old_excluded_points
                            ),
                            new_value=_serialize_excluded_points_for_audit(
                                new_excluded_points
                            ),
                        )
                    ],
                    reason=f"{save_reason}: {save_note}".rstrip(": "),
                    session=self._uow.session,
                )

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
                curve_type=curve.curve_type
                if isinstance(curve.curve_type, CurveType)
                else CurveType(curve.curve_type),
                x_readout_name="Concentration",
                y_readout_name="Response",
            )

        # Per-param override semantics: when ``override_<param>`` is True the
        # client is the authoritative source — its lock/range fields replace
        # the protocol's, including the case "Free" (all override fields None).
        # When False, the protocol's config carries through unchanged.
        if input.override_top:
            top_lock = input.top_constraint
            top_min = input.top_constraint_min
            top_max = input.top_constraint_max
        elif input.top_constraint is not None:
            # Legacy: client sent only ``top_constraint`` without the override
            # flag. Treat as Lock override (back-compat with pre-Phase-B clients).
            top_lock = input.top_constraint
            top_min = None
            top_max = None
        else:
            top_lock = base_config.top_constraint
            top_min = base_config.top_constraint_min
            top_max = base_config.top_constraint_max

        if input.override_bottom:
            bottom_lock = input.bottom_constraint
            bottom_min = input.bottom_constraint_min
            bottom_max = input.bottom_constraint_max
        elif input.bottom_constraint is not None:
            bottom_lock = input.bottom_constraint
            bottom_min = None
            bottom_max = None
        else:
            bottom_lock = base_config.bottom_constraint
            bottom_min = base_config.bottom_constraint_min
            bottom_max = base_config.bottom_constraint_max

        if input.override_hill:
            hill_enum = (
                HillSlopeConstraint(input.hill_slope_constraint)
                if input.hill_slope_constraint
                else HillSlopeConstraint.UNCONSTRAINED
            )
            hill_min = input.hill_slope_min
            hill_max = input.hill_slope_max
        elif input.hill_slope_constraint:
            hill_enum = HillSlopeConstraint(input.hill_slope_constraint)
            hill_min = None
            hill_max = None
        else:
            hill_enum = base_config.hill_slope_constraint
            hill_min = base_config.hill_slope_min
            hill_max = base_config.hill_slope_max

        # Sprint-2 callers (rich ``exclusions`` payload) ALWAYS suppress
        # auto-3σ — the chemist has hand-curated the selection set and the
        # fitter must not cascade more exclusions on top. Sprint-1 callers
        # opt in via the explicit ``disable_auto_outliers`` flag.
        if input.exclusions is not None or input.disable_auto_outliers:
            outlier_sigma = None
        else:
            outlier_sigma = base_config.outlier_sigma

        return DoseResponseConfig(
            curve_type=base_config.curve_type,
            x_readout_name=base_config.x_readout_name,
            y_readout_name=base_config.y_readout_name,
            hill_slope_constraint=hill_enum,
            activity_threshold=base_config.activity_threshold,
            normalization_scope=base_config.normalization_scope,
            top_constraint=top_lock,
            bottom_constraint=bottom_lock,
            top_constraint_min=top_min,
            top_constraint_max=top_max,
            bottom_constraint_min=bottom_min,
            bottom_constraint_max=bottom_max,
            hill_slope_min=hill_min,
            hill_slope_max=hill_max,
            outlier_sigma=outlier_sigma,
        )
