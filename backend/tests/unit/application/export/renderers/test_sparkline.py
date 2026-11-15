"""The plot a curve column shows: one curve, or every split group's curve overlaid."""

from __future__ import annotations

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
        "curve_params": {"top": 100.0, "bottom": 0.0, "hill_slope": 1.0},
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
