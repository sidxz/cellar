"""Unit tests for the instrument import planning helpers."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

from cellar.application.screening.instrument_export import (
    ExportChannel,
    HolderLayout,
    InstrumentExport,
    ReportedValue,
)
from cellar.application.screening.instrument_import_plan import (
    ReportedSeries,
    label_lookup_candidates,
    readout_mapping_error,
    refuse_instrument_import,
    reported_series,
    suggest_readout,
)
from cellar.domain.screening_assay.enums import HolderKind, ReadoutDataType, RunStatus
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.run import Plate, Run
from cellar.domain.shared.errors import ConflictError

PROTOCOL_ID = uuid.uuid4()


def _definition(
    name: str,
    unit: str | None,
    *,
    data_type: ReadoutDataType = ReadoutDataType.NUMERIC,
    calculated: bool = False,
) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=PROTOCOL_ID,
        name=name,
        data_type=data_type,
        unit=unit,
        is_calculated=calculated,
        calculation_formula="1" if calculated else None,
    )


def _series(label: str = "Onset #1 for Ratio", unit: str = "°C") -> ReportedSeries:
    return ReportedSeries(
        channel="ratio", kind="onset", ordinal=1, label=label, unit=unit, count=1
    )


def _value(column: int, channel: str, kind: str, label: str) -> ReportedValue:
    return ReportedValue(
        row=1,
        column=column,
        channel=channel,
        kind=kind,
        ordinal=1,
        label=label,
        value=50.0,
        unit="°C",
    )


def test_label_lookup_candidates():
    assert label_lookup_candidates("ABC-0000001") == ["ABC-0000001"]
    assert label_lookup_candidates(" ABC-0000001 (Old) ") == ["ABC-0000001 (Old)", "ABC-0000001"]
    assert label_lookup_candidates("") == [] and label_lookup_candidates("   ") == []


def test_reported_series_groups_and_warns_on_undeclared_channel():
    export = InstrumentExport(
        reader="stub",
        holder=HolderLayout(HolderKind.CASSETTE, 1, 3),
        positions=(),
        channels=(ExportChannel("ratio", "Ratio", "°C", None),),
        curves=(),
        reported=(
            _value(1, "ratio", "onset", "Onset #1"),
            _value(1, "ratio", "transition", "Transition #1"),
            _value(2, "ratio", "onset", "Onset #1"),
            _value(2, "ratio", "transition", "Transition #1"),
            _value(3, "ratio", "transition", "Transition #1"),
            _value(3, "ghost", "onset", "Ghost onset"),
        ),
        settings={},
    )
    series, warnings = reported_series(export)
    assert [(s.key, s.count) for s in series] == [
        (("ratio", "onset", 1), 2),
        (("ratio", "transition", 1), 3),
    ]
    # Named by its label; the signal's internal key is not shown.
    assert warnings == [
        "Reported value 'Ghost onset' belongs to a signal the file has no traces for. "
        "It is skipped."
    ]


def test_readout_mapping_error_cases():
    series_celsius = _series()
    numeric_celsius = _definition("Onset", "°C")
    numeric_percent = _definition("Onset", "%")
    calculated_celsius = _definition("Onset", "°C", calculated=True)
    text_readout = _definition("Onset", None, data_type=ReadoutDataType.TEXT)

    assert readout_mapping_error(series_celsius, numeric_celsius) is None
    err = str(readout_mapping_error(series_celsius, numeric_percent))
    assert "°C" in err and "%" in err
    assert readout_mapping_error(series_celsius, calculated_celsius) is not None
    assert readout_mapping_error(series_celsius, text_readout) is not None
    assert readout_mapping_error(series_celsius, None) is not None


def test_readout_mapping_accepts_unit_spelling_variants():
    assert readout_mapping_error(_series(unit="degC"), _definition("Onset", "°C")) is None


def test_suggest_readout_needs_same_name_ignoring_case_and_same_unit():
    same_name = _definition("onset #1 for ratio", "°C")
    assert suggest_readout(_series("Onset #1 for Ratio"), [same_name]) == same_name.id
    assert suggest_readout(_series("Onset #1 for Ratio"), [_definition("Onset", "°C")]) is None
    assert (
        suggest_readout(_series("Onset #1 for Ratio"), [_definition("Onset #1 for Ratio", "%")])
        is None
    )


def _run(
    *, status: RunStatus = RunStatus.DRAFT, locked: bool = False, with_holder: bool = False
) -> Run:
    run = Run(
        workspace_id=uuid.uuid4(),
        protocol_id=PROTOCOL_ID,
        run_date=date(2026, 11, 12),
        operator=uuid.uuid4(),
        status=status,
        is_locked=locked,
    )
    if with_holder:
        run.plates.append(Plate(run_id=run.id, plate_number=1))
    return run


def _repo(wellless: bool = False) -> AsyncMock:
    repo = AsyncMock()
    repo.has_wellless_rows = AsyncMock(return_value=wellless)
    return repo


async def test_refuse_instrument_import_order():
    # Every reason at once: the lock is named first.
    run = _run(status=RunStatus.COMPLETED, locked=True, with_holder=True)
    err = await refuse_instrument_import(run, _repo(wellless=True))
    assert isinstance(err, ConflictError) and "locked" in str(err)

    run = _run(status=RunStatus.COMPLETED, with_holder=True)
    err = await refuse_instrument_import(run, _repo(wellless=True))
    assert isinstance(err, ConflictError) and "'completed'" in str(err)

    run = _run(with_holder=True)
    repo = _repo(wellless=True)
    err = await refuse_instrument_import(run, repo)
    assert isinstance(err, ConflictError) and "well-less" in str(err)
    repo.has_wellless_rows.assert_awaited_once_with(run.workspace_id, run.id)

    err = await refuse_instrument_import(_run(with_holder=True), _repo())
    assert isinstance(err, ConflictError) and "Reset" in str(err)

    assert await refuse_instrument_import(_run(), _repo()) is None
    assert await refuse_instrument_import(_run(status=RunStatus.IN_PROGRESS), _repo()) is None


def test_mapping_a_transition_is_refused_with_the_step_message():
    step = ReportedSeries("ratio", "transition", 1, "Transition #1", "°C", 3)
    err = readout_mapping_error(step, _definition("Tm", "°C"))
    assert str(err) == (
        "'Transition #1' is a melting step. Steps are kept on each position and compared "
        "in temperature windows; they cannot be mapped to a readout."
    )
    # Checked first: even with no readout chosen.
    assert "melting step" in str(readout_mapping_error(step, None))


def test_mapping_onto_a_melt_readout_is_refused():
    from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig

    melt = ReadoutDefinition(
        protocol_id=PROTOCOL_ID,
        name="Tm (Main)",
        data_type=ReadoutDataType.NUMERIC,
        unit="°C",
        melt_config=MeltReadoutConfig("Main", MeltMeasure.TM, "ratio", 50.0, 85.0),
    )
    assert "derived" in str(readout_mapping_error(_series(), melt))
