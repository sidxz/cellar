"""Synthetic dose-response curves with known truth, for fitter tests and validation.

``make_curve`` samples the 4PL in the fitter's Prism parametrisation,

    y = bottom + (top - bottom) / (1 + 10^((log_ec50 - log10(c)) * hill)),

at the given doses and adds fixed-seed Gaussian noise. The formula is restated here, not
imported from the fitter, so the generator stays an independent truth.

``GRID`` spans dose designs (3-6 decades, 6-20 points), both directions, transitions left of,
inside and right of the tested doses, full / partial / flat curves (flat at 0, 40 and 95 %
effect), Hill 0.5-6 and noise SD 0, 3 and 8. No case is tuned to any dataset.

Each case also carries the outcomes the censoring rules (design spec 2026-11-19, section B, with
the controller's rulings) give under the default config (free plateaus and slope, default
thresholds) and the case's ``scale``: rising cases are read on a % scale (0 to 100), falling
cases on none, as raw-signal layers are. They are sets: the outcomes the rules can reach once
noise moves the fit. The fitted curve may sit ``NOISE_BAND`` noise SDs off the generating one
at a tested-dose edge or a plateau, so a crossing may land as far either side as that moves the
curve at it (``EDGE_DECADES`` at least). Noise-free cases are crisp, except where a curve whose
transition lies outside the doses lets the fit either extrapolate the true plateaus or read the
data as flat.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cellar.domain.screening_assay.curve_fitting import ConcentrationResponsePoint
from cellar.domain.screening_assay.dose_response_config import (
    DEFAULT_FULL_BOTTOM_MAX,
    DEFAULT_FULL_R2_MIN,
    DEFAULT_FULL_TOP_MIN,
    DEFAULT_INACTIVE_THRESHOLD,
    DEFAULT_PARTIAL_R2_MIN,
)
from cellar.domain.shared.aggregation_types import ValueQualifier

EDGE_DECADES = 0.5
NOISE_BAND = 3.0

FULL, PARTIAL, INACTIVE, ACTIVE_ALL_DOSES = "full", "partial", "inactive", "active_all_doses"

# The % scale of a rising curve (% inhibition / % activation), as (zero, full).
RISING_SCALE = (0.0, 100.0)

# (decades, points, lowest dose)
DOSE_DESIGNS = ((3, 6, 0.1), (4, 10, 0.01), (6, 20, 0.0001))
HILLS = (0.5, 1.0, 2.0, 6.0)
NOISE_SDS = (0.0, 3.0, 8.0)
FLAT_EFFECTS = (0.0, 40.0, 95.0)


def _4pl(log_c, top: float, bottom: float, log_ec50: float, hill: float):
    return bottom + (top - bottom) / (1.0 + 10.0 ** ((log_ec50 - log_c) * hill))


def make_curve(
    *,
    top: float,
    bottom: float,
    log_ec50: float,
    hill: float,
    doses,
    noise_sd: float,
    seed: int,
) -> list[ConcentrationResponsePoint]:
    log_c = np.log10(np.asarray(doses, dtype=float))
    noise = np.random.default_rng(seed).normal(0.0, noise_sd, len(log_c))
    y = _4pl(log_c, top, bottom, log_ec50, hill) + noise
    return [
        ConcentrationResponsePoint(concentration=float(c), response=float(r))
        for c, r in zip(doses, y, strict=True)
    ]


@dataclass(frozen=True)
class Case:
    name: str
    top: float
    bottom: float
    log_ec50: float
    hill: float
    doses: tuple[float, ...]
    noise_sd: float
    seed: int
    position: str  # "left" | "inside" | "right" | "flat"
    scale: tuple[float, float] | None  # (zero, full); None: no scale to judge a flat curve by
    expected_class: frozenset[str]
    expected_ec50: frozenset[ValueQualifier]
    expected_ec90: frozenset[ValueQualifier]

    def points(self) -> list[ConcentrationResponsePoint]:
        return make_curve(
            top=self.top,
            bottom=self.bottom,
            log_ec50=self.log_ec50,
            hill=self.hill,
            doses=self.doses,
            noise_sd=self.noise_sd,
            seed=self.seed,
        )


def _intercept_outcomes(
    *, top, bottom, log_ec50, hill, log_lo, log_hi, noise_sd, scale, level
) -> set[tuple[str, ValueQualifier]]:
    """``(branch, qualifier)`` pairs the rules can give; branch is "transition", "flat" (no
    transition, read on the scale) or "raw" (no transition, no scale)."""
    f_lo, f_hi = (_4pl(x, top, bottom, log_ec50, hill) for x in (log_lo, log_hi))
    span, amplitude = abs(f_hi - f_lo), abs(top - bottom)
    band = NOISE_BAND * noise_sd
    out: set[tuple[str, ValueQualifier]] = set()

    # With a transition: y* sits ``level`` % of the way from the low-dose plateau to the
    # high-dose one, and the qualifier follows where that crossing falls against the doses.
    transition_possible = span + band >= DEFAULT_INACTIVE_THRESHOLD or (
        noise_sd == 0 and amplitude >= DEFAULT_INACTIVE_THRESHOLD
    )
    if transition_possible and top != bottom:
        start, end = (bottom, top) if hill > 0 else (top, bottom)
        y = start + level / 100.0 * (end - start)
        crossing = log_ec50 - math.log10((top - y) / (y - bottom)) / hill
        # Response per decade at the crossing: |top - bottom|·|hill|·ln10·p(1 - p).
        p = level / 100.0
        slope = amplitude * abs(hill) * math.log(10.0) * p * (1.0 - p)
        tolerance = max(EDGE_DECADES, band / slope) if noise_sd else 0.0
        lo_x, hi_x = crossing - tolerance, crossing + tolerance
        if lo_x <= log_lo:
            out.add(("transition", ValueQualifier.LT))
        if hi_x > log_hi:
            out.add(("transition", ValueQualifier.GT))
        if lo_x <= log_hi and hi_x > log_lo:
            out.add(("transition", ValueQualifier.EQ))

    # Without one and without a scale ("raw"): the fit's own crossing, wherever its noise puts
    # it, read against the doses ("<", "=", ">"); ">" too when it has none (top == bottom).
    if span - band < DEFAULT_INACTIVE_THRESHOLD and scale is None:
        out |= {("raw", q) for q in (ValueQualifier.LT, ValueQualifier.EQ, ValueQualifier.GT)}
    # Without one, on a scale: y* sits at ``level`` % of the scale, the direction is the scale's.
    elif span - band < DEFAULT_INACTIVE_THRESHOLD:
        zero, full = scale
        y = zero + level / 100.0 * (full - zero)

        def reached(v: float) -> bool:
            return v >= y if full > zero else v <= y

        lo_reached = {reached(v) for v in (f_lo - band, f_lo + band)}
        hi_reached = {reached(v) for v in (f_hi - band, f_hi + band)}
        if True in lo_reached:
            out.add(("flat", ValueQualifier.LT))
        if False in lo_reached and False in hi_reached:
            out.add(("flat", ValueQualifier.GT))
        if False in lo_reached and True in hi_reached:
            out.add(("flat", ValueQualifier.ND))
    return out


def _shown_at_lowest(*, top, bottom, log_ec50, hill, log_lo, noise_sd, scale) -> set[bool]:
    """Whether the fitted curve at the lowest dose can be past the 50 % level of the scale."""
    zero, full = scale
    y = zero + 0.5 * (full - zero)
    f_lo = _4pl(log_lo, top, bottom, log_ec50, hill)
    band = NOISE_BAND * noise_sd
    return {(v >= y) if full > zero else (v <= y) for v in (f_lo - band, f_lo + band)}


def _transition_classes(*, top, bottom, log_ec50, hill, log_doses, noise_sd) -> set[str]:
    """Today's R²/plateau rules on a curve with a visible transition."""
    full = top >= DEFAULT_FULL_TOP_MIN and bottom <= DEFAULT_FULL_BOTTOM_MAX
    classes = {FULL if full else PARTIAL}
    if noise_sd == 0:
        return classes
    band = NOISE_BAND * noise_sd
    if top + band >= DEFAULT_FULL_TOP_MIN and bottom - band <= DEFAULT_FULL_BOTTOM_MAX:
        classes.add(FULL)
    if top - band < DEFAULT_FULL_TOP_MIN or bottom + band > DEFAULT_FULL_BOTTOM_MAX:
        classes.add(PARTIAL)
    y = _4pl(log_doses, top, bottom, log_ec50, hill)
    if abs(y[-1] - y[0]) < 0.8 * abs(top - bottom):
        # Plateaus not seen: the fit extrapolates them, either side of the full thresholds.
        classes |= {FULL, PARTIAL}
    r2 = 1.0 - noise_sd**2 / float(np.var(y))
    if r2 < DEFAULT_FULL_R2_MIN + 0.1:
        classes.add(PARTIAL)
    if r2 < DEFAULT_PARTIAL_R2_MIN + 0.1:
        classes.add(INACTIVE)
    return classes


def _case(name, *, top, bottom, log_ec50, hill, doses, noise_sd, seed, position, scale) -> Case:
    log_doses = np.log10(np.asarray(doses))
    log_lo, log_hi = float(log_doses[0]), float(log_doses[-1])
    params = dict(top=top, bottom=bottom, log_ec50=log_ec50, hill=hill)
    observed = make_curve(**params, doses=doses, noise_sd=noise_sd, seed=seed)
    if max(p.response for p in observed) < DEFAULT_INACTIVE_THRESHOLD:
        # The inactive fast path: no fit, every intercept "> highest dose".
        ec50 = ec90 = {("fast", ValueQualifier.GT)}
        classes = {INACTIVE}
    else:
        ec50, ec90 = (
            _intercept_outcomes(
                **params,
                log_lo=log_lo,
                log_hi=log_hi,
                noise_sd=noise_sd,
                scale=scale,
                level=level,
            )
            for level in (50.0, 90.0)
        )
        classes = set()
        for branch, q in ec50:
            # "Active at all doses" needs a "<" and the scale to show the effect at the lowest
            # dose; a flat "<" read on the scale shows it by construction.
            if q == ValueQualifier.LT and branch == "flat":
                classes.add(ACTIVE_ALL_DOSES)
                continue
            if q == ValueQualifier.LT and scale is not None:
                shown = _shown_at_lowest(**params, log_lo=log_lo, noise_sd=noise_sd, scale=scale)
                if True in shown:
                    classes.add(ACTIVE_ALL_DOSES)
                if False not in shown:
                    continue
            if branch in ("flat", "raw"):
                # R²-based classes of a flat fit: unchanged by the spec (non-goal).
                classes |= {INACTIVE, PARTIAL}
            else:
                classes |= _transition_classes(**params, log_doses=log_doses, noise_sd=noise_sd)
    return Case(
        name=name,
        **params,
        doses=tuple(doses),
        noise_sd=noise_sd,
        seed=seed,
        position=position,
        scale=scale,
        expected_class=frozenset(classes),
        expected_ec50=frozenset(q for _, q in ec50),
        expected_ec90=frozenset(q for _, q in ec90),
    )


def _build_grid() -> list[Case]:
    shapes = (  # name, top, bottom, rising
        ("rise-full", 100.0, 0.0, True),
        ("rise-partial", 60.0, 0.0, True),
        ("fall-full", 100.0, 0.0, False),
        ("fall-partial", 100.0, 40.0, False),
    )
    specs: list[dict] = []
    for decades, n, lowest in DOSE_DESIGNS:
        doses = tuple(float(d) for d in np.logspace(0, decades, n) * lowest)
        log_lo, log_hi = math.log10(doses[0]), math.log10(doses[-1])
        design = f"{decades}dec{n}"
        for noise_sd in NOISE_SDS:
            for shape, top, bottom, rising in shapes:
                for h in HILLS:
                    # Left / right: the whole transition (1-99 %) sits half a decade past the
                    # tested doses, so the data show one plateau whatever the slope; only the
                    # slope extremes are kept there.
                    tail = math.log10(99.0) / h + 0.5
                    positions = [("inside", (log_lo + log_hi) / 2.0)]
                    if h in (HILLS[0], HILLS[-1]):
                        positions += [("left", log_lo - tail), ("right", log_hi + tail)]
                    for position, log_ec50 in positions:
                        specs.append(
                            dict(
                                name=f"{shape}-{position}-h{h:g}-{design}-sd{noise_sd:g}",
                                top=top,
                                bottom=bottom,
                                log_ec50=log_ec50,
                                hill=h if rising else -h,
                                doses=doses,
                                noise_sd=noise_sd,
                                position=position,
                                scale=RISING_SCALE if rising else None,
                            )
                        )
            for effect in FLAT_EFFECTS:
                # The same effect on a rising % readout and on a falling raw one (100 = none).
                for direction, level, scale in (
                    ("rise", effect, RISING_SCALE),
                    ("fall", 100.0 - effect, None),
                ):
                    specs.append(
                        dict(
                            name=f"{direction}-flat{effect:g}-{design}-sd{noise_sd:g}",
                            top=level,
                            bottom=level,
                            log_ec50=(log_lo + log_hi) / 2.0,
                            hill=1.0 if direction == "rise" else -1.0,
                            doses=doses,
                            noise_sd=noise_sd,
                            position="flat",
                            scale=scale,
                        )
                    )
    return [_case(seed=i, **spec) for i, spec in enumerate(specs)]


GRID: list[Case] = _build_grid()
