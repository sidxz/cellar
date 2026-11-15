"""A run's export: the Traces tab's results, status and hit call, in every format."""

from __future__ import annotations

import csv
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from cellar.application.export.renderers.base import RenderOptions
from cellar.application.export.renderers.run_figures import shift_svg, traces_svg
from cellar.application.export.renderers.run_report_renderer import (
    render_run_report,
    results_table,
)
from cellar.application.export.run_report import (
    NO_STEP,
    PROVISIONAL,
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


def _step(well_id, value, status=MeltingStepStatus.UNREVIEWED):
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
    )


def _analysis():
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
                PositionWindowResult(REF, 71.3, None, ()),
                PositionWindowResult(A, 62.8, -8.5, ()),
                PositionWindowResult(B, 70.4, -0.9, ()),
                PositionWindowResult(C, None, None, (WindowFlag.NO_STEP,)),
            ),
            flags=(),
        ),
    )
    return MeltingAnalysis(
        run_id=uuid.uuid4(),
        edit_refusal=None,
        steps=(
            _step(REF, 71.3, MeltingStepStatus.ACCEPTED),
            _step(A, 62.8),
            _step(B, 70.4, MeltingStepStatus.ACCEPTED),
        ),
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
    assert (by[A].cells["Main"].status, by[A].hit) == (PROVISIONAL, True)  # -8.5 is outside ±2
    assert (by[B].cells["Main"].status, by[B].hit) == (REVIEWED, False)
    # Registration number names the sample; its batch loses the prefix.
    assert (by[B].sample, by[B].batch) == ("CC-014538", "001")
    # No step: no value fails the rule; the step-count check is noted.
    assert by[C].hit is False
    assert by[C].cells["Main"].status == f"{NO_STEP} · step count differs from the reference"


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
            {"Main": RunCell(71.3, None, REFERENCE)},
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
            {"Main": RunCell(62.8, -8.5, PROVISIONAL)},
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


async def test_excel_holds_results_steps_and_each_positions_own_temperatures(tmp_path: Path):
    out = tmp_path / "run.xlsx"
    await render_run_report(_report(), ExportFormat.XLSX, out, OPTIONS)
    wb = load_workbook(out)
    assert wb.sheetnames == [
        "Results",
        "Steps",
        "Ratio 350-330 measured",
        "Ratio 350-330 derivative",
        "Notes",
    ]
    assert wb["Results"]["A1"].value == "Position"
    assert wb["Steps"]["I2"].value == "Ada"
    traces = [[c.value for c in row] for row in wb["Ratio 350-330 measured"].iter_rows()]
    assert traces[0] == ["Position 1 · MadR", None, "Position 2 · 16:0-CoA", None]
    assert traces[2] == [50.5, 0.3, 50.0, 0.1]
    notes = [c.value for row in wb["Notes"].iter_rows() for c in row if c.value]
    assert notes[0] == "ChemCellar" and "By ada@lab.org" in notes
    assert "Hit rule: ΔTm (Main) outside \u22122 to 2 °C" in notes
    assert "Ratio 350/330 derivative smoothed over 3.5 °C" in notes


async def test_pdf_is_the_run_report(tmp_path: Path):
    out = tmp_path / "run.pdf"
    await render_run_report(_report(), ExportFormat.PDF, out, OPTIONS)
    assert out.read_bytes().startswith(b"%PDF")


async def test_sdf_is_not_a_run_format(tmp_path: Path):
    with pytest.raises(ValueError, match="Excel, CSV or PDF"):
        await render_run_report(_report(), ExportFormat.SDF, tmp_path / "x.sdf", OPTIONS)


def test_figures_are_vector_and_skip_when_empty():
    report = _report()
    assert "<svg" in traces_svg(report)
    assert "<svg" in shift_svg(report, report.windows[0])
    empty = RunReport(**{**report.__dict__, "rows": (), "signals": ()})
    assert traces_svg(empty) is None and shift_svg(empty, report.windows[0]) is None
