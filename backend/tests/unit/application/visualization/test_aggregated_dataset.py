"""build_aggregated_dataset: shared aggregation rows → Runs / Batches / Compounds datasets."""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from cellar.application.screening.compound_curves_reader import CurveRow
from cellar.application.screening.protocol_activity_reader import (
    ActivityAggregates,
    DRAggRow,
    NumericReadoutRow,
)
from cellar.application.visualization.aggregated_dataset import (
    build_aggregated_dataset,
    plan_aggregated,
)
from cellar.application.visualization.dataset_reader import CompoundInfo, ReadoutDefInfo, RunInfo

P = uuid.uuid4()
RD = uuid.uuid4()  # numeric "Signal" (AU)
POT = uuid.uuid4()  # numeric "Potency" (µM)
DR = uuid.uuid4()  # dose-response "Enzyme" (ic50, µM)
OP = uuid.uuid4()
WS = uuid.uuid4()
T0 = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

DEFS = [
    ReadoutDefInfo(
        id=RD, protocol_id=P, name="Signal", data_type="numeric", unit="AU", display_order=0
    ),
    ReadoutDefInfo(
        id=POT, protocol_id=P, name="Potency", data_type="numeric", unit="µM", display_order=1
    ),
    ReadoutDefInfo(
        id=DR,
        protocol_id=P,
        name="Enzyme",
        data_type="dose_response",
        unit=None,
        display_order=2,
        dose_unit="uM",
        curve_type="ic50",
    ),
]
SIG = f"rd:{RD}:raw"
POTK = f"rd:{POT}:raw"
DRK = f"dr:{DR}"


def _run(day: int = 12, *, conditions=None, status: str = "approved", minutes: int = 0):
    return RunInfo(
        id=uuid.uuid4(),
        protocol_id=P,
        run_date=date(2026, 11, day),
        operator_id=OP,
        status=status,
        conditions=conditions,
        created_at=T0 + timedelta(minutes=minutes),
    )


def _mol(reg: str = "CEL-000001", mw: float | None = 300.0) -> CompoundInfo:
    return CompoundInfo(
        registration_number=reg,
        smiles="CCO",
        molecular_weight=mw,
        logp=1.5,
        tpsa=40.0,
        hbd=1,
        hba=2,
        rotatable_bonds=3,
        aromatic_rings=1,
    )


def _num(mol: uuid.UUID, rd: uuid.UUID = RD, **kw) -> NumericReadoutRow:
    base = dict(
        molecule_id=mol,
        readout_name="Signal",
        best=20.0,
        mean=15.0,
        n=2,
        sd=7.07,
        low=10.0,
        layer=None,
        readout_definition_id=rd,
    )
    base.update(kw)
    return NumericReadoutRow(**base)


def _dr(mol: uuid.UUID, **kw) -> DRAggRow:
    base = dict(
        molecule_id=mol,
        readout_definition_id=DR,
        best=0.1,
        geo_mean=0.316,
        n_tested=3,
        n_inactive=1,
        n_used=2,
    )
    base.update(kw)
    return DRAggRow(**base)


def _curve(run: RunInfo, mol: uuid.UUID, batch: uuid.UUID, **kw) -> CurveRow:
    base = dict(
        id=uuid.uuid4(),
        workspace_id=WS,
        molecule_id=mol,
        batch_id=batch,
        protocol_id=P,
        run_id=run.id,
        readout_definition_id=DR,
        curve_type="ic50",
        fitted_value=1.5,
        hill_slope=1.1,
        top=100.0,
        bottom=0.0,
        r_squared=0.98,
        confidence_interval_low=1.0,
        confidence_interval_high=2.2,
        num_points=3,
        curve_class="full",
        raw_data=[
            {"concentration": 0.1, "response": 5.0},
            {"concentration": 1.0, "response": 40.0},
            {"concentration": 10.0, "response": 95.0},
        ],
        excluded_points=None,
    )
    base.update(kw)
    return CurveRow(**base)


def _build(
    level, *, numeric=(), dr=(), curves=(), runs=None, molecules=None, batches=None, defs=DEFS
):
    return build_aggregated_dataset(
        level,
        runs if runs is not None else [_run()],
        defs,
        ActivityAggregates(numeric_rows=list(numeric), dr_agg_rows=list(dr)),
        list(curves),
        molecules or {},
        batches or {},
    )


def _col(ds, key):
    return next(c for c in ds.columns if c.key == key)


def _keys(ds):
    return {c.key for c in ds.columns}


# --- condition sets ---------------------------------------------------------------


def test_two_condition_sets_give_two_labeled_columns_on_one_row():
    mol = uuid.uuid4()
    rows = [
        _num(mol, conditions={"NADP": "+"}, mean=10.0),
        _num(mol, conditions={"NADP": "-"}, mean=30.0),
    ]
    ds = _build("compounds", numeric=rows, molecules={mol: _mol()})
    assert ds.row_ids == [str(mol)]
    signal = [c for c in ds.columns if c.key.startswith(f"{SIG}@") and c.provenance.stat is None]
    assert sorted(c.label for c in signal) == ["Signal (AU) · NADP: +", "Signal (AU) · NADP: -"]
    by_label = {c.label: c for c in signal}
    assert by_label["Signal (AU) · NADP: +"].provenance.condition_set == "NADP: +"
    assert ds.values[by_label["Signal (AU) · NADP: +"].key] == [10.0]
    assert ds.values[by_label["Signal (AU) · NADP: -"].key] == [30.0]


def test_one_condition_set_keeps_the_wells_key_and_a_plain_label():
    mol = uuid.uuid4()
    ds = _build("compounds", numeric=[_num(mol, conditions={"NADP": "+"})])
    assert _col(ds, SIG).label == "Signal (AU)"
    assert _col(ds, SIG).provenance.condition_set is None
    assert ds.values[SIG] == [15.0]


def test_empty_and_all_null_conditions_are_one_set():
    a, b = uuid.uuid4(), uuid.uuid4()
    rows = [_num(a, conditions={}), _num(b, conditions={"NADP": None}), _num(a, rd=POT)]
    ds = _build("batches", numeric=rows)
    assert SIG in _keys(ds) and POTK in _keys(ds)
    assert not any("@" in k for k in _keys(ds))


def test_normalized_layer_reads_readout_then_condition_then_layer():
    mol = uuid.uuid4()
    rows = [
        _num(mol, layer="percent_inhibition", conditions={"NADP": "+"}),
        _num(mol, layer="percent_inhibition", conditions={}),
    ]
    ds = _build("compounds", numeric=rows)
    labels = sorted(
        c.label for c in ds.columns if c.provenance.stat is None and c.key.startswith("rd:")
    )
    assert labels == ["Signal · NADP: + · % Inhibition", "Signal · no conditions · % Inhibition"]


# --- numeric values: censored rules -------------------------------------------------


def test_censored_values_stay_out_of_the_mean_and_are_counted():
    mol = uuid.uuid4()
    ds = _build("compounds", numeric=[_num(mol, n=2, mean=15.0, gt_count=1, gt_bound=50.0)])
    assert ds.values[SIG] == [15.0]
    assert f"{SIG}:q" not in _keys(ds)
    assert ds.values[f"{SIG}:n_censored"] == [1]
    assert ds.values[f"{SIG}:n"] == [2]
    assert ds.values[f"{SIG}:best"] == [20.0]  # a signal reads high
    assert _col(ds, SIG).provenance.aggregation == "mean"


def test_all_censored_reports_the_bound_and_flips_the_p_qualifier():
    mol = uuid.uuid4()
    row = _num(
        mol, rd=POT, n=0, mean=None, sd=None, best=None, low=None, gt_count=2, gt_bound=80.0
    )
    ds = _build("compounds", numeric=[row])
    assert ds.values[POTK] == [80.0]
    assert ds.values[f"{POTK}:q"] == [">"]
    assert ds.values[f"{POTK}:p"] == [pytest.approx(4.097, abs=1e-3)]
    assert ds.values[f"{POTK}:p:q"] == ["<"]
    assert _col(ds, f"{POTK}:p").label == "pPotency"
    assert _col(ds, f"{POTK}:p").provenance.aggregation == "p"
    assert _col(ds, POTK).unit == "µM"


def test_mixed_greater_and_less_bounds_say_nothing():
    mol = uuid.uuid4()
    row = _num(mol, n=0, mean=None, best=None, low=None, gt_count=1, gt_bound=50, lt_count=1)
    ds = _build("compounds", numeric=[row])
    assert ds.values[SIG] == [None]
    assert f"{SIG}:q" not in _keys(ds)


def test_a_non_molar_numeric_readout_has_no_p_column():
    ds = _build("compounds", numeric=[_num(uuid.uuid4())])
    assert f"{SIG}:p" not in _keys(ds)


# --- numeric values: the readout's configured aggregation ---------------------------


@pytest.mark.parametrize(
    ("rd", "aggregation", "level", "value", "named"),
    [
        (POT, "geometric_mean", "compounds", 10.0, "geomean"),
        (POT, "median", "batches", 2.0, "median"),
        (POT, "mean", "compounds", 15.0, "mean"),
        (POT, "none", "compounds", 15.0, "mean"),
        (POT, "geometric_mean", "runs", 10.0, "replicate_geomean"),
        (RD, "geometric_mean", "compounds", 15.0, "mean"),  # AU: no geomean
    ],
)
def test_numeric_values_follow_the_readouts_aggregation(rd, aggregation, level, value, named):
    run = _run()
    defs = [replace(d, aggregation=aggregation) for d in DEFS]
    row = _num(uuid.uuid4(), rd=rd, run_id=run.id, median=2.0, geomean=10.0)
    ds = _build(level, numeric=[row], runs=[run], defs=defs)
    key = f"rd:{rd}:raw"
    assert ds.values[key] == [value]
    assert _col(ds, key).provenance.aggregation == named


def test_a_geomean_counts_the_values_it_leaves_out():
    defs = [replace(DEFS[1], aggregation="geometric_mean")]
    mol = uuid.uuid4()
    ds = _build(
        "compounds", numeric=[_num(mol, rd=POT, geomean=10.0, nonpositive_count=2)], defs=defs
    )
    assert ds.values[f"{POTK}:n_nonpositive"] == [2]
    assert _col(ds, f"{POTK}:n_nonpositive").provenance.stat == "n_nonpositive"
    ds = _build("compounds", numeric=[_num(mol, rd=POT, geomean=10.0)], defs=defs)
    assert f"{POTK}:n_nonpositive" not in _keys(ds)


# --- dose-response at batches / compounds ------------------------------------------


def test_dose_response_counts_inactive_runs():
    mol = uuid.uuid4()
    ds = _build("compounds", dr=[_dr(mol)])
    assert ds.values[DRK] == [0.316]
    assert ds.values[f"{DRK}:n_tested"] == [3]
    assert ds.values[f"{DRK}:n_inactive"] == [1]
    assert ds.values[f"{DRK}:n_used"] == [2]
    assert ds.values[f"{DRK}:best"] == [0.1]
    col = _col(ds, DRK)
    assert col.label == "Enzyme · IC50" and col.unit == "µM"
    assert col.provenance.aggregation == "geomean"
    assert _col(ds, f"{DRK}:p").label == "Enzyme · pIC50"


def test_all_inactive_curves_give_no_value():
    mol = uuid.uuid4()
    ds = _build(
        "compounds", dr=[_dr(mol, best=None, geo_mean=None, n_tested=3, n_inactive=3, n_used=0)]
    )
    assert ds.values[DRK] == [None]
    assert ds.values[f"{DRK}:n_inactive"] == [3]


@pytest.mark.parametrize(("dose_unit", "p"), [("nM", 7.0), ("mg/mL", None)])
def test_dose_response_p_column_needs_a_molar_dose_unit(dose_unit, p):
    defs = [
        ReadoutDefInfo(
            id=DR,
            protocol_id=P,
            name="IC50",
            data_type="dose_response",
            unit=None,
            display_order=0,
            dose_unit=dose_unit,
            curve_type="ic50",
        )
    ]
    mol = uuid.uuid4()
    ds = build_aggregated_dataset(
        "compounds",
        [_run()],
        defs,
        ActivityAggregates(numeric_rows=[], dr_agg_rows=[_dr(mol, geo_mean=100.0)]),
        [],
        {},
        {},
    )
    assert _col(ds, DRK).label == "IC50"  # the name already says IC50
    if p is None:
        assert f"{DRK}:p" not in _keys(ds)
    else:
        assert ds.values[f"{DRK}:p"] == [pytest.approx(p)]
        assert _col(ds, f"{DRK}:p").label == "IC50 · pIC50"


# --- runs ---------------------------------------------------------------------------


def test_runs_level_reads_the_runs_fit():
    run = _run(conditions={"NADP": "+"})
    mol, batch = uuid.uuid4(), uuid.uuid4()
    ds = _build(
        "runs",
        curves=[_curve(run, mol, batch)],
        runs=[run],
        molecules={mol: _mol()},
        batches={batch: "CEL-000001-01"},
    )
    assert ds.row_ids == [f"{run.id}:{mol}:{batch}"]
    assert ds.values[DRK] == [1.5]
    assert ds.values[f"{DRK}:r_squared"] == [0.98]
    assert ds.values[f"{DRK}:min_dose"] == [0.1]
    assert ds.values[f"{DRK}:max_dose"] == [10.0]
    assert ds.values[f"{DRK}:points"] == [
        [{"x": 0.1, "y": 5.0}, {"x": 1.0, "y": 40.0}, {"x": 10.0, "y": 95.0}]
    ]
    assert _col(ds, f"{DRK}:ci_low").hidden is True
    assert _col(ds, f"{DRK}:points").hidden is True
    assert _col(ds, f"{DRK}:r_squared").hidden is False
    assert _col(ds, DRK).provenance.aggregation == "fit"
    assert ds.values["run"] == ["2026-11-12"]
    assert ds.values["run_status"] == ["approved"]
    assert ds.values["cond:NADP"] == ["+"]
    assert ds.values["batch"] == ["CEL-000001-01"]
    assert ds.values["operator"] == [str(OP)]
    assert ds.level == "runs"


def test_runs_level_inactive_curve_reads_above_its_top_dose():
    run = _run()
    ds = _build(
        "runs",
        curves=[_curve(run, uuid.uuid4(), uuid.uuid4(), curve_class="inactive")],
        runs=[run],
    )
    assert ds.values[DRK] == [10.0]
    assert ds.values[f"{DRK}:q"] == [">"]
    assert ds.values[f"{DRK}:curve_class"] == ["inactive"]
    assert _col(ds, f"{DRK}:curve_class").kind == "category"


def test_runs_level_inactive_curve_without_doses_has_no_value():
    run = _run()
    curve = _curve(run, uuid.uuid4(), uuid.uuid4(), curve_class="inactive", raw_data=[])
    ds = _build("runs", curves=[curve], runs=[run])
    assert ds.values[DRK] == [None]


@pytest.mark.parametrize(
    ("fitted", "value", "q", "pq"),
    [(42.0, 10.0, ">", "<"), (0.004, 0.1, "<", ">"), (0.1, 0.1, None, None)],
)
def test_runs_level_fit_outside_the_doses_reads_as_the_dose_bound(fitted, value, q, pq):
    run = _run()
    ds = _build("runs", curves=[_curve(run, uuid.uuid4(), uuid.uuid4(), fitted_value=fitted)])
    assert ds.values[DRK] == [value]
    assert ds.values.get(f"{DRK}:q", [None]) == [q]
    assert ds.values.get(f"{DRK}:p:q", [None]) == [pq]


def test_runs_level_numeric_is_a_replicate_mean():
    run = _run()
    mol = uuid.uuid4()
    ds = _build("runs", numeric=[_num(mol, run_id=run.id)], runs=[run])
    assert ds.row_ids == [f"{run.id}:{mol}:-"]
    assert _col(ds, SIG).provenance.aggregation == "replicate_mean"


def test_a_curve_alone_makes_a_row_with_structure_and_descriptors():
    run = _run()
    mol, other, batch = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ds = _build(
        "runs",
        numeric=[_num(other, run_id=run.id)],
        curves=[_curve(run, mol, batch)],
        runs=[run],
        molecules={mol: _mol("CEL-000002"), other: _mol("CEL-000001")},
    )
    i = ds.values["compound"].index("CEL-000002")
    assert ds.values["structure"][i] == "CCO"
    assert ds.values["molecular_weight"][i] == 300.0
    assert ds.values[SIG][i] is None


# --- rows ---------------------------------------------------------------------------


def test_a_batchless_row_is_its_own_row():
    mol, batch = uuid.uuid4(), uuid.uuid4()
    rows = [_num(mol, batch_id=batch, mean=1.0), _num(mol, batch_id=None, mean=2.0)]
    ds = _build("batches", numeric=rows, batches={batch: "CEL-000001-01"})
    assert ds.row_ids == [f"{mol}:{batch}", f"{mol}:-"]
    assert ds.values["batch"] == ["CEL-000001-01", None]
    assert ds.values["batch_id"] == [str(batch), None]
    assert ds.values[SIG] == [1.0, 2.0]
    assert _col(ds, "batch_id").hidden is True


def test_rows_order_by_compound_then_batch_then_run_date():
    late, early = _run(14), _run(12)
    a, b = uuid.uuid4(), uuid.uuid4()
    b1, b2 = uuid.uuid4(), uuid.uuid4()
    rows = [
        _num(b, batch_id=b1, run_id=early.id),
        _num(a, batch_id=b2, run_id=late.id),
        _num(a, batch_id=b2, run_id=early.id),
        _num(a, batch_id=b1, run_id=late.id),
    ]
    ds = _build(
        "runs",
        numeric=rows,
        runs=[late, early],
        molecules={a: _mol("CEL-000001"), b: _mol("CEL-000002")},
        batches={b1: "01", b2: "02"},
    )
    assert ds.row_ids == [
        f"{late.id}:{a}:{b1}",
        f"{early.id}:{a}:{b2}",
        f"{late.id}:{a}:{b2}",
        f"{early.id}:{b}:{b1}",
    ]


def test_compounds_level_has_no_batch_or_run_columns():
    ds = _build("compounds", numeric=[_num(uuid.uuid4())])
    assert {"batch", "batch_id", "run", "run_date", "operator"}.isdisjoint(_keys(ds))
    assert _col(ds, "molecule_id").hidden is True


def test_descriptor_columns_on_compounds():
    mol = uuid.uuid4()
    ds = _build("compounds", numeric=[_num(mol)], molecules={mol: _mol()})
    assert ds.values["molecular_weight"] == [300.0]
    assert ds.values["aromatic_rings"] == [1]
    col = _col(ds, "molecular_weight")
    assert (col.label, col.kind, col.group) == ("MW", "number", "Descriptors")
    assert [c.label for c in ds.columns if c.group == "Descriptors"] == [
        "MW",
        "logP",
        "TPSA",
        "HBD",
        "HBA",
        "Rotatable bonds",
        "Aromatic rings",
    ]


def test_no_uuids_in_visible_values_and_every_sibling_has_a_stat():
    run_a, run_b = _run(12, conditions={"NADP": "+"}), _run(13, conditions={"NADP": "-"})
    mol, batch = uuid.uuid4(), uuid.uuid4()
    numeric = [
        _num(mol, batch_id=batch, run_id=run_a.id, gt_count=1, gt_bound=9.0),
        _num(mol, rd=POT, batch_id=batch, run_id=run_b.id, n=0, gt_count=1, gt_bound=9.0),
    ]
    curves = [_curve(run_a, mol, batch), _curve(run_b, mol, batch, curve_class="inactive")]
    for level in ("runs", "batches", "compounds"):
        ds = _build(
            level,
            numeric=[
                r if level == "runs" else _num_with_conditions(r, run_a, run_b) for r in numeric
            ],
            dr=[_dr(mol, batch_id=batch, conditions={"NADP": "+"})] if level != "runs" else [],
            curves=curves if level == "runs" else [],
            runs=[run_a, run_b],
            molecules={mol: _mol()},
            batches={batch: "CEL-000001-01"},
        )
        for c in ds.columns:
            if c.hidden or c.kind not in ("category", "text"):
                continue
            for v in ds.values[c.key]:
                assert v is None or not _looks_like_uuid(str(v)), (level, c.key, v)
        value_keys = {
            c.key
            for c in ds.columns
            if c.key.startswith(("rd:", "dr:")) and c.provenance.stat is None
        }
        for c in ds.columns:
            if c.key.startswith(("rd:", "dr:")) and c.key not in value_keys:
                assert c.key.endswith(":p") or c.provenance.stat, (level, c.key)


def test_revision_is_stable_and_follows_the_rows():
    mol = uuid.uuid4()
    run = _run()
    a = _build("compounds", numeric=[_num(mol)], runs=[run])
    b = _build("compounds", numeric=[_num(mol)], runs=[run])
    c = _build("batches", numeric=[_num(mol)], runs=[run])
    assert a.revision == b.revision != c.revision


def test_100k_compounds_build_quickly():
    mols = [uuid.uuid4() for _ in range(100_000)]
    numeric = [_num(m, gt_count=i % 2) for i, m in enumerate(mols)]
    dr = [_dr(m) for m in mols]
    molecules = {m: _mol(f"CEL-{i:06d}") for i, m in enumerate(mols)}
    start = time.perf_counter()
    ds = _build("compounds", numeric=numeric, dr=dr, molecules=molecules)
    elapsed = time.perf_counter() - start
    assert len(ds.row_ids) == 100_000
    assert elapsed < 5.0, elapsed


def _num_with_conditions(row: NumericReadoutRow, run_a: RunInfo, run_b: RunInfo):
    conditions = run_a.conditions if row.run_id == run_a.id else run_b.conditions
    return replace(row, run_id=None, conditions=conditions)


def _looks_like_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False


@pytest.mark.parametrize(
    ("bound", "q", "p_q"),
    [
        (dict(gt_count=1, gt_bound=10.0, gt_inclusive=True), ">=", "<="),
        (dict(lt_count=1, lt_bound=10.0, lt_inclusive=True), "<=", ">="),
        (dict(gt_count=1, gt_bound=10.0), ">", "<"),
    ],
)
def test_an_inclusive_bound_stays_inclusive_and_flips_inclusive(bound, q, p_q):
    row = _num(uuid.uuid4(), rd=POT, n=0, mean=None, sd=None, best=None, low=None, **bound)
    ds = _build("compounds", numeric=[row])
    assert ds.values[POTK] == [10.0]
    assert ds.values[f"{POTK}:q"] == [q]
    assert ds.values[f"{POTK}:p"] == [pytest.approx(5.0)]
    assert ds.values[f"{POTK}:p:q"] == [p_q]


# --- at-bound primary intercepts are censored at the max dose ------------------------

AT_BOUND = [{"spec": {"kind": "ic", "level": 50.0}, "value": None, "at_bound": True}]


def test_runs_level_at_bound_fit_reads_greater_than_the_max_dose():
    run = _run()
    curve = _curve(run, uuid.uuid4(), uuid.uuid4(), fitted_value=1.0, intercept_values=AT_BOUND)
    ds = _build("runs", curves=[curve], runs=[run])
    assert ds.values[DRK] == [10.0]
    assert ds.values[f"{DRK}:q"] == [">"]
    assert ds.values[f"{DRK}:p"] == [pytest.approx(5.0)]
    assert ds.values[f"{DRK}:p:q"] == ["<"]


def test_runs_level_at_bound_fit_without_doses_has_no_value():
    run = _run()
    curve = _curve(run, uuid.uuid4(), uuid.uuid4(), intercept_values=AT_BOUND, raw_data=[])
    ds = _build("runs", curves=[curve], runs=[run])
    assert ds.values[DRK] == [None]


def test_censored_fits_stay_out_of_the_geomean_and_are_counted():
    mol = uuid.uuid4()
    ds = _build(
        "compounds",
        dr=[_dr(mol, geo_mean=4.0, n_tested=2, n_inactive=0, n_used=1, n_censored=1,
                censored_bound=10.0)],
    )  # fmt: skip
    assert ds.values[DRK] == [4.0]
    assert f"{DRK}:q" not in _keys(ds)
    assert ds.values[f"{DRK}:n_censored"] == [1]
    assert _col(ds, f"{DRK}:n_censored").provenance.stat == "n_censored"


def test_all_censored_fits_report_the_bound():
    mol = uuid.uuid4()
    ds = _build(
        "batches",
        dr=[_dr(mol, best=None, geo_mean=None, n_tested=1, n_inactive=0, n_used=0,
                n_censored=1, censored_bound=10.0)],
    )  # fmt: skip
    assert ds.values[DRK] == [10.0]
    assert ds.values[f"{DRK}:q"] == [">"]
    assert ds.values[f"{DRK}:p"] == [pytest.approx(5.0)]
    assert ds.values[f"{DRK}:p:q"] == ["<"]


def test_all_fits_below_the_doses_report_the_lowest_bound():
    mol = uuid.uuid4()
    ds = _build(
        "compounds",
        dr=[_dr(mol, best=None, geo_mean=None, n_tested=2, n_inactive=0, n_used=0,
                n_censored=2, censored_below=0.01)],
    )  # fmt: skip
    assert ds.values[DRK] == [0.01]
    assert ds.values[f"{DRK}:q"] == ["<"]


def test_fits_censored_both_ways_give_no_value():
    mol = uuid.uuid4()
    ds = _build(
        "compounds",
        dr=[_dr(mol, best=None, geo_mean=None, n_tested=2, n_inactive=1, n_used=0,
                n_censored=2, censored_bound=500.0, censored_below=0.01)],
    )  # fmt: skip
    assert ds.values[DRK] == [None]
    assert f"{DRK}:q" not in _keys(ds)


def test_blank_condition_values_are_absent():
    a, b = uuid.uuid4(), uuid.uuid4()
    ds = _build("compounds", numeric=[_num(a, conditions={"NADP": " "}), _num(b, conditions={})])
    assert not any("@" in k for k in _keys(ds))


def test_sets_differing_only_by_json_type_get_distinct_labels():
    mol = uuid.uuid4()
    rows = [_num(mol, conditions={"pH": 7}), _num(mol, conditions={"pH": "7"})]
    ds = _build("compounds", numeric=rows)
    labels = [c.provenance.condition_set for c in ds.columns if c.key.startswith(f"{SIG}@")]
    labels = sorted({label for label in labels})
    assert labels == ['pH: "7"', "pH: 7"]


# --- provenance.run_ids: the runs behind each value column ----------------------------


def test_each_condition_sets_columns_name_the_runs_of_that_set():
    plus, minus = _run(12, conditions={"NADP": "+", "pH": ""}), _run(13, conditions={"NADP": "-"})
    plus2 = _run(14, conditions={"NADP": "+"})
    mol = uuid.uuid4()
    rows = [_num(mol, conditions={"NADP": "+"}), _num(mol, conditions={"NADP": "-"})]
    ds = _build("compounds", numeric=rows, runs=[plus, minus, plus2])
    by_set = {
        c.provenance.condition_set: c.provenance.run_ids
        for c in ds.columns
        if c.key.startswith(f"{SIG}@") and c.provenance.stat is None
    }
    assert by_set == {"NADP: +": (plus.id, plus2.id), "NADP: -": (minus.id,)}


def test_one_condition_set_names_every_run_on_value_columns_only():
    a, b = _run(12), _run(13, conditions={"NADP": "+"})
    mol = uuid.uuid4()
    ds = _build("batches", numeric=[_num(mol, rd=POT)], dr=[_dr(mol)], runs=[a, b])
    for key in (POTK, f"{POTK}:p", DRK, f"{DRK}:p"):
        assert _col(ds, key).provenance.run_ids == (a.id, b.id), key
    assert _col(ds, f"{POTK}:n").provenance.run_ids is None


def test_pick_list_and_text_readouts_are_never_aggregated():
    pick = ReadoutDefInfo(
        id=uuid.uuid4(), protocol_id=P, name="Score", data_type="pick_list", unit=None,
        display_order=3,
    )  # fmt: skip
    a, b = uuid.uuid4(), uuid.uuid4()
    rows = [_num(a), _num(b, rd=pick.id, mean=2.0)]  # pick-list labels imported as numbers
    ds = _build("compounds", numeric=rows, defs=[*DEFS, pick])
    assert ds.row_ids == [str(a)]
    assert not any(c.provenance.readout_definition_id == pick.id for c in ds.columns)


def test_a_geomean_column_has_no_arithmetic_sd():
    mol = uuid.uuid4()
    geo = [replace(DEFS[1], aggregation="geometric_mean")]
    ds = _build("compounds", numeric=[_num(mol, rd=POT, geomean=10.0)], defs=geo)
    assert f"{POTK}:sd" not in _keys(ds)
    ds = _build("compounds", numeric=[_num(mol, rd=POT)], defs=[DEFS[1]])
    assert ds.values[f"{POTK}:sd"] == [7.07]


# --- a primary intercept other than 50 % --------------------------------------------

IC90 = {"kind": "ic", "level": 90.0, "basis": "relative_percent", "label": None}


def test_dose_response_labels_name_the_primary_intercept():
    defs = [replace(DEFS[2], primary_intercept=IC90)]  # curve_type stays "ic50"
    ds = _build("compounds", dr=[_dr(uuid.uuid4())], defs=defs)
    assert _col(ds, DRK).label == "Enzyme · IC90"
    assert _col(ds, f"{DRK}:p").label == "Enzyme · pIC90"


@pytest.mark.parametrize(
    ("primary", "fitted", "midpoint"),
    [
        ({"spec": IC90, "value": 9.0, "at_bound": False}, 9.0, 1.0),
        ({"spec": {**IC90, "level": 50.0}, "value": 1.5, "at_bound": False}, 1.5, 1.5),
        ({"spec": IC90, "value": None, "at_bound": True}, 2.0, 2.0),  # stored midpoint
        # A bound or n.d. primary stores the fitted midpoint itself as fitted_value.
        ({"spec": IC90, "value": 0.01, "at_bound": False, "qualifier": "<"}, 2.0, 2.0),
        ({"spec": IC90, "value": None, "at_bound": False, "qualifier": "nd"}, 2.0, 2.0),
        ({"spec": IC90, "value": 9.0, "at_bound": False, "qualifier": "="}, 9.0, 1.0),
        (None, 1.5, 1.5),  # fitted before intercepts were stored
    ],
)
def test_runs_level_carries_the_4pl_midpoint(primary, fitted, midpoint):
    run = _run()
    curve = _curve(
        run, uuid.uuid4(), uuid.uuid4(), fitted_value=fitted, hill_slope=1.0,
        intercept_values=[primary] if primary else None,
    )  # fmt: skip
    ds = _build("runs", curves=[curve], runs=[run])
    assert ds.values[f"{DRK}:midpoint"] == [pytest.approx(midpoint)]
    col = _col(ds, f"{DRK}:midpoint")
    assert (col.hidden, col.unit, col.provenance.stat) == (True, "µM", "midpoint")


@pytest.mark.parametrize("level", ["runs", "batches", "compounds"])
def test_the_plan_counts_the_rows_and_a_floor_of_the_columns(level):
    run_a, run_b = _run(12, conditions={"NADP": "+"}), _run(13, conditions={"NADP": "-"})
    mol, batch = uuid.uuid4(), uuid.uuid4()
    runs = [run_a, run_b]
    numeric = [
        _num(mol, batch_id=batch, run_id=run_a.id, conditions=run_a.conditions),
        _num(mol, rd=POT, batch_id=batch, run_id=run_b.id, conditions=run_b.conditions),
    ]
    dr = [_dr(mol, batch_id=batch, run_id=run_a.id, conditions=run_a.conditions)]
    if level == "runs":
        numeric = [replace(r, conditions=None) for r in numeric]
        dr = [replace(r, conditions=None) for r in dr]
    else:
        numeric = [replace(r, run_id=None) for r in numeric]
        dr = [replace(r, run_id=None) for r in dr]
    curves = [_curve(run_a, mol, batch)] if level == "runs" else []
    aggregates = ActivityAggregates(numeric_rows=numeric, dr_agg_rows=dr)

    plan = plan_aggregated(level, runs, DEFS, aggregates)
    ds = build_aggregated_dataset(level, runs, DEFS, aggregates, curves, {}, {})

    assert plan.rows == len(ds.row_ids)
    assert plan.columns <= len(ds.columns)
    owned = [c.provenance for c in ds.columns if c.provenance.readout_definition_id is not None]
    p_columns = [c for c in owned if c.stat is None and c.aggregation == "p"]
    assert plan.p == len(p_columns) > 0
    assert plan.values == len([c for c in owned if c.stat is None]) - len(p_columns)
