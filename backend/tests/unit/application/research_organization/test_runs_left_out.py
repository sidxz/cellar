"""The line a saved view shows when some of the runs it was saved with are gone."""

from __future__ import annotations

import pytest

from cellar.application.research_organization.saved_visualizations import _runs_left_out


@pytest.mark.parametrize(
    ("saved", "kept", "expected"),
    [
        (3, 3, None),
        (3, 2, "1 of the 3 runs this view was saved with no longer exists; it was left out."),
        (3, 1, "2 of the 3 runs this view was saved with no longer exist; they were left out."),
        (
            1,
            0,
            "The run this view was saved with no longer exists; "
            "showing every current run of the protocol.",
        ),
        (
            3,
            0,
            "None of the 3 runs this view was saved with exist any more; "
            "showing every current run of the protocol.",
        ),
    ],
)
def test_runs_left_out(saved: int, kept: int, expected: str | None) -> None:
    assert _runs_left_out(saved, kept, "this view") == expected
