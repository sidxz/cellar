"""build_wells_dataset: readout rows → one columnar row per well (or well-less key)."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, timedelta

from cellar.application.visualization.dataset import build_wells_dataset
from cellar.application.visualization.dataset_reader import ReadoutDefInfo, RunInfo, WellValueRow

P = uuid.uuid4()
RD = uuid.uuid4()
TXT = uuid.uuid4()
OP = uuid.uuid4()
T0 = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


def _run(day: int = 12, *, conditions=None, minutes: int = 0) -> RunInfo:
    return RunInfo(
        id=uuid.uuid4(),
        protocol_id=P,
        run_date=date(2026, 11, day),
        operator_id=OP,
        status="approved",
        conditions=conditions,
        created_at=T0 + timedelta(minutes=minutes),
    )


DEFS = [
    ReadoutDefInfo(
        id=RD, protocol_id=P, name="Signal", data_type="numeric", unit="AU", display_order=0
    ),
    ReadoutDefInfo(
        id=TXT, protocol_id=P, name="Call", data_type="text", unit=None, display_order=1
    ),
]


def _row(run: RunInfo, **kw) -> WellValueRow:
    base = dict(
        run_id=run.id,
        well_id=uuid.uuid4(),
        plate_id=uuid.uuid4(),
        plate_number=1,
        plate_barcode=None,
        plate_format="384",
        holder_rows=None,
        holder_columns=None,
        well_row="B",
        well_column=3,
        well_type="sample",
        dose=None,
        well_label=None,
        molecule_id=uuid.uuid4(),
        registration_number="CEL-000001",
        smiles="CCO",
        batch_id=None,
        batch_number=None,
        readout_definition_id=RD,
        normalization_applied=None,
        value_numeric=0.5,
        value_qualifier=None,
        value_text=None,
        is_outlier=False,
        created_at=T0,
    )
    base.update(kw)
    return WellValueRow(**base)


def _col(ds, key):
    return next(c for c in ds.columns if c.key == key)


RAW = f"rd:{RD}:raw"
INH = f"rd:{RD}:percent_inhibition"


def test_two_layers_of_one_readout_pivot_onto_one_row():
    run = _run()
    w = uuid.uuid4()
    rows = [
        _row(run, well_id=w, value_numeric=0.42),
        _row(run, well_id=w, normalization_applied="percent_inhibition", value_numeric=61.0),
    ]
    ds = build_wells_dataset([run], DEFS, rows)
    assert len(ds.row_ids) == 1
    assert ds.values[RAW] == [0.42]
    assert ds.values[INH] == [61.0]
    assert _col(ds, RAW).label == "Signal (AU)" and _col(ds, RAW).unit == "AU"
    assert _col(ds, INH).label == "Signal · % Inhibition" and _col(ds, INH).unit == "%"
    assert _col(ds, RAW).group == "Signal" and _col(ds, RAW).kind == "number"


def test_raw_label_skips_the_unit_when_the_name_already_ends_with_it():
    run = _run()
    rd_ids = [uuid.uuid4(), uuid.uuid4()]
    defs = [
        ReadoutDefInfo(
            id=i, protocol_id=P, name=name, data_type="numeric", unit="AU", display_order=0
        )
        for i, name in zip(rd_ids, ["raw AU", "Raw au"], strict=True)
    ]
    rows = [_row(run, readout_definition_id=i) for i in rd_ids]
    ds = build_wells_dataset([run], defs, rows)
    assert [_col(ds, f"rd:{i}:raw").label for i in rd_ids] == ["raw AU", "Raw au"]


def test_well_order_on_a_384_plate():
    run = _run()
    ds = build_wells_dataset([run], DEFS, [_row(run, well_row="B", well_column=3)])
    assert ds.values["well_order"] == [27]
    assert ds.values["well"] == ["B03"]
    assert ds.values["plate"] == ["Plate 1"]


def test_wellless_row_has_null_plate_and_well():
    run = _run()
    mol = uuid.uuid4()
    row = _row(
        run,
        well_id=None,
        plate_id=None,
        plate_number=None,
        plate_format=None,
        well_row=None,
        well_column=None,
        well_type=None,
        molecule_id=mol,
    )
    ds = build_wells_dataset([run], DEFS, [row])
    assert ds.row_ids == [f"{run.id}:m:{mol}:-"]
    assert ds.values["plate"] == [None]
    assert ds.values["well"] == [None]
    assert ds.values["well_order"] == [None]


def test_duplicate_value_keeps_the_latest_created():
    run = _run()
    w = uuid.uuid4()
    later = _row(run, well_id=w, value_numeric=2.0, created_at=T0 + timedelta(seconds=5))
    earlier = _row(run, well_id=w, value_numeric=1.0, created_at=T0)
    ds = build_wells_dataset([run], DEFS, [later, earlier])
    assert ds.values[RAW] == [2.0]


def test_a_newer_null_keeps_the_older_value_and_its_flags():
    run = _run()
    w = uuid.uuid4()
    older = _row(run, well_id=w, value_numeric=1.0, value_qualifier=">", is_outlier=True)
    newer = _row(run, well_id=w, value_numeric=None, created_at=T0 + timedelta(seconds=5))
    ds = build_wells_dataset([run], DEFS, [older, newer])
    assert ds.values[RAW] == [1.0]
    assert ds.values[f"{RAW}:q"] == [">"]
    assert ds.values[f"{RAW}:outlier"] == ["outlier"]


def test_a_newer_value_without_flags_clears_the_older_ones():
    run = _run()
    w = uuid.uuid4()
    older = _row(run, well_id=w, value_numeric=1.0, value_qualifier=">", is_outlier=True)
    newer = _row(run, well_id=w, value_numeric=2.0, created_at=T0 + timedelta(seconds=5))
    ds = build_wells_dataset([run], DEFS, [older, newer])
    assert ds.values[RAW] == [2.0]
    keys = {c.key for c in ds.columns}
    assert f"{RAW}:q" not in keys and f"{RAW}:outlier" not in keys


def test_qualifier_goes_to_a_sibling_column_and_the_number_stays():
    run = _run()
    ds = build_wells_dataset([run], DEFS, [_row(run, value_numeric=10.0, value_qualifier=">")])
    assert ds.values[RAW] == [10.0]
    assert ds.values[f"{RAW}:q"] == [">"]


def test_siblings_only_when_present():
    run = _run()
    ds = build_wells_dataset([run], DEFS, [_row(run)])
    keys = {c.key for c in ds.columns}
    assert f"{RAW}:q" not in keys and f"{RAW}:outlier" not in keys


def test_outlier_flag_column():
    run = _run()
    ds = build_wells_dataset([run], DEFS, [_row(run, is_outlier=True)])
    assert ds.values[f"{RAW}:outlier"] == ["outlier"]


def test_nan_becomes_null():
    run = _run()
    ds = build_wells_dataset([run], DEFS, [_row(run, value_numeric=math.nan)])
    assert ds.values[RAW] == [None]


def test_condition_keys_from_two_runs_share_one_column():
    a = _run(12, conditions={"NADP": "+"})
    b = _run(13, conditions={"NADP": "-"})
    ds = build_wells_dataset([a, b], DEFS, [_row(a), _row(b)])
    assert sorted(ds.values["cond:NADP"]) == ["+", "-"]
    assert _col(ds, "cond:NADP").kind == "category"


def test_text_readout_becomes_a_category_column():
    run = _run()
    ds = build_wells_dataset(
        [run], DEFS, [_row(run, readout_definition_id=TXT, value_numeric=None, value_text="hit")]
    )
    key = f"rd:{TXT}:raw"
    assert _col(ds, key).kind == "category"
    assert ds.values[key] == ["hit"]


def test_identity_columns_carry_no_uuids():
    a = _run(12, minutes=0)
    b = _run(12, minutes=5)  # same date → disambiguated
    ds = build_wells_dataset([a, b], DEFS, [_row(a), _row(b, plate_barcode="BC-9")])
    assert ds.values["run"] == ["2026-11-12 #1", "2026-11-12 #2"]
    assert ds.values["plate"] == ["Plate 1", "BC-9"]
    assert ds.values["compound"] == ["CEL-000001", "CEL-000001"]
    for key in ("run", "plate", "compound", "well", "well_type"):
        for v in ds.values[key]:
            assert v is None or not _looks_like_uuid(str(v))
    assert _col(ds, "operator").kind == "user"
    assert _col(ds, "molecule_id").hidden is True


def test_single_run_per_date_has_plain_label_and_revision_is_stable():
    run = _run()
    rows = [_row(run)]
    ds = build_wells_dataset([run], DEFS, rows)
    assert ds.values["run"] == ["2026-11-12"]
    assert build_wells_dataset([run], DEFS, rows).revision == ds.revision
    assert ds.level == "wells"


def _looks_like_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False
