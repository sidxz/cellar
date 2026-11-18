"""Facts recorded about a campaign measurement: the concentration it was taken at."""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cellar.domain.research_organization.enums import MeasurementBasis
from cellar.domain.shared.aggregation_types import SelectionRule
from cellar.domain.shared.units import (
    MICRO,
    canonical_unit,
    comparable_magnitude,
    is_concentration_unit,
)

if TYPE_CHECKING:
    from cellar.domain.research_organization.campaign_channel import CampaignChannel
    from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement

TEST_CONCENTRATION = "Test concentration"

_DOSE_FAMILIES = {"molar", "mass concentration"}
_TEXT = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(\S*)\s*$")


@dataclass(frozen=True)
class Concentration:
    value: float
    unit: str

    def same_as(self, other: Concentration) -> bool:
        fa, a = comparable_magnitude(self.value, self.unit)
        fb, b = comparable_magnitude(other.value, other.unit)
        return fa == fb and math.isclose(a, b, rel_tol=1e-9)


def parse_concentration(raw: object, default_unit: str = f"{MICRO}M") -> Concentration | None:
    """A molar or mass/volume concentration from "10 µM" / "10 ug/mL" / a bare number / a dict.
    Anything else (including a lone lowercase "um", ambiguous with µm) is None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, dict):
        value, unit = raw.get("value"), raw.get("unit")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
    elif isinstance(raw, (int, float)):
        value, unit = raw, default_unit
    elif isinstance(raw, str):
        m = _TEXT.match(raw)
        if not m:
            return None
        value, unit = float(m.group(1)), m.group(2) or default_unit
    else:
        return None
    unit = canonical_unit(unit if isinstance(unit, str) else None)
    if unit is None or not math.isfinite(value) or not is_concentration_unit(unit):
        return None
    if comparable_magnitude(1, unit)[0] not in _DOSE_FAMILIES:  # ×MIC is not a dose
        return None
    return Concentration(float(value), unit)


# --- column profile and description (R13) -------------------------------------------

SINGLE = "single_concentration"
MIXED = "single_concentration_mixed"
SERIES = "concentration_series"
REPORTED = "reported"
NOT_RECORDED = "not_recorded"

RULE_NAMES = {
    SelectionRule.LATEST_RUN: "latest run",
    SelectionRule.MEAN_ACROSS_RUNS: "mean across runs",
    SelectionRule.GEOMETRIC_MEAN: "geometric mean",
    SelectionRule.BEST_R_SQUARED: "best fit",
    SelectionRule.MANUAL_PICK: "manual pick",
}


@dataclass(frozen=True)
class ColumnProfile:
    designs: frozenset[str]
    #: (concentration or None for "not recorded", count); series cells are not listed.
    concentrations: tuple[tuple[Concentration | None, int], ...]
    replicate_min: int | None
    replicate_max: int | None
    replicate_not_recorded: int
    run_count: int
    several_concentrations: int
    basis: frozenset[MeasurementBasis]


@dataclass(frozen=True)
class ColumnDescription:
    stage_name: str | None
    readout_label: str
    design: str
    concentrations: list[dict[str, Any]]
    replicates: dict[str, Any]
    run_count: int
    rule: str
    basis: list[str]
    needs_concentration: bool
    label: str


def build_column_profile(
    channel: CampaignChannel, measurements: Iterable[CampaignMeasurement]
) -> ColumnProfile:
    designs: set[str] = set()
    buckets: list[list[Any]] = []  # [Concentration | None, count]
    reps: list[int] = []
    not_recorded = several = 0
    runs: set[uuid.UUID] = set()
    basis: set[MeasurementBasis] = set()
    for m in measurements:
        if m.unresolved_reason is not None:
            several += m.unresolved_reason.value == "several_concentrations"
            continue
        conc = (
            parse_concentration(
                {"value": m.test_concentration_value, "unit": m.test_concentration_unit}
            )
            if m.test_concentration_value is not None
            else None
        )
        run_ids = m.contributing_run_ids or ([m.source_run_id] if m.source_run_id else [])
        if (
            m.basis is None
            and not m.concentration_series
            and conc is None
            and m.replicate_count is None
            and not run_ids
        ):
            continue  # no facts (plain ND / untested)
        runs.update(run_ids)
        if m.basis is not None:
            basis.add(m.basis)
        if m.concentration_series:
            designs.add(SERIES)
            continue
        if conc is not None:
            designs.add(SINGLE)
        elif m.basis == MeasurementBasis.REPORTED:
            designs.add(REPORTED)
        else:
            designs.add(NOT_RECORDED)
        for b in buckets:
            if (b[0] is None and conc is None) or (
                b[0] is not None and conc is not None and b[0].same_as(conc)
            ):
                b[1] += 1
                break
        else:
            buckets.append([conc, 1])
        if m.replicate_count is None:
            not_recorded += 1
        else:
            reps.append(m.replicate_count)
    return ColumnProfile(
        designs=frozenset(designs),
        concentrations=tuple((c, n) for c, n in buckets),
        replicate_min=min(reps, default=None),
        replicate_max=max(reps, default=None),
        replicate_not_recorded=not_recorded,
        run_count=len(runs),
        several_concentrations=several,
        basis=frozenset(basis),
    )


def _conc_text(c: Concentration) -> str:
    return f"{c.value:g} {c.unit}"


def _design(profile: ColumnProfile) -> tuple[str, list[Concentration]]:
    known = [c for c, _ in profile.concentrations if c is not None]
    if len(known) == 1:
        return SINGLE, known
    if len(known) > 1:
        return MIXED, known
    if profile.designs == {SERIES}:
        return SERIES, known
    if profile.designs == {REPORTED}:
        return REPORTED, known
    return NOT_RECORDED, known


def _replicates_text(p: ColumnProfile) -> str:
    if p.replicate_min is None:
        return "replicates not recorded"
    lo, hi = p.replicate_min, p.replicate_max
    if lo != hi:
        text = f"{lo}–{hi} replicates"  # noqa: RUF001
    else:
        text = "1 replicate" if lo == 1 else f"mean of {lo} replicates"
    return (
        f"{text} ({p.replicate_not_recorded} not recorded)" if p.replicate_not_recorded else text
    )


def describe_column(
    *,
    channel: CampaignChannel,
    stage_name: str | None,
    readout_label: str,
    profile: ColumnProfile,
) -> ColumnDescription:
    design, known = _design(profile)
    design_text = {
        SINGLE: f"single concentration {_conc_text(known[0])}" if known else "",
        MIXED: "several concentrations (" + ", ".join(_conc_text(c) for c in known) + ")",
        SERIES: "dose-response",
        REPORTED: "reported value",
        NOT_RECORDED: "concentration not recorded",
    }[design]
    rule = RULE_NAMES[channel.selection_rule]
    runs = f"{profile.run_count} run" + ("" if profile.run_count == 1 else "s")
    parts = [stage_name, readout_label, design_text]
    if design != SERIES:
        parts.append(_replicates_text(profile))
    parts += [runs, rule]
    return ColumnDescription(
        stage_name=stage_name,
        readout_label=readout_label,
        design=design,
        concentrations=[
            {"value": c.value, "unit": c.unit, "count": n}
            if c
            else {"value": None, "unit": None, "count": n}
            for c, n in profile.concentrations
        ],
        replicates={
            "min": profile.replicate_min,
            "max": profile.replicate_max,
            "not_recorded": profile.replicate_not_recorded,
        },
        run_count=profile.run_count,
        rule=rule,
        basis=sorted(b.value for b in profile.basis),
        needs_concentration=channel.test_concentration is None
        and (len(known) > 1 or profile.several_concentrations > 0),
        label=" · ".join(p for p in parts if p),
    )
