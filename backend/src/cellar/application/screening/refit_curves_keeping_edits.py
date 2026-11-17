"""RefitCurvesKeepingEdits: refit a run's dose-response curves after its readout rows
changed, keeping what chemists did to each curve.

A chemist's work on a curve lives on the curve, not on the readout rows: points excluded
by hand (with their reason), an accepted 3σ suggestion, the curve's own fit constraints.
A change to the rows (an outlier flag that moves the normalization anchors or takes a
well out) must not throw it away. Given the rows before and after the change, each curve
of a (compound, batch) series whose points changed is refitted in place (same id) with
its own settings (its config snapshot) and its exclusions carried to the same wells; a
well flagged as an outlier is left out as a well flag. A series left with fewer than
four doses loses its curve; one that gained enough gets a curve with the protocol's
settings. Every other curve stays as it is.

ponytail: series and layer selection mirror ``FitDoseResponseCurves._fit``; fold the two
together when that module can take a refit scope.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace

from returns.result import Failure

from cellar.application.screening._dose_response_config_serde import (
    deserialize_dose_response_config,
    serialize_dose_response_config,
)
from cellar.application.screening.fit_dose_response import _build_excluded_from_fitter
from cellar.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    CurveFittingService,
)
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import (
    ReadoutDataType,
    WellType,
    primary_normalization,
)
from cellar.domain.screening_assay.excluded_point_detail import (
    ExcludedPointDetail,
    ExclusionSource,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.repository import DoseResponseCurveRepository
from cellar.domain.screening_assay.run import Run

_MIN_DOSES = 4

# (molecule, batch) -> well -> (dose, value, flagged as an outlier)
Series = dict[tuple[uuid.UUID, uuid.UUID], dict[uuid.UUID, tuple[float, float, bool]]]


@dataclass
class CurveRefitOutcome:
    refitted: int = 0
    created: int = 0
    removed: int = 0  # fewer than four doses left, or the fit failed
    exclusions_dropped: int = 0  # an excluded point that no longer names a well of the run
    failed: list[str] = field(default_factory=list)

    def warning(self) -> str | None:
        """What the chemist must hear: curves removed or exclusions that could not stay."""
        parts = []
        if self.removed:
            parts.append(
                f"{_n(self.removed, 'curve')} removed: fewer than {_MIN_DOSES} doses "
                "left in the fit, or the fit failed"
            )
        if self.exclusions_dropped:
            parts.append(
                f"{_n(self.exclusions_dropped, 'excluded point')} no longer matched a well "
                "and could not be kept"
            )
        return "; ".join(parts) or None


def _n(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class RefitCurvesKeepingEdits:
    def __init__(
        self, *, curve_repo: DoseResponseCurveRepository, curve_fitter: CurveFittingService
    ) -> None:
        self._curve_repo = curve_repo
        self._curve_fitter = curve_fitter

    async def refit(
        self,
        *,
        run: Run,
        protocol: Protocol,
        before: list[ReadoutData],
        after: list[ReadoutData],
        only_changed: bool = True,
    ) -> CurveRefitOutcome:
        """Refit the curves of series whose points differ between ``before`` and
        ``after`` (every series with ``only_changed=False``), keeping their edits."""
        out = CurveRefitOutcome()
        rd_by_name = {rd.name: rd for rd in protocol.readout_definitions}
        curves = await self._curve_repo.find_by_run(run.workspace_id, run.id)
        for dr_def in protocol.readout_definitions:
            config = dr_def.dose_response_config
            if dr_def.data_type != ReadoutDataType.DOSE_RESPONSE or config is None:
                continue
            y_rd = rd_by_name.get(config.y_readout_name)
            if y_rd is None or y_rd.is_calculated:
                continue  # formula values are per compound: never a curve on wells
            layer = (
                str(config.y_normalization or primary_normalization(y_rd.normalizations))
                if y_rd.normalizations
                else None
            )
            on_wells, new = _series(run, y_rd, layer, after)
            if not on_wells:
                continue  # rows on no well of the run: their curves cannot be rebuilt
            _, old = _series(run, y_rd, layer, before)
            existing = {
                (c.molecule_id, c.batch_id): c
                for c in curves
                if c.readout_definition_id == dr_def.id
            }
            for key in sorted(set(old) | set(new) | set(existing), key=str):
                if only_changed and _same(old.get(key), new.get(key)):
                    continue
                curve = existing.get(key)
                points = new.get(key)
                if points is None:
                    if curve is not None:  # no sample well left: no curve
                        await self._curve_repo.delete(run.workspace_id, curve.id)
                        out.removed += 1
                    continue
                await self._refit_one(out, run, dr_def, key, curve, old.get(key, {}), points)
        return out

    async def _refit_one(
        self,
        out: CurveRefitOutcome,
        run: Run,
        dr_def: ReadoutDefinition,
        key: tuple[uuid.UUID, uuid.UUID],
        curve: DoseResponseCurve | None,
        old: dict[uuid.UUID, tuple[float, float, bool]],
        new: dict[uuid.UUID, tuple[float, float, bool]],
    ) -> None:
        kept = _kept_exclusions(curve, old) if curve is not None else {}
        if curve is not None:
            out.exclusions_dropped += _edits(curve) - len(kept)
        order = sorted(new, key=lambda w: new[w][0])
        points = [
            ConcentrationResponsePoint(
                concentration=new[w][0],
                response=new[w][1],
                is_excluded=new[w][2] or w in kept,
            )
            for w in order
        ]
        doses = {p.concentration for p in points if p.concentration > 0 and not p.is_excluded}
        if len(doses) < _MIN_DOSES:
            if curve is not None:
                await self._curve_repo.delete(run.workspace_id, curve.id)
                out.removed += 1
            return

        assert dr_def.dose_response_config is not None
        config = (
            deserialize_dose_response_config(curve.dose_response_config_snapshot)
            if curve is not None and curve.dose_response_config_snapshot
            else dr_def.dose_response_config
        )
        fit = self._curve_fitter.fit(points, config)
        if isinstance(fit, Failure):
            if curve is not None:
                await self._curve_repo.delete(run.workspace_id, curve.id)
                out.removed += 1
            return
        fitted = fit.unwrap()
        excluded = _carry(
            _build_excluded_from_fitter(fitted),
            [(new[w][0], new[w][1], kept[w]) for w in order if w in kept and not new[w][2]],
        )
        fields = {
            "fitted_value": fitted.fitted_value,
            "hill_slope": fitted.hill_slope,
            "top": fitted.top,
            "bottom": fitted.bottom,
            "r_squared": fitted.r_squared,
            "confidence_interval_low": fitted.confidence_interval_low,
            "confidence_interval_high": fitted.confidence_interval_high,
            "num_points": fitted.num_points,
            "curve_class": fitted.curve_class,
            "raw_data": fitted.raw_data,
            "excluded_points": excluded,
            "fit_quality_warnings": list(fitted.fit_quality_warnings),
            "intercept_values": list(fitted.intercept_values),
            "dose_response_config_snapshot": serialize_dose_response_config(config),
        }
        if curve is not None:
            curve.update_fit(**fields)
            out.refitted += 1
        else:
            curve = DoseResponseCurve(
                workspace_id=run.workspace_id,
                molecule_id=key[0],
                batch_id=key[1],
                protocol_id=run.protocol_id,
                run_id=run.id,
                readout_definition_id=dr_def.id,
                curve_type=config.curve_type,
                **fields,
            )
            out.created += 1
        await self._curve_repo.save(curve)


def _series(
    run: Run, y_rd: ReadoutDefinition, layer: str | None, rows: list[ReadoutData]
) -> tuple[bool, Series]:
    """Whether any row of the layer sits on a well of the run, and the sample-well
    points of each (compound, batch) on it — the rows a curve is fitted from."""
    wells = {w.id: w for w in run.wells}
    on_wells = False
    series: Series = defaultdict(dict)
    for r in rows:
        if r.readout_definition_id != y_rd.id or r.is_computed != (layer is not None):
            continue
        if layer is not None and r.normalization_applied != layer:
            continue
        well = wells.get(r.well_id) if r.well_id is not None else None
        if well is None:
            continue
        on_wells = True
        if r.value is None or r.molecule_id is None or r.batch_id is None:
            continue
        if well.dose is None or well.well_type != WellType.SAMPLE:
            continue
        series[(r.molecule_id, r.batch_id)][well.id] = (well.dose, r.value.value, r.is_outlier)
    return on_wells, dict(series)


def _same(
    a: dict[uuid.UUID, tuple[float, float, bool]] | None,
    b: dict[uuid.UUID, tuple[float, float, bool]] | None,
) -> bool:
    """The same points: wells, doses and flags equal, values up to float noise (anchor
    means summed in another order)."""
    if a is None or b is None or a.keys() != b.keys():
        return a == b
    return all(
        a[w][0] == b[w][0] and a[w][2] == b[w][2] and math.isclose(a[w][1], b[w][1], abs_tol=1e-9)
        for w in a
    )


def _edits(curve: DoseResponseCurve) -> int:
    """The curve's exclusions a chemist made: by hand, or an accepted 3σ suggestion."""
    return sum(
        1
        for e in curve.excluded_points or []
        if e.excluded and e.source != ExclusionSource.WELL_FLAG
    )


def _kept_exclusions(
    curve: DoseResponseCurve, old: dict[uuid.UUID, tuple[float, float, bool]]
) -> dict[uuid.UUID, ExcludedPointDetail]:
    """The curve's chemist-made exclusions, each matched to the well whose point it was."""
    kept: dict[uuid.UUID, ExcludedPointDetail] = {}
    for e in curve.excluded_points or []:
        if not e.excluded or e.source == ExclusionSource.WELL_FLAG:
            continue
        if e.concentration is None or e.response is None:
            continue
        well = next(
            (
                w
                for w, (dose, value, _) in old.items()
                if w not in kept
                and math.isclose(dose, e.concentration)
                and math.isclose(value, e.response)
            ),
            None,
        )
        if well is not None:
            kept[well] = e
    return kept


def _carry(
    entries: list[ExcludedPointDetail],
    kept: list[tuple[float, float, ExcludedPointDetail]],
) -> list[ExcludedPointDetail]:
    """The fitter records every left-out point as a well flag; a point the chemist
    excluded takes back its own entry (source, reason, note, author) at its new value."""
    pending: dict[tuple[float, float], list[ExcludedPointDetail]] = defaultdict(list)
    for dose, value, e in kept:
        pending[(dose, value)].append(e)
    out = []
    for e in entries:
        own = pending.get((e.concentration, e.response))  # type: ignore[arg-type]
        if e.source == ExclusionSource.WELL_FLAG and own:
            o = own.pop()
            e = replace(
                e, source=o.source, reason=o.reason, author_id=o.author_id, ts=o.ts, note=o.note
            )
        out.append(e)
    return out
