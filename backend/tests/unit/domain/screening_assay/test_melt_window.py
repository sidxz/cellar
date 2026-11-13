import uuid

import pytest

from cellar.domain.screening_assay.melt_window import (
    WindowFlag,
    WindowPosition,
    check_step_counts,
    evaluate_window,
    window_positions,
)
from cellar.domain.shared.enums import WellType

REF, SAMPLE = WellType.REFERENCE, WellType.SAMPLE


def _id() -> uuid.UUID:
    return uuid.uuid4()


def test_merged_step_gives_negative_shift_in_main_window_and_no_step_in_low_window():
    r, s = _id(), _id()
    ps = [WindowPosition(r, REF, (36.6, 71.3)), WindowPosition(s, SAMPLE, (64.0,))]
    main = evaluate_window(50.0, 85.0, ps)
    assert main.reference_tm == 71.3
    assert main.positions[1].delta_tm == pytest.approx(-7.3)
    low = evaluate_window(25.0, 50.0, ps)
    assert low.positions[1].tm is None
    assert low.positions[1].flags == (WindowFlag.NO_STEP,)


def test_step_count_differs_from_reference():
    r, s, t = _id(), _id(), _id()
    ps = [
        WindowPosition(r, REF, (36.6, 71.3)),
        WindowPosition(s, SAMPLE, (64.0,)),
        WindowPosition(t, SAMPLE, (37.0, 70.0)),
        WindowPosition(_id(), WellType.BLANK, ()),
    ]
    check = check_step_counts(ps)
    assert check.differs == frozenset({s})
    assert check.references_differ is False


def test_edges_are_inclusive():
    ps = [WindowPosition(_id(), SAMPLE, (50.0,)), WindowPosition(_id(), SAMPLE, (85.0,))]
    res = evaluate_window(50.0, 85.0, ps)
    assert [p.tm for p in res.positions] == [50.0, 85.0]


def test_several_steps_in_window_give_no_value_and_a_flag():
    ps = [WindowPosition(_id(), SAMPLE, (55.0, 60.0))]
    p = evaluate_window(50.0, 85.0, ps).positions[0]
    assert p.tm is None and p.flags == (WindowFlag.SEVERAL_STEPS,)


def test_mean_of_several_references():
    ps = [
        WindowPosition(_id(), REF, (70.0,)),
        WindowPosition(_id(), REF, (72.0,)),
        WindowPosition(_id(), SAMPLE, (75.0,)),
    ]
    res = evaluate_window(50.0, 85.0, ps)
    assert res.reference_tm == 71.0 and res.reference_count == 2
    assert res.positions[2].delta_tm == pytest.approx(4.0)
    assert res.positions[0].delta_tm is None


def test_rejected_reference_step_leaves_window_without_reference():
    ps = [WindowPosition(_id(), REF, ()), WindowPosition(_id(), SAMPLE, (64.0,))]
    res = evaluate_window(50.0, 85.0, ps)
    assert res.reference_tm is None and res.reference_count == 0
    assert res.flags == (WindowFlag.NO_REFERENCE,)
    assert res.positions[1].delta_tm is None and res.positions[1].tm == 64.0


def test_controls_are_treated_as_samples():
    ps = [
        WindowPosition(_id(), REF, (70.0,)),
        WindowPosition(_id(), WellType.POSITIVE_CONTROL, (73.0,)),
    ]
    assert evaluate_window(50.0, 85.0, ps).positions[1].delta_tm == pytest.approx(3.0)


def test_references_that_disagree_flag_the_run_not_the_positions():
    s = _id()
    ps = [
        WindowPosition(_id(), REF, (36.0, 70.0)),
        WindowPosition(_id(), REF, (70.0,)),
        WindowPosition(s, SAMPLE, (70.0,)),
    ]
    check = check_step_counts(ps)
    assert check.references_differ is True and check.differs == frozenset()
    assert check_step_counts([WindowPosition(s, SAMPLE, (1.0,))]) == check_step_counts([])


def test_window_positions_drops_blanks_rejected_steps_and_other_channels():
    a, b, c = _id(), _id(), _id()
    wells = [(a, REF), (b, WellType.BLANK), (c, SAMPLE)]
    steps = [
        (a, "ch1", 71.0, True),
        (a, "ch1", 36.0, True),
        (a, "ch1", 80.0, False),
        (a, "ch2", 55.0, True),
        (b, "ch1", 60.0, True),
    ]
    out = window_positions(wells, steps, "ch1")
    assert out == [WindowPosition(a, REF, (36.0, 71.0)), WindowPosition(c, SAMPLE, ())]
