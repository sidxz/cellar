"""Aggregated datasets for the workbench: one row per (compound, batch, run) at Runs,
per (compound, batch) at Batches and per compound at Compounds.

The numbers come from the shared aggregation (``ProtocolActivityReader.get_aggregates``,
the one behind the Activity tab) and, at Runs, from each run's fitted curve. This module
only turns them into values (``combine_replicates`` for censored values, ``p_scale`` for
pIC50) and pivots them into columns. Condition sets are never pooled: when the rows
carry more than one set, each readout gets one column per set.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from cellar.application.screening import _condense_raw_data
from cellar.application.screening.compound_curves_reader import CurveRow
from cellar.application.screening.protocol_activity_reader import (
    ActivityAggregates,
    DRAggRow,
    NumericReadoutRow,
)
from cellar.application.screening.run_aggregation import combine_replicates
from cellar.application.visualization.dataset import (
    IDENTITY_COLUMNS,
    RAW_LAYER,
    ColumnKind,
    ColumnProvenance,
    Dataset,
    DatasetColumn,
    condition_columns,
    descriptor_columns,
    finite,
    readout_label,
    run_labels,
)
from cellar.application.visualization.dataset_reader import CompoundInfo, ReadoutDefInfo, RunInfo
from cellar.domain.screening_assay.enums import CurveClass, unit_for_normalization
from cellar.domain.screening_assay.readout_best import best_direction, best_of_range
from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.domain.shared.units import canonical_unit, is_concentration_unit, p_scale

AggLevel = Literal["runs", "batches", "compounds"]

_FLIP = {">": "<", ">=": "<=", "<": ">", "<=": ">="}

# Sibling columns after a value column: (stat = key suffix, label, kind, in the value's
# unit, hidden). CI and points stay hidden: no CI columns in a grid.
_Sibling = tuple[str, str, ColumnKind, bool, bool]
_NUMERIC_SIBLINGS: list[_Sibling] = [
    ("n", "n", "number", False, False),
    ("sd", "SD", "number", True, False),
    ("best", "best", "number", True, False),
    ("n_censored", "n censored", "number", False, False),
    ("n_nonpositive", "n ≤ 0 not in geomean", "number", False, False),
]
_DR_SIBLINGS: list[_Sibling] = [
    ("best", "best", "number", True, False),
    ("n_tested", "n tested", "number", False, False),
    ("n_inactive", "n inactive", "number", False, False),
    ("n_used", "n used", "number", False, False),
]
_FIT_SIBLINGS: list[_Sibling] = [
    ("top", "top", "number", False, False),
    ("bottom", "bottom", "number", False, False),
    ("hill_slope", "Hill slope", "number", False, False),
    ("r_squared", "R²", "number", False, False),
    ("curve_class", "curve class", "category", False, False),
    ("min_dose", "min dose", "number", True, False),
    ("max_dose", "max dose", "number", True, False),
    ("ci_low", "CI low", "number", True, True),
    ("ci_high", "CI high", "number", True, True),
    ("points", "points", "text", False, True),
]
_IDENTITY_BY_KEY = {c[0]: c for c in [*IDENTITY_COLUMNS, ("batch_id", "Batch id", "text", True)]}
# A numeric readout's replicate aggregation (combine_replicates' name) → provenance name.
# "none" and anything else read as the mean.
_AGGREGATION_NAMES = {
    "geometric_mean": "geomean",
    "median": "median",
    "min": "min",
    "max": "max",
    "mean": "mean",
}
# Counted on every row; their columns show only when some count is > 0.
_COUNTS = ("n_censored", "n_nonpositive")


@dataclass
class _ValueColumn:
    rd: ReadoutDefInfo
    layer: str | None  # None for a dose-response value
    condition_set: str  # canonical JSON of the set
    unit: str | None
    molar: bool = field(init=False)  # gets a p column
    aggregation: str = field(init=False)  # a numeric value's, as combine_replicates names it

    def __post_init__(self) -> None:
        self.molar = p_scale(1.0, self.unit) is not None
        agg = self.rd.aggregation or "mean"
        if agg == "geometric_mean" and not is_concentration_unit(self.unit):
            agg = "mean"  # combine_replicates' rule: a geomean needs a concentration
        self.aggregation = agg if agg in _AGGREGATION_NAMES else "mean"


def _qualifier(q: ValueQualifier, r: NumericReadoutRow) -> str | None:
    """The cell's qualifier: a censored bound keeps its inclusivity (">=10" stays ">=")."""
    if q == ValueQualifier.GT:
        return ">=" if r.gt_inclusive else ">"
    if q == ValueQualifier.LT:
        return "<=" if r.lt_inclusive else "<"
    return None


def _condition_set(conditions: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """(canonical JSON, set): None values dropped, so {} and {"NADP": None} are one set."""
    if not conditions:
        return "{}", {}
    kept = {k: v for k, v in conditions.items() if v is not None}
    return json.dumps(kept, sort_keys=True, default=str), kept


def _set_labels(sets: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Each set named by the keys whose value differs across the sets present."""
    names = {k for s in sets.values() for k in s}
    varying = sorted(
        k
        for k in names
        if len({(k in s, json.dumps(s.get(k), default=str)) for s in sets.values()}) > 1
    )
    return {
        cs: ", ".join(f"{k}: {s[k]}" for k in varying if k in s) or "no conditions"
        for cs, s in sets.items()
    }


def _dr_labels(rd: ReadoutDefInfo, cs: str) -> tuple[str, str]:
    """("Enzyme · IC50", "Enzyme · pIC50"); just "IC50" when the name already says it."""
    ct = (rd.curve_type or "").upper()
    value = rd.name if not ct or ct.lower() in rd.name.lower() else f"{rd.name} · {ct}"
    p = f"{rd.name} · p{ct}" if ct else f"p{rd.name}"
    suffix = f" · {cs}" if cs else ""
    return value + suffix, p + suffix


def build_aggregated_dataset(
    level: AggLevel,
    runs: list[RunInfo],
    defs: list[ReadoutDefInfo],
    aggregates: ActivityAggregates,
    curves: list[CurveRow],
    molecules: dict[uuid.UUID, CompoundInfo],
    batches: dict[uuid.UUID, str],
) -> Dataset:
    defs_by_id: dict[uuid.UUID | None, ReadoutDefInfo] = {d.id: d for d in defs}
    runs_by_id = {r.id: r for r in runs}
    records: list[NumericReadoutRow | DRAggRow | CurveRow] = [
        r
        for r in (
            *aggregates.numeric_rows,
            *aggregates.dr_agg_rows,
            *(curves if level == "runs" else ()),
        )
        if r.readout_definition_id in defs_by_id
    ]

    # Pass 1: row keys, and condition sets (Runs has the run's conditions as columns).
    idents: dict[str, tuple[uuid.UUID, uuid.UUID | None, uuid.UUID | None]] = {}
    keyed: list[tuple[str, str]] = []
    sets: dict[str, dict[str, Any]] = {}
    for r in records:
        batch = str(r.batch_id) if r.batch_id is not None else "-"
        ident: tuple[uuid.UUID, uuid.UUID | None, uuid.UUID | None]
        if level == "compounds":
            key, ident = str(r.molecule_id), (r.molecule_id, None, None)
        elif level == "batches":
            key, ident = f"{r.molecule_id}:{batch}", (r.molecule_id, r.batch_id, None)
        else:
            key, ident = (
                f"{r.run_id}:{r.molecule_id}:{batch}",
                (r.molecule_id, r.batch_id, r.run_id),
            )
        idents.setdefault(key, ident)
        cs = "{}"
        if level != "runs" and not isinstance(r, CurveRow):
            cs, canonical = _condition_set(r.conditions)
            sets.setdefault(cs, canonical)
        keyed.append((key, cs))

    def _order(key: str) -> tuple[Any, ...]:
        mol, batch, run_id = idents[key]
        info = molecules.get(mol)
        reg = info.registration_number if info else None
        number = batches.get(batch) if batch is not None else None
        run = runs_by_id.get(run_id) if run_id is not None else None
        return (
            reg is None,
            reg or "",
            number is None,
            number or "",
            run is None,
            (run.run_date, run.created_at) if run else (),
            key,
        )

    row_ids = sorted(idents, key=_order)
    index = {k: i for i, k in enumerate(row_ids)}
    n = len(row_ids)

    # Several condition sets: one column per set, keyed and labeled by it.
    labels = _set_labels(sets) if len(sets) > 1 else {}
    suffixes = {
        cs: "@" + hashlib.sha1(cs.encode(), usedforsecurity=False).hexdigest()[:8] for cs in labels
    }

    # Pass 2: values. One list per column, allocated on first use.
    cells: defaultdict[str, list[Any]] = defaultdict(lambda: [None] * n)
    specs: dict[str, _ValueColumn] = {}

    def put(vk: str, spec: _ValueColumn, i: int, value: float | None, q: str | None) -> None:
        cells[vk][i] = value
        if q:
            cells[f"{vk}:q"][i] = q
        if value is not None and spec.molar:
            cells[f"{vk}:p"][i] = p_scale(value, spec.unit)
            if q:
                cells[f"{vk}:p:q"][i] = _FLIP[q]

    for r, (key, cs) in zip(records, keyed, strict=True):
        i = index[key]
        rd = defs_by_id[r.readout_definition_id]
        if isinstance(r, NumericReadoutRow):
            layer = r.layer or RAW_LAYER
            vk = f"rd:{rd.id}:{layer}{suffixes.get(cs, '')}"
            spec = specs.get(vk) or specs.setdefault(
                vk, _ValueColumn(rd, layer, cs, unit_for_normalization(r.layer, rd.unit))
            )
            value, q = combine_replicates(r.stats(), spec.aggregation, unit=spec.unit)
            put(vk, spec, i, finite(value), _qualifier(q, r))
            if spec.aggregation == "geometric_mean":
                cells[f"{vk}:n_nonpositive"][i] = r.nonpositive_count
            cells[f"{vk}:n"][i] = r.n
            cells[f"{vk}:sd"][i] = finite(r.sd)
            direction = best_direction(rd.data_type, rd.melt_measure)
            cells[f"{vk}:best"][i] = finite(best_of_range(r.low, r.best, direction))
            cells[f"{vk}:n_censored"][i] = r.gt_count + r.lt_count
            continue
        if isinstance(r, DRAggRow) and level == "runs":
            continue  # the run's own curve carries its values
        vk = f"dr:{rd.id}{suffixes.get(cs, '')}"
        spec = specs.get(vk) or specs.setdefault(
            vk, _ValueColumn(rd, None, cs, canonical_unit(rd.dose_unit))
        )
        if isinstance(r, DRAggRow):
            put(vk, spec, i, finite(r.geo_mean), None)
            cells[f"{vk}:best"][i] = finite(r.best)
            cells[f"{vk}:n_tested"][i] = r.n_tested
            cells[f"{vk}:n_inactive"][i] = r.n_inactive
            cells[f"{vk}:n_used"][i] = r.n_used
            continue
        inactive = r.curve_class == CurveClass.INACTIVE.value
        put(vk, spec, i, None if inactive else finite(r.fitted_value), None)
        points = _condense_raw_data(r.raw_data) if isinstance(r.raw_data, list) else []
        doses = [p["x"] for p in points]
        for stat, v in (
            ("top", r.top),
            ("bottom", r.bottom),
            ("hill_slope", r.hill_slope),
            ("r_squared", r.r_squared),
            ("min_dose", min(doses, default=None)),
            ("max_dose", max(doses, default=None)),
            ("ci_low", r.confidence_interval_low),
            ("ci_high", r.confidence_interval_high),
        ):
            cells[f"{vk}:{stat}"][i] = finite(v)
        cells[f"{vk}:curve_class"][i] = r.curve_class
        cells[f"{vk}:points"][i] = points or None

    # Identity columns.
    identity_keys = ["compound", "structure", "molecule_id"]
    if level != "compounds":
        identity_keys += ["batch", "batch_id"]
    if level == "runs":
        identity_keys += ["run", "run_date", "operator", "run_status"]
    columns = [
        DatasetColumn(key=k, label=label, kind=kind, hidden=hidden)
        for k, label, kind, hidden in (_IDENTITY_BY_KEY[k] for k in identity_keys)
    ]
    mol_ids = [idents[k][0] for k in row_ids]
    infos = [molecules.get(m) for m in mol_ids]
    values: dict[str, list[Any]] = {
        "compound": [i.registration_number if i else None for i in infos],
        "structure": [i.smiles if i else None for i in infos],
        "molecule_id": [str(m) for m in mol_ids],
    }
    if level != "compounds":
        batch_ids = [idents[k][1] for k in row_ids]
        values["batch"] = [batches.get(b) if b is not None else None for b in batch_ids]
        values["batch_id"] = [str(b) if b is not None else None for b in batch_ids]
    if level == "runs":
        row_runs = [idents[k][2] for k in row_ids]
        names = run_labels(runs)
        row_run_infos = [runs_by_id.get(r) if r is not None else None for r in row_runs]
        values["run"] = [names.get(r) if r is not None else None for r in row_runs]
        values["run_date"] = [r.run_date.isoformat() if r else None for r in row_run_infos]
        values["operator"] = [str(r.operator_id) if r else None for r in row_run_infos]
        values["run_status"] = [r.status if r else None for r in row_run_infos]
        cond_cols, cond_values = condition_columns(runs, row_runs)
        columns += cond_cols
        values |= cond_values

    # Value columns (and p columns of molar ones), each followed by its non-empty siblings.
    def _rank(vk: str) -> tuple[Any, ...]:
        s = specs[vk]
        return (
            s.rd.display_order,
            s.rd.name,
            str(s.rd.id),
            s.layer not in (None, RAW_LAYER),
            s.layer or "",
            labels.get(s.condition_set, ""),
        )

    def emit(
        key: str,
        label: str,
        kind: ColumnKind,
        unit: str | None,
        prov: ColumnProvenance,
        hidden: bool = False,
        *,
        always: bool = False,
    ) -> None:
        col = cells.get(key) or ([None] * n if always else None)
        if col is None or not (always or any(v is not None for v in col)):
            return
        if prov.stat in _COUNTS and not any(col):
            return
        columns.append(
            DatasetColumn(
                key=key,
                label=label,
                kind=kind,
                unit=unit,
                group=defs_by_id[prov.readout_definition_id].name,
                provenance=prov,
                hidden=hidden,
            )
        )
        values[key] = col

    for vk in sorted(specs, key=_rank):
        s = specs[vk]
        rd = s.rd
        cs_label = labels.get(s.condition_set)
        if s.layer is not None:
            label = readout_label(rd, s.layer, s.unit, cs_label)
            p_label = "p" + readout_label(rd, s.layer, None, cs_label)
            named = _AGGREGATION_NAMES[s.aggregation]
            aggregation = f"replicate_{named}" if level == "runs" else named
            siblings = _NUMERIC_SIBLINGS
        else:
            label, p_label = _dr_labels(rd, cs_label or "")
            aggregation = "fit" if level == "runs" else "geomean"
            siblings = _FIT_SIBLINGS if level == "runs" else _DR_SIBLINGS
        prov = ColumnProvenance(
            protocol_id=rd.protocol_id,
            readout_definition_id=rd.id,
            layer=s.layer,
            condition_set=cs_label,
            aggregation=aggregation,
        )
        p_prov = replace(prov, aggregation="p")
        emit(vk, label, "number", s.unit, prov, always=True)
        emit(f"{vk}:q", f"{label} qualifier", "category", None, replace(prov, stat="qualifier"))
        if s.molar:
            emit(f"{vk}:p", p_label, "number", None, p_prov, always=True)
        emit(
            f"{vk}:p:q",
            f"{p_label} qualifier",
            "category",
            None,
            replace(p_prov, stat="qualifier"),
        )
        for stat, sib_label, kind, in_unit, hidden in siblings:
            unit = s.unit if in_unit else None
            emit(
                f"{vk}:{stat}",
                f"{label} {sib_label}",
                kind,
                unit,
                replace(prov, stat=stat),
                hidden,
            )

    desc_cols, desc_values = descriptor_columns(values["molecule_id"], molecules)
    columns += desc_cols
    values |= desc_values

    digest = hashlib.sha1(
        "|".join([level, ",".join(sorted(str(r.id) for r in runs)), ",".join(row_ids)]).encode(),
        usedforsecurity=False,
    ).hexdigest()
    return Dataset(revision=digest, level=level, row_ids=row_ids, columns=columns, values=values)
