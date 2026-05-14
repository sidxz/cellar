"""Channel resolution — turns source candidates into a CampaignMeasurement.

ChannelResolver is the pure-domain (application-layer) service that
applies the channel's QC filter, qualifier handling, and selection rule
to a list of candidates fetched by a ChannelResolutionQuery port. The
infrastructure-layer SQL implementation of the port lives in
``cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query``.

Selection rules:
- LATEST_APPROVED_RUN: pick the candidate with the largest run_date and
  carry its value/qualifier/source FKs into the measurement.
- MEAN_ACROSS_RUNS: arithmetic mean of candidate values; qualifier=EQ.
- GEOMETRIC_MEAN: log-space mean over strictly positive candidate values.
- MANUAL_PICK: leaves the cell as ND so the user can fill it.

Empty candidates yield an ND measurement (no value, no hit_call). The
domain invariant requires a non-empty ``unit`` even for ND cells, so a
single-char placeholder is used when no candidate is available to
contribute one.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.hit_criterion import HitCriterion

# Placeholder unit used for ND cells when no candidate is available to
# contribute one. The domain forbids empty units; this keeps invariants
# satisfied without inventing a unit we don't actually know.
_ND_UNIT_PLACEHOLDER = "-"


@dataclass(frozen=True)
class ResolvedCandidate:
    """A single source row already coerced to a numeric value + qualifier.

    Produced by ChannelResolutionQuery implementations (typically a SQL
    join across run + protocol + curve/readout_data). The resolver is
    indifferent to source kind — by the time it sees candidates, they
    look uniform.

    ``curve_class`` and the curve-shape fields are only meaningful for
    dose_response_curve-sourced candidates (None for readout_data-sourced).
    The curve-shape fields are populated so the resolver can freeze a
    full ``curve_snapshot`` onto the CampaignMeasurement at import time.
    """

    value: float
    qualifier: ValueQualifier
    unit: str
    run_id: uuid.UUID
    run_date: date | None
    run_approved: bool
    z_prime: float | None
    protocol_name: str
    protocol_version: int
    curve_id: uuid.UUID | None
    readout_id: uuid.UUID | None
    curve_class: str | None = None
    # DR-curve shape — populated only for source_kind=dose_response_curve;
    # the resolver packs these into a curve_snapshot dict on the measurement.
    curve_top: float | None = None
    curve_bottom: float | None = None
    curve_hill_slope: float | None = None
    curve_r_squared: float | None = None
    curve_raw_data: list[dict] | None = None
    curve_excluded_points: list[dict] | None = None
    #: JSONB shape: ``[{"spec": {"kind": "ec", "level": 50.0, ...},
    #: "value": 1.23, "at_bound": false, ...}, ...]``. Populated only for
    #: dose_response_curve candidates; carries every per-spec intercept
    #: persisted with the fit so an intercept-keyed HitCriterion can read
    #: the right value (e.g. EC90 instead of the primary EC50).
    intercept_values: list[dict] | None = None


@runtime_checkable
class ChannelResolutionQuery(Protocol):
    """Port: returns the raw candidate rows for one (channel, molecule) pair."""

    async def fetch_candidates(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        molecule_id: uuid.UUID,
    ) -> list[ResolvedCandidate]: ...

    async def fetch_candidates_for_runs(
        self,
        *,
        workspace_id: uuid.UUID,
        run_ids: list[uuid.UUID],
        protocol_id: uuid.UUID,
        readout_definition_id: uuid.UUID,
        source_kind: ChannelSourceKind,
        normalization_applied: str | None = None,
    ) -> dict[uuid.UUID, list[ResolvedCandidate]]:
        """Per-molecule candidates restricted to a specific set of runs.

        Used by PreviewRunImport / AddResultsFromRuns to enumerate all molecules
        tested in the selected runs for a given (protocol, readout) pair.
        ``normalization_applied`` filters readout_data rows by their formula
        layer (None = raw; "percent_inhibition" = computed); ignored for
        dose-response curve channels. Returns
        ``dict[molecule_id, list[ResolvedCandidate]]``.
        """
        ...


def _passes_qc(c: ResolvedCandidate, qc: dict | None) -> bool:
    if not qc:
        return True
    if qc.get("require_approved", False) and not c.run_approved:
        return False
    min_z = qc.get("min_z_prime")
    if min_z is not None and (c.z_prime is None or c.z_prime < min_z):
        return False
    return True


def _is_qualified(c: ResolvedCandidate) -> bool:
    return c.qualifier in {ValueQualifier.LT, ValueQualifier.GT}


def _threshold_input_value(
    c: ResolvedCandidate, threshold: HitCriterion | None
) -> float | None:
    """Scalar to compare against ``threshold`` for one candidate.

    Legacy criteria (no ``intercept_key``) read ``c.value`` — for a DR
    channel this equals the curve's primary fitted value, preserving
    historical behavior. Intercept-keyed criteria look up the matching
    ``(kind, level)`` pair in ``c.intercept_values``; missing match (legacy
    fit, intercept added after the curve was fit) yields None.
    """
    if threshold is None or threshold.intercept_key is None:
        return c.value
    ivs = c.intercept_values
    if not ivs:
        return None
    target_kind = threshold.intercept_key.kind
    target_level = threshold.intercept_key.level
    for iv in ivs:
        spec = iv.get("spec") or {}
        if spec.get("kind") == target_kind and spec.get("level") == target_level:
            val = iv.get("value")
            return float(val) if isinstance(val, (int, float)) else None
    return None


def _compute_hit_call(value: float | None, threshold: HitCriterion | None) -> HitCall | None:
    if value is None or threshold is None:
        return None
    op = threshold.operator
    target = threshold.value
    if op == "between":
        if not (isinstance(target, list) and len(target) == 2):
            return None
        low, high = target
        if not (isinstance(low, (int, float)) and isinstance(high, (int, float))):
            return None
        return HitCall.HIT if (low <= value <= high) else HitCall.MISS
    if isinstance(target, list):
        # 'in' operator targets a set of strings — not applicable to a
        # numeric measurement cell. Leave hit_call unset.
        return None
    if op == "lt":
        return HitCall.HIT if value < target else HitCall.MISS
    if op == "lte":
        return HitCall.HIT if value <= target else HitCall.MISS
    if op == "gt":
        return HitCall.HIT if value > target else HitCall.MISS
    if op == "gte":
        return HitCall.HIT if value >= target else HitCall.MISS
    return None


def _nd_measurement(
    *,
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    unit: str,
    protocol_name: str = "",
    protocol_version: int = 0,
) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id,
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit=unit or _ND_UNIT_PLACEHOLDER,
        protocol_name_snapshot=protocol_name or "-",
        protocol_version_snapshot=protocol_version,
        hit_call=None,
    )


def _condense_curve_points(
    raw: list[dict] | None,
) -> list[dict] | None:
    """Convert raw_data items to ``{x, y, ...}`` for FE consumption.

    Accepts both legacy ``{concentration, response}`` and modern ``{x, y}``
    shapes; preserves every other field (is_excluded, is_outlier,
    replicate_count, …) so the campaign rendering matches what the
    protocol Activity tab draws.
    """
    if not raw:
        return None
    out: list[dict] = []
    for pt in raw:
        if not isinstance(pt, dict):
            continue
        item: dict = dict(pt)  # shallow copy so we don't mutate the JSONB
        if "x" not in item and "concentration" in item:
            item["x"] = item.pop("concentration")
        if "y" not in item and "response" in item:
            item["y"] = item.pop("response")
        out.append(item)
    return out


def _build_curve_snapshot(c: ResolvedCandidate) -> dict | None:
    """Freeze a DR candidate's full curve shape into a JSONB-able dict.

    Returns None when the candidate has no curve shape (readout_data
    sources, or a defensive fallback when the SQL didn't populate the
    extra columns). The shape mirrors what the frontend's shared
    DoseResponseFigure component expects, so the campaign drawing is
    reproducible from this dict alone without a live FK lookup.
    """
    if c.curve_top is None or c.curve_bottom is None or c.curve_hill_slope is None:
        return None
    snap: dict = {
        "fitted_value": c.value,
        "top": c.curve_top,
        "bottom": c.curve_bottom,
        "hill_slope": c.curve_hill_slope,
        "r_squared": c.curve_r_squared,
        "curve_class": c.curve_class,
        "raw_data": _condense_curve_points(c.curve_raw_data) or [],
    }
    excluded = _condense_curve_points(c.curve_excluded_points)
    if excluded:
        snap["excluded_points"] = excluded
    return snap


class ChannelResolver:
    """Application service that resolves one (channel, molecule) cell."""

    def __init__(self, query: ChannelResolutionQuery) -> None:
        self._q = query

    async def resolve(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        result_id: uuid.UUID,
        molecule_id: uuid.UUID,
    ) -> CampaignMeasurement:
        candidates = await self._q.fetch_candidates(
            workspace_id=workspace_id, channel=channel, molecule_id=molecule_id
        )
        candidates = [c for c in candidates if _passes_qc(c, channel.qc_filter)]
        if channel.qualifier_handling == QualifierHandling.EXCLUDE_QUALIFIED:
            candidates = [c for c in candidates if not _is_qualified(c)]

        if not candidates:
            return _nd_measurement(
                result_id=result_id,
                channel_id=channel.id,
                unit=_ND_UNIT_PLACEHOLDER,
            )

        unit = candidates[0].unit or _ND_UNIT_PLACEHOLDER
        pname = candidates[0].protocol_name
        pver = candidates[0].protocol_version

        if channel.selection_rule == SelectionRule.LATEST_APPROVED_RUN:
            pick = max(candidates, key=lambda c: c.run_date or date.min)
            value = pick.value
            qualifier = pick.qualifier
            source_run = pick.run_id
            curve = pick.curve_id
            readout = pick.readout_id
            pname = pick.protocol_name
            pver = pick.protocol_version
            rdate = pick.run_date
            unit = pick.unit or _ND_UNIT_PLACEHOLDER
            eval_value = _threshold_input_value(pick, channel.hit_threshold)
        elif channel.selection_rule == SelectionRule.MEAN_ACROSS_RUNS:
            vals = [c.value for c in candidates]
            value = sum(vals) / len(vals)
            qualifier = ValueQualifier.EQ
            source_run = curve = readout = None
            rdate = None
            # Snapshot from the latest-run candidate as a representative
            # curve shape — the aggregate value can't be a sigmoid, but a
            # drawing still needs *something* to render.
            pick = max(candidates, key=lambda c: c.run_date or date.min)
            eval_pool = [_threshold_input_value(c, channel.hit_threshold) for c in candidates]
            eval_pool = [v for v in eval_pool if v is not None]
            eval_value = sum(eval_pool) / len(eval_pool) if eval_pool else None
        elif channel.selection_rule == SelectionRule.GEOMETRIC_MEAN:
            positives = [c.value for c in candidates if c.value > 0]
            if not positives:
                return _nd_measurement(
                    result_id=result_id,
                    channel_id=channel.id,
                    unit=unit,
                    protocol_name=pname,
                    protocol_version=pver,
                )
            value = math.exp(sum(math.log(v) for v in positives) / len(positives))
            qualifier = ValueQualifier.EQ
            source_run = curve = readout = None
            rdate = None
            pick = max(candidates, key=lambda c: c.run_date or date.min)
            eval_pool = [_threshold_input_value(c, channel.hit_threshold) for c in candidates]
            eval_positives = [v for v in eval_pool if v is not None and v > 0]
            eval_value = (
                math.exp(sum(math.log(v) for v in eval_positives) / len(eval_positives))
                if eval_positives
                else None
            )
        else:  # MANUAL_PICK — user fills in later; cell stays ND.
            return _nd_measurement(
                result_id=result_id,
                channel_id=channel.id,
                unit=unit,
                protocol_name=pname,
                protocol_version=pver,
            )

        return CampaignMeasurement(
            result_id=result_id,
            channel_id=channel.id,
            value=value,
            value_qualifier=qualifier,
            unit=unit,
            hit_call=_compute_hit_call(eval_value, channel.hit_threshold),
            source_run_id=source_run,
            source_curve_id=curve,
            source_readout_id=readout,
            protocol_name_snapshot=pname,
            protocol_version_snapshot=pver,
            run_date_snapshot=rdate,
            curve_snapshot=_build_curve_snapshot(pick),
        )
