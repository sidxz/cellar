"""Unit tests for the Prometheus raw-export reader, against synthetic workbooks."""

from __future__ import annotations

import io
import math
import os
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from cellar.application.screening.instrument_export import HolderLayout, InstrumentFileError
from cellar.domain.screening_assay.enums import HolderKind
from cellar.infrastructure.instrument_readers.prometheus_raw_xlsx import PrometheusRawXlsxReader
from tests.helpers.instrument_workbook import (
    build_processed_workbook,
    build_raw_workbook,
    temperature,
)

READER = PrometheusRawXlsxReader()


def plain_workbook_bytes() -> bytes:
    wb = Workbook()
    wb.active.append(["Well", "Value"])
    wb.active.append(["A1", 2])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_reads_synthetic_raw_workbook():
    export = READER.read(build_raw_workbook(), "run.xlsx")
    assert export.reader == "nanotemper-prometheus-raw-xlsx"
    assert export.holder == HolderLayout(HolderKind.CASSETTE, 1, 24)
    assert [(p.row, p.column, p.label) for p in export.positions][:2] == [
        (1, 1, "S1"),
        (1, 2, "S2"),
    ]
    assert [c.key for c in export.channels] == ["ratio", "f330", "f350", "scattering"]
    assert [(c.x_unit, c.y_unit) for c in export.channels] == [
        ("°C", None),
        ("°C", "counts*mm"),
        ("°C", "counts*mm"),
        ("°C", "mAU"),
    ]
    assert all(c.x_label == "Temperature" for c in export.channels)
    assert len(export.curves) == 96 and all(len(c.x) == len(c.y) == 50 for c in export.curves)
    first = next(c for c in export.curves if (c.column, c.channel) == (1, "ratio"))
    assert first.x == tuple(temperature(i) for i in range(50))  # as measured, not resampled


def test_reported_values_and_trailing_space_headers():
    values = READER.read(build_raw_workbook(), "run.xlsx").reported
    assert {(v.kind, v.ordinal, v.channel, v.unit) for v in values} == {
        ("onset", 1, "ratio", "°C"),
        ("transition", 1, "ratio", "°C"),
        ("transition", 2, "ratio", "°C"),
    }
    assert sum(v.kind == "transition" and v.ordinal == 2 for v in values) == 12  # odd positions
    assert {v.label for v in values if v.kind == "onset"} == {"Onset #1 for Ratio"}


def test_blank_sample_names_give_empty_labels():
    export = READER.read(build_raw_workbook(positions={n: None for n in range(1, 25)}), "run.xlsx")
    assert len(export.positions) == 24 and all(p.label == "" for p in export.positions)
    assert len(export.curves) == 96


def test_ragged_columns_and_missing_cells():
    data = build_raw_workbook(
        positions={1: "a", 2: "b", 3: "c"},
        points={1: 10, 2: 7, 3: 10},
        cells={("Ratio", 3, 4, "value"): None},
    )
    curves = {c.column: c for c in READER.read(data, "run.xlsx").curves if c.channel == "ratio"}
    assert [len(curves[n].x) for n in (1, 2, 3)] == [10, 7, 9]
    assert curves[1].x == tuple(temperature(i) for i in range(10))
    assert curves[3].x == tuple(temperature(i) for i in range(10) if i != 4)
    assert all(len(c.x) == len(c.y) for c in curves.values())


def test_text_and_error_cells_are_dropped():
    data = build_raw_workbook(
        positions={1: "a"},
        points=6,
        cells={("Ratio", 1, 2, "value"): "NaN", ("Ratio", 1, 3, "temperature"): "#N/A"},
    )
    (curve,) = [c for c in READER.read(data, "run.xlsx").curves if c.channel == "ratio"]
    assert len(curve.x) == 4 and all(math.isfinite(v) for v in curve.x + curve.y)


def test_position_gaps_and_numbers_above_24():
    export = READER.read(
        build_raw_workbook(positions={1: "a", 2: "b", 5: "c", 48: "d"}), "run.xlsx"
    )
    assert [p.column for p in export.positions] == [1, 2, 5, 48] and export.holder.columns == 48


@pytest.mark.parametrize("number", [0, -1])
def test_position_number_below_one_is_refused(number):
    data = build_raw_workbook(positions={number: "a", 1: "b"})
    with pytest.raises(InstrumentFileError, match=f"capillary {number}; .* start at 1"):
        READER.read(data, "run.xlsx")


def test_position_listed_twice_is_refused():
    wb = load_workbook(io.BytesIO(build_raw_workbook(positions={1: "a", 2: "b"})))
    wb["Overview"].append([1, "again"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(InstrumentFileError, match="capillary 1 more than once"):
        READER.read(buf.getvalue(), "run.xlsx")


def test_reported_value_for_a_channel_without_a_sheet_keeps_its_channel_key():
    data = build_raw_workbook(sheets=("Ratio",), reported={"Onset #1 for Scattering ": {1: 55.0}})
    (value,) = READER.read(data, "run.xlsx").reported
    assert value.channel == "scattering"
    assert [c.key for c in READER.read(data, "run.xlsx").channels] == ["ratio"]


def test_other_three_column_sheet_becomes_a_channel_keyed_by_its_title():
    export = READER.read(build_raw_workbook(sheets=("Ratio", "Turbidity")), "run.xlsx")
    assert [(c.key, c.label) for c in export.channels] == [
        ("ratio", "Ratio 350/330"),
        ("Turbidity", "Turbidity"),
    ]


def test_settings_come_from_the_first_position_row():
    settings = READER.read(build_raw_workbook(), "run.xlsx").settings
    assert set(settings) == {
        "Excitation Power",
        "Start Temperature",
        "End Temperature",
        "Temperature Slope",
        "Start Time",
        "Duration",
    }
    assert settings["Start Temperature"] == "25"


def test_processed_layout_is_refused_asking_for_raw():
    data = build_processed_workbook()
    assert READER.recognises(data, "processed.xlsx") is True
    with pytest.raises(InstrumentFileError, match="raw"):
        READER.read(data, "processed.xlsx")


def test_does_not_recognise_other_files():
    assert READER.recognises(b"Well,Value\nA1,2\n", "x.csv") is False
    assert READER.recognises(plain_workbook_bytes(), "x.xlsx") is False  # one sheet, no Overview
    assert READER.recognises(b"PK\x03\x04 not a zip", "x.xlsx") is False


@pytest.mark.skipif(
    not os.environ.get("CELLAR_NANODSF_SAMPLE_DIR"), reason="CELLAR_NANODSF_SAMPLE_DIR is not set"
)
def test_real_files_when_sample_dir_set():
    # Every *.xlsx the reader recognises in the folder. The files are opened read-only and never
    # copied. No file name appears in this test; a workbook is identified by its counts.
    seen = set()
    for path in sorted(Path(os.environ["CELLAR_NANODSF_SAMPLE_DIR"]).glob("*.xlsx")):
        content = path.read_bytes()
        if not READER.recognises(content, path.name):
            continue
        try:
            export = READER.read(content, path.name)
        except InstrumentFileError:
            continue  # a processed export in the folder
        assert len(export.positions) == 24 and len(export.channels) == 4
        seen.add(
            (
                sum(v.kind == "transition" for v in export.reported),
                sum(v.kind == "onset" for v in export.reported),
                all(p.label == "" for p in export.positions),
                {len(c.x) for c in export.curves} == {1223},
            )
        )
    assert (42, 24, False, True) in seen  # labelled run: 1,223 points on every curve
    assert any(s[:3] == (41, 21, True) for s in seen)  # run with blank labels


def test_reader_tells_the_user_which_export_to_make():
    assert READER.hint == (
        "Export the raw data from the instrument's software as an Excel workbook. "
        "The processed export is not supported."
    )
