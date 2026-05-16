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

import uuid
from typing import Protocol, runtime_checkable

from cellar.application.screening.run_aggregation import (
    ResolvedRun,
    _max_dose_from_raw,
    apply_selection_rule,
)
from cellar.application.screening.run_aggregation import (
    intercept_scalar as _intercept_scalar,
)
from cellar.application.screening.run_aggregation import (
    resolve_intercept as _resolve_intercept,
)
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    HitCall,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.hit_criterion import HitCriterion

# Back-compat alias — channel_resolution callers still type ResolvedCandidate.
# Remove in a follow-up commit once consumers migrate.
ResolvedCandidate = ResolvedRun

# Public surface + intentionally re-exported helpers. The leading-underscore
# names below are re-exported so existing callers (preview_run_import,
# add_results_from_runs, scripts/rebuild_campaign_curve_snapshots, and the
# channel_resolver test module) can keep importing them from this module
# without an SDK-style migration. Without ``__all__``, ruff's --fix would
# strip these on the next sweep.
__all__ = [
    "ChannelResolutionQuery",
    "ChannelResolver",
    "ResolvedCandidate",
    # Re-exported for tests / channel-side callers
    "_build_curve_snapshot",
    "_compute_hit_call",
    "_intercept_scalar",
    "_max_dose_from_raw",
    "_resolve_intercept",
]

# Placeholder unit used for ND cells when no candidate is available to
# contribute one. The domain forbids empty units; this keeps invariants
# satisfied without inventing a unit we don't actually know.
_ND_UNIT_PLACEHOLDER = "-"


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
    return not (min_z is not None and (c.z_prime is None or c.z_prime < min_z))


def _threshold_input_value(
    c: ResolvedCandidate, threshold: HitCriterion | None
) -> float | None:
    """Back-compat shim: scalar for the threshold's intercept_key.

    Pre-Option-A callers pass a ``HitCriterion`` whose ``intercept_key``
    carried the channel's intercept identity. Post-Option-A, channel
    identity lives on the channel itself; this shim still exists for
    protocol-level criterion evaluation paths that haven't been
    rewired (e.g. evaluating ``recommended_hit_criteria`` outside of a
    campaign channel).
    """
    return _intercept_scalar(c, threshold.intercept_key if threshold else None)


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
    # Extra fields the FE <DoseResponseChart> reads. Without these the
    # campaign's expand-dialog would lose the secondary intercept chips,
    # CI strip, and fit-warning badges that the search + protocol-runs
    # surfaces already show. None values are preserved on the wire so the
    # FE can distinguish "not yet fit" from "0".
    if c.curve_type is not None:
        snap["curve_type"] = c.curve_type
    if c.curve_confidence_interval_low is not None:
        snap["confidence_interval_low"] = c.curve_confidence_interval_low
    if c.curve_confidence_interval_high is not None:
        snap["confidence_interval_high"] = c.curve_confidence_interval_high
    if c.intercept_values:
        snap["intercept_values"] = c.intercept_values
    if c.curve_fit_quality_warnings:
        snap["fit_quality_warnings"] = c.curve_fit_quality_warnings
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

        if not candidates:
            return _nd_measurement(
                result_id=result_id,
                channel_id=channel.id,
                unit=_ND_UNIT_PLACEHOLDER,
            )

        ik = channel.intercept_key
        result = apply_selection_rule(
            candidates,
            channel.selection_rule,
            channel.qualifier_handling,
            ik,
        )

        if result.value is None:
            # The aggregator returned ND (all candidates dropped, MANUAL_PICK,
            # or aggregate produced no positives). Use the representative run
            # if any to carry protocol metadata onto the ND cell.
            rep = result.representative_run or candidates[0]
            return _nd_measurement(
                result_id=result_id,
                channel_id=channel.id,
                unit=rep.unit or _ND_UNIT_PLACEHOLDER,
                protocol_name=rep.protocol_name,
                protocol_version=rep.protocol_version,
            )

        pick = result.representative_run
        assert pick is not None  # value-Some implies representative-Some

        # The candidate's wire-level qualifier (e.g. ">100 µM" detection
        # limit on a readout) is overridden by the resolver-derived
        # qualifier (ND from inactive, GT from at_bound). Otherwise carry it
        # through.
        qualifier = (
            result.qualifier
            if result.qualifier != ValueQualifier.EQ
            else pick.qualifier
        )

        # Aggregate modes (mean / geometric_mean) don't have a single source
        # run / curve to pin onto the measurement — the value is synthesized.
        is_aggregate = channel.selection_rule in {
            SelectionRule.MEAN_ACROSS_RUNS,
            SelectionRule.GEOMETRIC_MEAN,
        }
        source_run = None if is_aggregate else pick.run_id
        source_curve = None if is_aggregate else pick.curve_id
        source_readout = None if is_aggregate else pick.readout_id

        return CampaignMeasurement(
            result_id=result_id,
            channel_id=channel.id,
            value=result.value,
            value_qualifier=qualifier,
            unit=pick.unit or _ND_UNIT_PLACEHOLDER,
            hit_call=_compute_hit_call(result.value, channel.hit_threshold),
            source_run_id=source_run,
            source_curve_id=source_curve,
            source_readout_id=source_readout,
            protocol_name_snapshot=pick.protocol_name,
            protocol_version_snapshot=pick.protocol_version,
            run_date_snapshot=pick.run_date,
            curve_snapshot=_build_curve_snapshot(pick),
        )
