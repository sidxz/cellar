"""The plot a curve column shows: one curve, or every split group's curve overlaid."""

from __future__ import annotations

import pytest

from cellar.application.export.renderers.sparkline import (
    column_plot,
    render_overlay,
    render_sparkline,
)
from cellar.application.export.row_streams.base import ColumnSpec

PNG = b"\x89PNG"


def _av(ic50: float) -> dict:
    return {
        "value": ic50,
        "curve_params": {"top": 100.0, "bottom": 0.0, "hill_slope": 1.0, "fitted_value": ic50},
        "raw_data": [{"x": x, "y": 100 * x / (x + ic50)} for x in (0.01, 0.1, 1.0, 10.0, 100.0)],
    }


def test_overlay_draws_when_any_group_has_a_curve():
    from cellar.application.export.renderers.sparkline import av_to_sparkline_snapshot

    assert render_overlay([None, av_to_sparkline_snapshot(_av(1.0))]).startswith(PNG)
    assert render_overlay([None, None]) is None


def test_an_overlay_column_draws_each_groups_curve_and_a_plain_column_its_own():
    activity = {"drc:r@cond:a": _av(1.0), "drc:r@cond:b": _av(30.0)}
    overlay = ColumnSpec(
        key="drc:r::overlay",
        header="Plot",
        kind="image_curve",
        overlay_of=("drc:r@cond:a", "drc:r@cond:b"),
    )
    plain = ColumnSpec(key="drc:r@cond:b::plot", header="Plot", kind="image_curve")
    two = column_plot(overlay, activity)
    one = column_plot(plain, activity)
    assert two.startswith(PNG) and one.startswith(PNG)
    assert two != one
    assert column_plot(plain, {}) is None


def test_a_single_curve_still_renders():
    assert render_sparkline({"data_points": [{"dose": 1.0, "response": 50.0}]}).startswith(PNG)


def test_the_pdf_takes_the_plot_as_svg():
    plain = ColumnSpec(key="drc:r::plot", header="Plot", kind="image_curve")
    svg = column_plot(plain, {"drc:r": _av(1.0)}, fmt="svg")
    assert b"<svg" in svg


def test_structures_draw_as_png_for_excel_and_svg_for_the_pdf():
    from cellar.application.export.renderers.structure import (
        render_structure_pngs,
        render_structure_svgs,
    )

    assert render_structure_pngs(["CCO", "not a smiles"]).keys() == {"CCO"}
    assert render_structure_pngs(["CCO"])["CCO"].startswith(PNG)
    assert "<svg" in render_structure_svgs(["CCO"])["CCO"]


def _potency_lines(av: dict) -> list[float]:
    """The x of every vertical line the sparkline draws for ``av``."""
    import matplotlib.pyplot as plt

    from cellar.application.export.renderers.sparkline import (
        _draw_curve,
        _figure,
        av_to_sparkline_snapshot,
    )

    snapshot = av_to_sparkline_snapshot(av)
    fig, ax = _figure(None, 0.001, 1000.0)
    _draw_curve(ax, snapshot)
    plt.close(fig)
    return [line.get_xdata()[0] for line in ax.lines if len(set(line.get_xdata())) == 1]


def _cell(curve_class: str, fitted: float, primary: dict | None) -> dict:
    return {
        "curve_params": {
            "top": 100.0,
            "bottom": 0.0,
            "hill_slope": 1.0,
            "curve_class": curve_class,
            "fitted_value": fitted,
        },
        "raw_data": [{"x": x, "y": 50.0} for x in (0.01, 0.1, 1.0, 10.0)],
        "intercept_values": [primary] if primary else None,
    }


_IC50 = {"kind": "ic", "level": 50.0, "basis": "relative_percent", "label": None}


def test_the_potency_line_marks_an_exact_primary():
    exact = {"spec": _IC50, "value": 1.0, "at_bound": False, "qualifier": "="}
    assert _potency_lines(_cell("full", 1.0, exact)) == [1.0]
    assert _potency_lines(_cell("full", 1.0, None)) == [1.0]  # fitted before qualifiers


@pytest.mark.parametrize(
    ("curve_class", "fitted", "primary"),
    [
        ("partial", 1000.0, {"spec": _IC50, "value": 10.0, "at_bound": True, "qualifier": ">"}),
        ("partial", 1.0, {"spec": _IC50, "value": None, "at_bound": False, "qualifier": "nd"}),
        ("active_all_doses", 0.001, {"spec": _IC50, "value": 0.01, "qualifier": "<"}),
        ("inactive", 1.0, {"spec": _IC50, "value": 1.0, "at_bound": False, "qualifier": "="}),
        ("full", 500.0, None),  # fitted before qualifiers, past the top dose
    ],
    ids=["above-the-doses", "nd", "active-at-all-doses", "inactive", "legacy-past-the-doses"],
)
def test_no_potency_line_where_the_primary_reads_no_exact_value(curve_class, fitted, primary):
    """The dotted line sits at the fitted midpoint: a potency only when the primary reads
    exactly. A bound, an n.d. or a class that reads a bound has none to mark."""
    assert _potency_lines(_cell(curve_class, fitted, primary)) == []
