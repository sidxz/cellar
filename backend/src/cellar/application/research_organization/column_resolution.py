"""Column resolution — one bulk resolver from candidate readings to campaign cells.

``ColumnResolver`` is pure: the caller fetches every candidate of one column in one
``ColumnCandidateQuery.fetch`` call and hands them over (never one query per cell).

Readout (single-point) columns follow spec §6.4:

1. A compound's readings group by (run, concentration). The concentration is already
   resolved on each ``Candidate``; "not recorded" (None) is its own bucket.
2. A group's readings combine through ``combine_replicates``: one value per run and
   concentration, so "latest run" no longer picks one replicate well.
3. A run holding the compound at more than one recorded concentration is a
   concentration series and never feeds a single-point column.
4. The column's rule (``effective_rule(..., single_point=True)``) combines runs only at
   one concentration: the column's ``test_concentration`` when set, otherwise the only
   one there is; several leave the cell untested with ``SEVERAL_CONCENTRATIONS``.

Dose-response columns keep the curve path and the D1 reported-endpoint fallback.

Every value records the facts of the readings behind it (§6.2): contributing runs,
batches, replicate total (null when any part is unrecorded, never a partial sum),
concentration and basis.
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from cellar.application.screening.curve_snapshot import (
    build_aggregate_curve_snapshot,
    build_curve_snapshot,
)
from cellar.application.screening.run_aggregation import (
    ResolvedRun,
    apply_selection_rule,
    combine_replicates,
    effective_rule,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    MeasurementBasis,
    SelectionRule,
    UnresolvedReason,
    ValueQualifier,
)
from cellar.domain.research_organization.measurement_facts import Concentration
from cellar.domain.screening_assay.activity_types import ReplicateStats
from cellar.domain.shared.aggregation_types import QualifierHandling
from cellar.domain.shared.units import comparable_magnitude

_CENSORED = {ValueQualifier.GT, ValueQualifier.LT}
_AGGREGATE_RULES = {SelectionRule.MEAN_ACROSS_RUNS, SelectionRule.GEOMETRIC_MEAN}

# The domain forbids an empty unit, even on an ND cell; this stands in when no
# reading contributes one, without inventing a unit we don't know.
_ND_UNIT_PLACEHOLDER = "-"


@dataclass(frozen=True)
class Candidate:
    """One reading a column can resolve from: screening's ``ResolvedRun`` plus the
    campaign-side facts it doesn't carry (batch, well, dose, replicates; §6.5)."""

    run: ResolvedRun
    molecule_id: uuid.UUID
    batch_id: uuid.UUID | None
    well_id: uuid.UUID | None
    #: Already resolved: the well's dose, else the run's Test concentration, else None.
    dose: Concentration | None
    #: Recorded on a well-less row; None means not recorded (and for wells and curves).
    replicate_count: int | None
    #: The readout definition's replicate aggregation, as ``combine_replicates`` names it.
    aggregation: str = "none"
    #: When the run row was created; breaks a tie between runs of the same ``run_date``.
    run_created_at: datetime | None = None


class ColumnCandidateQuery(Protocol):
    """Port: every candidate of one column, per molecule, in one round trip
    (two for a dose-response column: its curves plus the well-less endpoints, D1)."""

    async def fetch(
        self,
        *,
        workspace_id: uuid.UUID,
        channel: CampaignChannel,
        run_ids: list[uuid.UUID] | None,
        molecule_ids: list[uuid.UUID] | None,
    ) -> dict[uuid.UUID, list[Candidate]]:
        """``run_ids=None`` is protocol-wide; ``molecule_ids=None`` every molecule."""
        ...


def resolution_run_ids(
    campaign: Campaign, channel: CampaignChannel
) -> list[uuid.UUID] | Literal["none"] | None:
    """The runs a column reads (spec §6.3); ``None`` = every run of its protocol.

    ``"none"``: a stage column whose stage has no runs of its protocol. It never falls
    back to protocol-wide; the caller writes ND with ``NO_RUNS_AT_STAGE`` and does not
    query. Compute once per column, not per cell."""
    if channel.resolve_from_all_runs:
        return None
    if channel.stage_id is not None:
        return campaign.stage_run_ids(channel.stage_id, channel.protocol_id) or "none"
    return campaign.campaign_run_ids(channel.protocol_id) or None


@dataclass(frozen=True)
class _Value:
    """One value the column's rule chooses among, with the readings behind it."""

    run: ResolvedRun
    readings: tuple[Candidate, ...]


def _newest_first(values: list[_Value]) -> list[_Value]:
    """Newest run first: ``run_date`` is a date, so same-day runs tie and the one
    created later wins. The rules pick the first of equals, so order is the tie-break."""

    def key(v: _Value) -> tuple[date, datetime]:
        created = v.readings[0].run_created_at
        return (v.run.run_date or date.min, created or datetime.min.replace(tzinfo=UTC))

    return sorted(values, key=key, reverse=True)


def _passes_qc(run: ResolvedRun, qc: dict[str, Any] | None) -> bool:
    if not qc:
        return True
    if qc.get("require_approved", False) and not run.run_approved:
        return False
    min_z = qc.get("min_z_prime")
    return not (min_z is not None and (run.z_prime is None or run.z_prime < min_z))


def _nd_measurement(
    *,
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    unit: str,
    protocol_name: str = "",
    protocol_version: int = 0,
    source: ResolvedRun | None = None,
    pin_source: bool = True,
) -> CampaignMeasurement:
    """An ND cell. ``source`` is the run it was resolved *from*, when one exists: an
    inactive curve, or a fit with no readable intercept.

    Its snapshot (and, with ``pin_source``, its run/curve ids) is what tells "tested,
    no value" from "nothing to resolve": ``CampaignMeasurement.is_tested_nd`` reads
    exactly these fields to call the first a miss and the second untested. The
    aggregate rules pass ``pin_source=False``: they have no single run to point at.
    """
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id,
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit=unit or _ND_UNIT_PLACEHOLDER,
        protocol_name_snapshot=protocol_name or "-",
        protocol_version_snapshot=protocol_version,
        source_run_id=source.run_id if source and pin_source else None,
        source_curve_id=source.curve_id if source and pin_source else None,
        run_date_snapshot=source.run_date if source and pin_source else None,
        curve_snapshot=build_curve_snapshot(source) if source else None,
    )


class ColumnResolver:
    """Resolves one column for many molecules at once. Pure and synchronous."""

    def resolve_column(
        self,
        *,
        channel: CampaignChannel,
        molecule_ids: list[uuid.UUID],
        candidates: dict[uuid.UUID, list[Candidate]],
        result_id_by_molecule: dict[uuid.UUID, uuid.UUID],
    ) -> dict[uuid.UUID, CampaignMeasurement]:
        return {
            mid: _resolve(channel, result_id_by_molecule[mid], candidates.get(mid, []))
            for mid in molecule_ids
        }


def _resolve(
    channel: CampaignChannel, result_id: uuid.UUID, candidates: list[Candidate]
) -> CampaignMeasurement:
    passed = [c for c in candidates if _passes_qc(c.run, channel.qc_filter)]
    if channel.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE:
        # D1 — a QC-passing curve of any class wins, an inactive one included;
        # reported (well-less) endpoints count only when no curve survives QC.
        curves = [c for c in passed if c.run.curve_id is not None]
        chosen = curves or [c for c in passed if c.run.curve_id is None]
        values = [_Value(c.run, (c,)) for c in chosen]
        return _measure(channel, channel.selection_rule, result_id, values, series=True)

    recorded = _readable(_single_point_groups(passed), channel.qualifier_handling)
    found = _concentrations_found(recorded)
    groups = _at_one_concentration(recorded, channel.test_concentration)
    if groups is None:
        m = _nd_measurement(result_id=result_id, channel_id=channel.id, unit=_ND_UNIT_PLACEHOLDER)
        m.unresolved_reason = UnresolvedReason.SEVERAL_CONCENTRATIONS
    else:
        values = [_combine(g) for g in groups]
        unit = values[0].run.unit if values else None
        rule = effective_rule(channel.selection_rule, unit=unit, single_point=True)
        m = _measure(channel, rule, result_id, values, series=False)
    m.concentrations_found = found
    return m


def _single_point_groups(
    candidates: list[Candidate],
) -> dict[tuple[uuid.UUID, Concentration | None], list[Candidate]]:
    """Readings grouped by (run, concentration), concentration-series runs dropped."""
    known: list[Concentration] = []

    def bucket(dose: Concentration | None) -> Concentration | None:
        # One representative per concentration, compared across units.
        if dose is None:
            return None
        for k in known:
            if k.same_as(dose):
                return k
        known.append(dose)
        return dose

    groups: dict[tuple[uuid.UUID, Concentration | None], list[Candidate]] = {}
    for c in candidates:
        groups.setdefault((c.run.run_id, bucket(c.dose)), []).append(c)
    recorded_per_run = Counter(run for run, dose in groups if dose is not None)
    return {k: g for k, g in groups.items() if recorded_per_run[k[0]] < 2}


_Groups = dict[tuple[uuid.UUID, Concentration | None], list[Candidate]]


def _readable(groups: _Groups, handling: QualifierHandling) -> _Groups:
    """The groups the column reads. Under EXCLUDE_QUALIFIED a group of only censored
    readings is never read, so its dose is neither listed nor counted as a second
    concentration."""
    if handling != QualifierHandling.EXCLUDE_QUALIFIED:
        return groups
    return {k: g for k, g in groups.items() if _combine(g).run.qualifier not in _CENSORED}


def _concentrations_found(groups: _Groups) -> list[Concentration]:
    """Distinct known doses of the groups the column reads, by magnitude. Taken
    before the column's ``test_concentration`` so a chosen dose still sees the others."""
    doses = [d for _, d in groups if d is not None]
    out: list[Concentration] = []
    for d in sorted(doses, key=lambda d: comparable_magnitude(d.value, d.unit)):
        if not any(o.same_as(d) for o in out):
            out.append(d)
    return out


def _at_one_concentration(
    groups: _Groups, test_concentration: Concentration | None
) -> list[list[Candidate]] | None:
    """The groups at one concentration: the column's, else the only one there is.
    ``None`` when several remain and the column names none."""
    if test_concentration is not None:
        return [
            g for (_, d), g in groups.items() if d is not None and d.same_as(test_concentration)
        ]
    if len({d for _, d in groups}) > 1:
        return None
    return list(groups.values())


def _combine(readings: list[Candidate]) -> _Value:
    """One (run, concentration) group's readings as that run's value."""
    first = readings[0].run

    def values(q: ValueQualifier) -> list[float]:
        return [c.run.value for c in readings if c.run.qualifier == q and c.run.value is not None]

    eq, gt, lt = values(ValueQualifier.EQ), values(ValueQualifier.GT), values(ValueQualifier.LT)
    positive = [v for v in eq if v > 0]
    stats = ReplicateStats(
        eq_count=len(eq),
        eq_mean=statistics.fmean(eq) if eq else None,
        eq_median=statistics.median(eq) if eq else None,
        eq_min=min(eq, default=None),
        eq_max=max(eq, default=None),
        eq_geomean=statistics.geometric_mean(positive) if positive else None,
        gt_count=len(gt),
        gt_max_bound=max(gt, default=None),
        lt_count=len(lt),
        lt_min_bound=min(lt, default=None),
    )
    value, qualifier = combine_replicates(stats, readings[0].aggregation, unit=first.unit)
    ivs = first.intercept_values
    run = replace(
        first,
        value=value,
        qualifier=qualifier,
        # A group of several readings has no single row to point at.
        readout_id=first.readout_id if len(readings) == 1 else None,
        # Keep the reported-endpoint intercept tag (see ``resolve_intercept``).
        intercept_values=[{**ivs[0], "value": value}] if ivs else None,
    )
    return _Value(run, tuple(readings))


def _measure(
    channel: CampaignChannel,
    rule: SelectionRule,
    result_id: uuid.UUID,
    values: list[_Value],
    *,
    series: bool,
) -> CampaignMeasurement:
    """The column's rule over ``values``, building the cell (snapshot, source pin, ND)."""
    if not values:
        return _nd_measurement(
            result_id=result_id, channel_id=channel.id, unit=_ND_UNIT_PLACEHOLDER
        )
    values = _newest_first(values)
    runs = [v.run for v in values]
    result = apply_selection_rule(runs, rule, channel.qualifier_handling, channel.intercept_key)
    # Aggregate modes have no single source run / curve to pin: the value is synthesized.
    is_aggregate = rule in _AGGREGATE_RULES

    if result.value is None:
        rep = result.representative_run or runs[0]
        if rule == SelectionRule.MANUAL_PICK:
            # No chemist has picked yet: untested, never a miss.
            return _nd_measurement(
                result_id=result_id,
                channel_id=channel.id,
                unit=rep.unit or _ND_UNIT_PLACEHOLDER,
                protocol_name=rep.protocol_name,
                protocol_version=rep.protocol_version,
            )
        m = _nd_measurement(
            result_id=result_id,
            channel_id=channel.id,
            unit=rep.unit or _ND_UNIT_PLACEHOLDER,
            protocol_name=rep.protocol_name,
            protocol_version=rep.protocol_version,
            source=rep,
            pin_source=not is_aggregate,
        )
        return _with_facts(
            m, values if is_aggregate else [v for v in values if v.run is rep], series
        )

    pick = result.representative_run
    assert pick is not None  # value-Some implies representative-Some
    if is_aggregate and result.qualifier == ValueQualifier.EQ:
        snapshot = build_aggregate_curve_snapshot(
            runs,
            aggregate_value=result.value,
            aggregate_label="gmean" if rule == SelectionRule.GEOMETRIC_MEAN else "mean",
        )
    else:
        snapshot = build_curve_snapshot(pick)
    m = CampaignMeasurement(
        result_id=result_id,
        channel_id=channel.id,
        value=result.value,
        value_qualifier=result.qualifier,
        unit=pick.unit or _ND_UNIT_PLACEHOLDER,
        source_run_id=None if is_aggregate else pick.run_id,
        source_curve_id=None if is_aggregate else pick.curve_id,
        source_readout_id=None if is_aggregate else pick.readout_id,
        protocol_name_snapshot=pick.protocol_name,
        protocol_version_snapshot=pick.protocol_version,
        run_date_snapshot=pick.run_date,
        curve_snapshot=snapshot,
    )
    contributing = set(result.contributing_run_ids)
    used = (
        [v for v in values if v.run.run_id in contributing]
        if is_aggregate
        else [v for v in values if v.run is pick]
    )
    return _with_facts(m, used, series)


def _with_facts(m: CampaignMeasurement, used: list[_Value], series: bool) -> CampaignMeasurement:
    """Record the facts of the readings behind the cell (spec §6.2, §6.4)."""
    readings = [c for v in used for c in v.readings]
    counts = [1 if c.well_id is not None else c.replicate_count for c in readings]
    bases = {
        MeasurementBasis.MEASURED
        if c.well_id is not None or c.run.curve_id is not None
        else MeasurementBasis.REPORTED
        for c in readings
    }
    m.contributing_run_ids = list(dict.fromkeys(v.run.run_id for v in used))
    m.batch_ids = sorted({c.batch_id for c in readings if c.batch_id is not None})
    m.replicate_count = None if None in counts else sum(c for c in counts if c is not None)
    m.basis = bases.pop() if len(bases) == 1 else MeasurementBasis.MIXED
    m.concentration_series = series
    dose = readings[0].dose if readings and not series else None
    if dose is not None:
        m.test_concentration_value, m.test_concentration_unit = dose.value, dose.unit
    return m
