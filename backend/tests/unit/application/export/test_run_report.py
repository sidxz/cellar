"""A run's export: the Traces tab's results, status and hit call, in every format."""

from __future__ import annotations

import csv
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.run_figures import shift_svg, traces_svg
from cellar.application.export.renderers.run_report_renderer import (
    render_run_report,
    results_table,
    steps_table,
)
from cellar.application.export.run_report import (
    DIFFERS,
    NO_STEP,
    REFERENCE,
    REVIEWED,
    RunCell,
    RunReport,
    RunRow,
    RunSignal,
    RunStep,
    RunTrace,
    RunWindow,
    _band,
    _rows,
    _steps,
    rule_text,
)
from cellar.application.screening.get_melting_analysis import (
    ChannelStepCheck,
    MeltingAnalysis,
    WindowAnalysis,
)
from cellar.application.screening.plate_map_reader import WellMapEntry
from cellar.domain.export.enums import ExportFormat
from cellar.domain.screening_assay.melt_window import (
    MeltMeasure,
    NamedBy,
    PositionWindowResult,
    StepCountCheck,
    WindowFlag,
    WindowResult,
)
from cellar.domain.screening_assay.melting_step import (
    MeltingStep,
    MeltingStepSource,
    MeltingStepStatus,
)
from cellar.domain.shared.hit_criterion import HitCriterion

REF, A, B, C = (uuid.uuid4() for _ in range(4))


def _pos(well_id, kind, label, reg=None, batch=None):
    return WellMapEntry(
        well_id=well_id,
        position="A1",
        row="A",
        column=1,
        well_type=kind,
        registration_number=reg,
        batch_number=batch,
        label=label,
        position_label=f"Position {label}",
    )


def _step(well_id, value, status=MeltingStepStatus.UNREVIEWED, **assignment):
    return MeltingStep(
        workspace_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        well_id=well_id,
        channel_key="ratio",
        source=MeltingStepSource.INSTRUMENT,
        value=value,
        instrument_value=value,
        instrument_label="Tm #1",
        status=status,
        **assignment,
    )


def _analysis(a_peaks=None, a_result=None):
    """Position A's peaks and its result in Main can be replaced."""
    ref = _step(REF, 71.3, MeltingStepStatus.ACCEPTED)
    b = _step(B, 70.4, MeltingStepStatus.ACCEPTED)
    a_peaks = a_peaks or (_step(A, 62.8),)
    a_result = a_result or PositionWindowResult(A, 62.8, -8.5, (), NamedBy.RANGE, a_peaks[0].id)
    main = WindowAnalysis(
        window="Main",
        channel_key="ratio",
        low=50.0,
        high=85.0,
        tm_readout_id=None,
        delta_tm_readout_id=None,
        result=WindowResult(
            low=50.0,
            high=85.0,
            reference_tm=71.3,
            reference_count=1,
            positions=(
                PositionWindowResult(REF, 71.3, None, (), NamedBy.RANGE, ref.id),
                a_result,
                PositionWindowResult(B, 70.4, -0.9, (), NamedBy.RANGE, b.id),
                PositionWindowResult(C, None, None, (WindowFlag.NO_STEP,)),
            ),
            flags=(),
        ),
    )
    return MeltingAnalysis(
        run_id=uuid.uuid4(),
        edit_refusal=None,
        steps=(ref, *a_peaks, b),
        windows=(main,),
        step_checks=(
            ChannelStepCheck("ratio", StepCountCheck(frozenset({C}), references_differ=False)),
        ),
    )


POSITIONS = (
    _pos(REF, "reference", "MadR"),
    _pos(A, "sample", "16:0-CoA"),
    _pos(B, "sample", None, reg="CC-014538", batch="CC-014538-001"),
    _pos(C, "sample", "SACC-0465797"),
)
OUTSIDE = HitCriterion(readout_name="ΔTm (Main)", operator="not_between", value=[-2.0, 2.0])


def test_rows_carry_the_pages_status_and_hit_call():
    rows = _rows(POSITIONS, _analysis(), [(OUTSIDE, "Main", MeltMeasure.DELTA_TM)])
    by = {r.well_id: r for r in rows}
    assert by[REF].cells["Main"].status == REFERENCE and by[REF].hit is None
    # An unreviewed peak leaves the review cell empty. -8.5 is outside ±2.
    assert (by[A].cells["Main"].status, by[A].hit) == ("", True)
    assert (by[B].cells["Main"].status, by[B].hit) == (REVIEWED, False)
    # Registration number names the sample; its batch loses the prefix.
    assert (by[B].sample, by[B].batch) == ("CC-014538", "001")
    # No peak: no value fails the rule; the count check is noted.
    assert by[C].hit is False
    assert by[C].cells["Main"].status == f"{NO_STEP} · {DIFFERS}"


def test_report_uses_the_assigned_peak_for_status():
    # A's Tm is the unreviewed peak assigned to Main from below its range; the
    # accepted peak inside the range no longer counts.
    in_range = _step(A, 62.8, MeltingStepStatus.ACCEPTED)
    assigned = _step(A, 45.0, assigned_window="Main")
    result = PositionWindowResult(A, 45.0, -26.3, (), NamedBy.ASSIGNMENT, assigned.id)
    cell = _rows(POSITIONS, _analysis((in_range, assigned), result), [])[1].cells["Main"]
    assert (cell.tm, cell.status) == (45.0, "")
    # The other way round: the assigned peak is accepted, the one in range is not.
    in_range = _step(A, 62.8)
    assigned = _step(A, 45.0, MeltingStepStatus.ACCEPTED, assigned_window="Main")
    result = PositionWindowResult(A, 45.0, -26.3, (), NamedBy.ASSIGNMENT, assigned.id)
    cell = _rows(POSITIONS, _analysis((in_range, assigned), result), [])[1].cells["Main"]
    assert cell.status == REVIEWED


def test_report_lists_assignment_on_peaks():
    ada, grace = uuid.uuid4(), uuid.uuid4()
    when = datetime(2026, 11, 17, 9, 5, tzinfo=UTC)
    stamp = {"assigned_by": ada, "assigned_at": when}
    assigned = _step(A, 45.0, assigned_window="Main", assignment_reason="split peak", **stamp)
    by_stranger = _step(A, 48.0, assigned_window="Main", assigned_by=grace, assigned_at=when)
    # "Gone" is not a window on this signal: the peak counts as unassigned.
    stale = _step(A, 62.8, assigned_window="Gone", assignment_reason="old", **stamp)
    analysis = _analysis((assigned, by_stranger, stale))
    _, first, second, third, _ = _steps(analysis, {}, {}, {str(ada): "Ada"})
    assert (
        first.assigned_window,
        first.assignment_reason,
        first.assigned_by,
        first.assigned_at,
    ) == ("Main", "split peak", "Ada", when)
    assert second.assigned_by == str(grace)  # as an unknown "changed by" is shown
    assert (
        third.assigned_window,
        third.assignment_reason,
        third.assigned_by,
        third.assigned_at,
    ) == (None, None, None, None)

    headers, rows = steps_table(replace(_report(), steps=(first,)))
    assert headers[-4:] == ["Assigned to", "Assignment reason", "Assigned by", "Assigned at (UTC)"]
    assert rows[0][-4:] == ["Main", "split peak", "Ada", "2026-11-17 09:05"]


def test_report_says_how_each_tm_was_named():
    assigned = _step(A, 45.0, MeltingStepStatus.ACCEPTED, assigned_window="Main")
    result = PositionWindowResult(A, 45.0, -26.3, (), NamedBy.ASSIGNMENT, assigned.id)
    rows = _rows(POSITIONS, _analysis((assigned,), result), [])
    assert {r.well_id: r.cells["Main"].named_by for r in rows} == {
        REF: "By range",
        A: "Assigned",
        B: "By range",
        C: "",  # no Tm, so nothing named it
    }
    headers, table = results_table(_report())
    assert headers[7:11] == ["Main Tm (°C)", "Main ΔTm (°C)", "Main status", "Main Tm named"]
    assert [row[10] for row in table] == ["By range", "Assigned"]


def test_an_unreviewed_peak_leaves_the_review_cell_empty():
    headers, table = results_table(_report())
    assert [row[headers.index("Main status")] for row in table] == [REFERENCE, None]


def test_a_differing_peak_count_is_said_whether_or_not_the_peak_was_reviewed():
    # A's peak is unreviewed, B's accepted; both have another number of peaks than the reference.
    check = ChannelStepCheck("ratio", StepCountCheck(frozenset({A, B}), references_differ=False))
    rows = _rows(POSITIONS, replace(_analysis(), step_checks=(check,)), [])
    by = {r.well_id: r.cells["Main"].status for r in rows}
    assert by[A] == "Different number of peaks than the reference"
    assert by[B] == f"{REVIEWED} · {DIFFERS}"


def test_without_a_rule_nobody_is_called():
    assert all(r.hit is None for r in _rows(POSITIONS, _analysis(), []))


def test_the_rule_reads_as_stated_and_draws_its_band():
    assert rule_text(OUTSIDE, "°C") == "ΔTm (Main) outside \u22122 to 2 °C"
    assert rule_text(HitCriterion("Tm (Low)", "gt", 40.0), "°C") == "Tm (Low) > 40 °C"
    assert _band("Main", [(OUTSIDE, "Main", MeltMeasure.DELTA_TM)]) == {"band": (-2.0, 2.0)}
    line = HitCriterion("ΔTm (Main)", "lt", -3.0)
    assert _band("Main", [(line, "Main", MeltMeasure.DELTA_TM)]) == {"line": -3.0}
    assert _band("Low", [(OUTSIDE, "Main", MeltMeasure.DELTA_TM)]) == {}


def _report() -> RunReport:
    window = RunWindow("Main", "Ratio 350/330", 50.0, 85.0, 71.3, 1, band=(-2.0, 2.0))
    rows = (
        RunRow(
            REF,
            "Position 1",
            "MadR",
            None,
            None,
            "MadR",
            None,
            "reference",
            None,
            {"Main": RunCell(71.3, None, REFERENCE, "By range")},
            None,
        ),
        RunRow(
            A,
            "Position 2",
            "16:0-CoA",
            None,
            None,
            "16:0-CoA",
            50.0,
            "sample",
            "cloudy",
            {"Main": RunCell(62.8, -8.5, "", "Assigned")},
            True,
        ),
    )
    trace = RunTrace("Position 2", "16:0-CoA", "sample", True, (50.0, 60.0), (0.1, 0.2))
    ref = RunTrace("Position 1", "MadR", "reference", None, (50.5, 60.5), (0.3, 0.4))
    return RunReport(
        protocol="PRT-00219 HsaA/B binding",
        run_date=date(2026, 11, 13),
        status="approved",
        operator="Ada",
        holder="Holder of 24",
        notes=None,
        dose_unit="uM",
        windows=(window,),
        hit_rule=("ΔTm (Main) outside \u22122 to 2 °C",),
        rows=rows,
        steps=(
            RunStep(
                "Position 2",
                "16:0-CoA",
                "Ratio 350/330",
                62.8,
                "Instrument",
                "Unreviewed",
                62.8,
                None,
                "Ada",
                datetime(2026, 11, 13, 21, 28, tzinfo=UTC),
            ),
        ),
        signals=(
            RunSignal(
                "ratio",
                "Ratio 350/330",
                "measured",
                "Temperature (°C)",
                "Ratio 350/330",
                None,
                (ref, trace),
            ),
            RunSignal(
                "ratio",
                "Ratio 350/330",
                "derivative",
                "Temperature (°C)",
                "Derivative of Ratio 350/330 (1/°C)",
                3.5,
                (ref, trace),
            ),
        ),
    )


OPTIONS = RenderOptions(
    title="Run report",
    extras={"exported_at": "2026-11-15 20:18 UTC", "exported_by": "ada@lab.org"},
)


async def test_csv_is_the_results_table_alone(tmp_path: Path):
    out = tmp_path / "run.csv"
    await render_run_report(_report(), ExportFormat.CSV, out, OPTIONS)
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[0] == results_table(_report())[0]
    assert rows[0][7:10] == ["Main Tm (°C)", "Main ΔTm (°C)", "Main status"]
    assert rows[2][:2] == ["Position 2", "16:0-CoA"] and rows[2][-2:] == ["Hit", "cloudy"]
    assert "ChemCellar" not in out.read_text(encoding="utf-8")  # no branding in the records


async def test_excel_holds_results_peaks_and_each_positions_own_temperatures(tmp_path: Path):
    out = tmp_path / "run.xlsx"
    await render_run_report(_report(), ExportFormat.XLSX, out, OPTIONS)
    wb = load_workbook(out)
    assert wb.sheetnames == [
        "Results",
        "Peaks",
        "Ratio 350-330 measured",
        "Ratio 350-330 derivative",
        "Notes",
    ]
    assert wb["Results"]["A1"].value == "Position"
    assert wb["Peaks"]["I2"].value == "Ada"
    traces = [[c.value for c in row] for row in wb["Ratio 350-330 measured"].iter_rows()]
    assert traces[0] == ["Position 1 · MadR", None, "Position 2 · 16:0-CoA", None]
    assert traces[2] == [50.5, 0.3, 50.0, 0.1]
    notes = "\n".join(str(c.value or "") for row in wb["Notes"].iter_rows() for c in row)
    assert "ada@lab.org" in notes
    assert "\u22122 to 2 °C" in notes  # the hit rule's bounds
    assert "3.5 °C" in notes  # the derivative's smoothing window


async def test_pdf_is_the_run_report(tmp_path: Path):
    out = tmp_path / "run.pdf"
    await render_run_report(_report(), ExportFormat.PDF, out, OPTIONS)
    assert out.read_bytes().startswith(b"%PDF")


async def test_sdf_is_not_a_run_format(tmp_path: Path):
    with pytest.raises(ValueError):
        await render_run_report(_report(), ExportFormat.SDF, tmp_path / "x.sdf", OPTIONS)


def test_figures_are_vector_and_skip_when_empty():
    report = _report()
    assert "<svg" in traces_svg(report)
    assert "<svg" in shift_svg(report, report.windows[0])
    empty = RunReport(**{**report.__dict__, "rows": (), "signals": ()})
    assert traces_svg(empty) is None and shift_svg(empty, report.windows[0]) is None
