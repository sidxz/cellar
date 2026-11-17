import uuid

import pytest

from cellar.domain.screening_assay.melt_window import (
    NamedBy,
    StepFact,
    WindowFlag,
    WindowPosition,
    check_step_counts,
    evaluate_window,
    outside_every_window,
    window_positions,
)
from cellar.domain.shared.enums import WellType

REF, SAMPLE = WellType.REFERENCE, WellType.SAMPLE
NAMES = {"Low", "Main"}


def _id() -> uuid.UUID:
    return uuid.uuid4()


def _fact(
    value: float,
    assigned: str | None = None,
    *,
    well: uuid.UUID | None = None,
    key: str = "ch1",
    counts: bool = True,
) -> StepFact:
    return StepFact(_id(), well or _id(), key, value, counts, assigned)


def _pos(well_type: WellType, *steps: StepFact | float, well: uuid.UUID | None = None):
    facts = tuple(s if isinstance(s, StepFact) else _fact(s) for s in steps)
    return WindowPosition(well or _id(), well_type, facts)


def _main(ps: list[WindowPosition]):
    return evaluate_window("Main", 50.0, 85.0, ps, NAMES)


def _low(ps: list[WindowPosition]):
    return evaluate_window("Low", 25.0, 50.0, ps, NAMES)


def test_merged_step_gives_negative_shift_in_main_window_and_no_step_in_low_window():
    ps = [_pos(REF, 36.6, 71.3), _pos(SAMPLE, 64.0)]
    main = _main(ps)
    assert main.reference_tm == 71.3
    assert main.positions[1].delta_tm == pytest.approx(-7.3)
    low = _low(ps)
    assert low.positions[1].tm is None
    assert low.positions[1].flags == (WindowFlag.NO_STEP,)
    assert low.positions[1].named_by is None and low.positions[1].step_id is None


def test_step_count_differs_from_reference():
    s = _id()
    ps = [
        _pos(REF, 36.6, 71.3),
        _pos(SAMPLE, 64.0, well=s),
        _pos(SAMPLE, 37.0, 70.0),
        _pos(WellType.BLANK),
    ]
    check = check_step_counts(ps)
    assert check.differs == frozenset({s})
    assert check.references_differ is False


def test_edges_are_inclusive():
    res = _main([_pos(SAMPLE, 50.0), _pos(SAMPLE, 85.0)])
    assert [p.tm for p in res.positions] == [50.0, 85.0]


def test_several_steps_in_window_give_no_value_and_a_flag():
    p = _main([_pos(SAMPLE, 55.0, 60.0)]).positions[0]
    assert p.tm is None and p.flags == (WindowFlag.SEVERAL_STEPS,)
    assert p.named_by is None and p.step_id is None


def test_mean_of_several_references():
    res = _main([_pos(REF, 70.0), _pos(REF, 72.0), _pos(SAMPLE, 75.0)])
    assert res.reference_tm == 71.0 and res.reference_count == 2
    assert res.positions[2].delta_tm == pytest.approx(4.0)
    assert res.positions[0].delta_tm is None


def test_rejected_reference_step_leaves_window_without_reference():
    res = _main([_pos(REF), _pos(SAMPLE, 64.0)])
    assert res.reference_tm is None and res.reference_count == 0
    assert res.flags == (WindowFlag.NO_REFERENCE,)
    assert res.positions[1].delta_tm is None and res.positions[1].tm == 64.0


def test_controls_are_treated_as_samples():
    ps = [_pos(REF, 70.0), _pos(WellType.POSITIVE_CONTROL, 73.0)]
    assert _main(ps).positions[1].delta_tm == pytest.approx(3.0)


def test_references_that_disagree_flag_the_run_not_the_positions():
    s = _id()
    ps = [_pos(REF, 36.0, 70.0), _pos(REF, 70.0), _pos(SAMPLE, 70.0, well=s)]
    check = check_step_counts(ps)
    assert check.references_differ is True and check.differs == frozenset()
    assert check_step_counts([_pos(SAMPLE, 1.0, well=s)]) == check_step_counts([])


def test_window_positions_drops_blanks_rejected_steps_and_other_channels():
    a, b, c = _id(), _id(), _id()
    wells = [(a, REF), (b, WellType.BLANK), (c, SAMPLE)]
    high, low = _fact(71.0, well=a), _fact(36.0, well=a)
    steps = [
        high,
        low,
        _fact(80.0, well=a, counts=False),
        _fact(55.0, well=a, key="ch2"),
        _fact(60.0, well=b),
    ]
    traced = {(a, "ch1"), (b, "ch1"), (c, "ch1")}
    out = window_positions(wells, steps, "ch1", traced)
    assert out == [WindowPosition(a, REF, (low, high)), WindowPosition(c, SAMPLE, ())]


def test_window_positions_leaves_out_positions_without_a_trace_on_the_channel():
    a, c = _id(), _id()
    wells = [(a, REF), (c, SAMPLE)]
    step = _fact(71.0, well=a)
    # c has a trace on ch2 only: it is not evaluated on ch1, so no "no step" flag for it.
    out = window_positions(wells, [step], "ch1", {(a, "ch1"), (c, "ch2")})
    assert out == [WindowPosition(a, REF, (step,))]


def test_assigned_peak_wins_over_the_range():
    shoulder = _fact(48.1, "Main")
    p = _main([_pos(SAMPLE, shoulder, 63.0)]).positions[0]
    assert p.tm == 48.1 and p.flags == ()
    assert p.named_by is NamedBy.ASSIGNMENT and p.step_id == shoulder.id


def test_peak_assigned_elsewhere_does_not_count_in_its_range():
    p = _low([_pos(SAMPLE, _fact(48.1, "Main"), 63.0)]).positions[0]
    assert p.tm is None and p.flags == (WindowFlag.NO_STEP,)


def test_range_naming_reports_the_peak():
    peak = _fact(63.0)
    p = _main([_pos(SAMPLE, 36.0, peak)]).positions[0]
    assert p.tm == 63.0 and p.named_by is NamedBy.RANGE and p.step_id == peak.id


def test_stale_assignment_is_ignored():
    # "Gone" is no longer a window of this signal: the peak is named by range again.
    peak = _fact(63.0, "Gone")
    ps = [_pos(SAMPLE, peak)]
    p = _main(ps).positions[0]
    assert p.tm == 63.0 and p.named_by is NamedBy.RANGE and p.step_id == peak.id
    assert _low(ps).positions[0].flags == (WindowFlag.NO_STEP,)


def test_two_peaks_assigned_to_one_window_give_several_steps():
    p = _main([_pos(SAMPLE, _fact(48.1, "Main"), _fact(63.0, "Main"))]).positions[0]
    assert p.tm is None and p.flags == (WindowFlag.SEVERAL_STEPS,)
    assert p.named_by is None and p.step_id is None


def test_rejected_assigned_peak_falls_back_to_range():
    a = _id()
    in_range = _fact(63.0, well=a)
    steps = [_fact(48.1, "Main", well=a, counts=False), in_range]
    ps = window_positions([(a, SAMPLE)], steps, "ch1", {(a, "ch1")})
    p = _main(ps).positions[0]
    assert p.tm == 63.0 and p.named_by is NamedBy.RANGE and p.step_id == in_range.id


def test_reference_assignment_feeds_the_reference_mean():
    ps = [_pos(REF, _fact(48.0, "Main"), 70.0), _pos(REF, 72.0), _pos(SAMPLE, 65.0)]
    res = _main(ps)
    assert res.reference_tm == 60.0 and res.reference_count == 2
    assert res.positions[0].named_by is NamedBy.ASSIGNMENT
    assert res.positions[2].delta_tm == pytest.approx(5.0)


def test_outside_every_window_lists_unplaced_counted_peaks():
    unplaced, stale = _fact(90.0), _fact(91.0, "Gone")
    ps = [
        _pos(SAMPLE, 36.0, 63.0, unplaced),
        # Assigned to a current window: placed, wherever it lies. A stale name places nothing.
        _pos(SAMPLE, _fact(92.0, "Main"), stale),
    ]
    windows = [("Low", 25.0, 50.0), ("Main", 50.0, 85.0)]
    assert outside_every_window(ps, windows) == (unplaced.id, stale.id)
    # With no windows nothing is placed, not even the peak assigned to "Main".
    assert len(outside_every_window(ps, [])) == 5
