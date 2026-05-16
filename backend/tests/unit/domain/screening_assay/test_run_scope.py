"""RunScope value object — translates FE 'last N runs' / date-window into a BE filter."""

import uuid
from datetime import date

import pytest

from cellar.domain.screening_assay.run_scope import RunScope


def test_all_runs_is_default():
    s = RunScope.all()
    assert s.is_all() is True


def test_last_n_carries_count():
    s = RunScope.last_n(3)
    assert s.last_n_count == 3
    assert s.is_all() is False


def test_since_carries_lower_bound():
    d = date(2026, 1, 1)
    s = RunScope.since(d)
    assert s.since_date == d


def test_between_carries_inclusive_window():
    s = RunScope.between(date(2026, 1, 1), date(2026, 5, 1))
    assert s.from_date == date(2026, 1, 1)
    assert s.to_date == date(2026, 5, 1)


def test_run_ids_carries_explicit_set():
    a, b = uuid.uuid4(), uuid.uuid4()
    s = RunScope.run_ids([a, b])
    assert set(s.explicit_run_ids) == {a, b}


def test_invalid_last_n_rejected():
    with pytest.raises(ValueError):
        RunScope.last_n(0)
    with pytest.raises(ValueError):
        RunScope.last_n(-1)


def test_invalid_between_rejected():
    with pytest.raises(ValueError):
        RunScope.between(date(2026, 5, 1), date(2026, 1, 1))
