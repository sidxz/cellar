"""Columnar datasets for the visualization workbench.

A dataset is one flat table: ``row_ids`` plus one value array per column, all
the same length. ``build_wells_dataset`` turns readout rows into one row per
measured well (or per well-less (compound, batch) key of a summary import),
with one column per readout x normalization layer.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from cellar.application.visualization.dataset_reader import (
    CompoundInfo,
    ReadoutDefInfo,
    RunInfo,
    WellValueRow,
)
from cellar.domain.screening_assay.enums import unit_for_normalization
from cellar.domain.screening_assay.plate_geometry import plate_dimensions, well_order

ColumnKind = Literal["number", "category", "text", "structure", "user"]

RAW_LAYER = "raw"
_NUMERIC_DATA_TYPES = {"numeric", "dose_response"}
_LAYER_LABELS = {
    "percent_inhibition": "% Inhibition",
    "percent_activation": "% Activation",
    "percent_control": "% Control",
    "z_score": "Z-Score",
}


@dataclass(frozen=True)
class ColumnProvenance:
    protocol_id: uuid.UUID | None = None
    readout_definition_id: uuid.UUID | None = None
    layer: str | None = None
    condition_set: str | None = None  # the set's label, when the dataset has several
    # "mean" / "median" / "geomean" / "min" / "max" ("replicate_…" at Runs), "fit", "p"
    aggregation: str | None = None
    stat: str | None = None  # what a sibling column holds ("qualifier", "n", "sd" …)


@dataclass(frozen=True)
class DatasetColumn:
    key: str
    label: str
    kind: ColumnKind
    unit: str | None = None
    group: str | None = None
    provenance: ColumnProvenance = field(default_factory=ColumnProvenance)
    hidden: bool = False


@dataclass(frozen=True)
class Dataset:
    revision: str
    level: str
    row_ids: list[str]
    columns: list[DatasetColumn]
    values: dict[str, list[Any]]


# Identity columns, in display order: (key, label, kind, hidden).
IDENTITY_COLUMNS: list[tuple[str, str, ColumnKind, bool]] = [
    ("compound", "Compound", "category", False),
    ("structure", "Structure", "structure", False),
    ("molecule_id", "Molecule id", "text", True),
    ("batch", "Batch", "category", False),
    ("run", "Run", "category", False),
    ("run_date", "Run date", "category", False),
    ("operator", "Operator", "user", False),
    ("run_status", "Run status", "category", False),
    ("plate", "Plate", "category", False),
    ("plate_id", "Plate id", "text", True),
    ("well", "Well", "text", False),
    ("well_row", "Row", "category", False),
    ("well_column", "Column", "number", False),
    ("well_order", "Well order", "number", False),
    ("well_type", "Well type", "category", False),
    ("dose", "Dose", "number", False),
    ("label", "Well label", "text", False),
]


# Computed descriptors: (key, label, unit).
_DESCRIPTORS: list[tuple[str, str, str | None]] = [
    ("molecular_weight", "MW", "Da"),
    ("logp", "logP", None),
    ("tpsa", "TPSA", "Å²"),
    ("hbd", "HBD", None),
    ("hba", "HBA", None),
    ("rotatable_bonds", "Rotatable bonds", None),
    ("aromatic_rings", "Aromatic rings", None),
]


def descriptor_columns(
    molecule_ids: list[str | None], molecules: dict[uuid.UUID, CompoundInfo]
) -> tuple[list[DatasetColumn], dict[str, list[Any]]]:
    """Descriptor columns for rows whose ``molecule_id`` values are given; a
    descriptor no row has is left out."""
    by_id = {str(k): v for k, v in molecules.items()}
    infos = [by_id.get(m) if m else None for m in molecule_ids]
    columns: list[DatasetColumn] = []
    values: dict[str, list[Any]] = {}
    for key, label, unit in _DESCRIPTORS:
        col = [None if info is None else getattr(info, key) for info in infos]
        if any(v is not None for v in col):
            columns.append(
                DatasetColumn(key=key, label=label, kind="number", unit=unit, group="Descriptors")
            )
            values[key] = col
    return columns, values


def condition_columns(
    runs: list[RunInfo], row_runs: list[uuid.UUID | None]
) -> tuple[list[DatasetColumn], dict[str, list[Any]]]:
    """One ``cond:<name>`` category column per condition any run sets, valued from
    each row's run."""
    runs_by_id = {r.id: r for r in runs}
    names = sorted({name for r in runs for name in (r.conditions or {})})
    columns = [
        DatasetColumn(key=f"cond:{name}", label=name, kind="category", group="Conditions")
        for name in names
    ]
    values: dict[str, list[Any]] = {f"cond:{name}": [None] * len(row_runs) for name in names}
    for i, run_id in enumerate(row_runs):
        run = runs_by_id.get(run_id) if run_id is not None else None
        for name, v in (run.conditions or {}).items() if run else ():
            values[f"cond:{name}"][i] = None if v is None else str(v)
    return columns, values


def readout_label(
    rd: ReadoutDefInfo, layer: str, unit: str | None, condition_set: str | None = None
) -> str:
    """Readout → condition set → layer: "Signal (AU)", "Signal · NADP: + · % Inhibition"."""
    cs = f" · {condition_set}" if condition_set else ""
    if layer == RAW_LAYER:
        named = not unit or rd.name.lower().endswith(unit.lower())  # "raw AU" + "AU"
        return (rd.name if named else f"{rd.name} ({unit})") + cs
    return f"{rd.name}{cs} · {_LAYER_LABELS.get(layer, layer.replace('_', ' '))}"


def run_labels(runs: list[RunInfo]) -> dict[uuid.UUID, str]:
    by_date: dict[Any, list[RunInfo]] = defaultdict(list)
    for r in runs:
        by_date[r.run_date].append(r)
    labels: dict[uuid.UUID, str] = {}
    for day, same in by_date.items():
        same.sort(key=lambda r: r.created_at)
        for i, r in enumerate(same, start=1):
            labels[r.id] = day.isoformat() if len(same) == 1 else f"{day.isoformat()} #{i}"
    return labels


def _row_key(row: WellValueRow) -> str:
    if row.well_id is not None:
        return f"{row.run_id}:{row.well_id}"
    batch = row.batch_id if row.batch_id is not None else "-"
    return f"{row.run_id}:m:{row.molecule_id}:{batch}"


def finite(v: float | None) -> float | None:
    return v if v is not None and math.isfinite(v) else None


def _identity_values(
    row: WellValueRow, run: RunInfo | None, run_label: str | None, multi_run: bool
) -> dict[str, Any]:
    order = None
    if row.well_row is not None and row.well_column is not None:
        dims = plate_dimensions(row.plate_format, row.holder_rows, row.holder_columns)
        if dims is not None:
            order = well_order(row.well_row, row.well_column, dims[1])
    plate = None
    if row.plate_id is not None:
        plate = row.plate_barcode or f"Plate {row.plate_number}"
        if multi_run:  # every run has a "Plate 1"
            plate = f"{run_label} · {plate}"
    well = None
    if row.well_row is not None and row.well_column is not None:
        well = f"{row.well_row}{row.well_column:02d}"
    return {
        "compound": row.registration_number,
        "structure": row.smiles,
        "molecule_id": str(row.molecule_id) if row.molecule_id else None,
        "batch": row.batch_number,
        "run": run_label,
        "run_date": run.run_date.isoformat() if run else None,
        "operator": str(run.operator_id) if run else None,
        "run_status": run.status if run else None,
        "plate": plate,
        "plate_id": str(row.plate_id) if row.plate_id else None,
        "well": well,
        "well_row": row.well_row,
        "well_column": row.well_column,
        "well_order": order,
        "well_type": row.well_type,
        "dose": finite(row.dose),
        "label": row.well_label,
    }


def build_wells_dataset(
    runs: list[RunInfo],
    defs: list[ReadoutDefInfo],
    rows: list[WellValueRow],
    molecules: dict[uuid.UUID, CompoundInfo] | None = None,
) -> Dataset:
    runs_by_id = {r.id: r for r in runs}
    labels_of_runs = run_labels(runs)
    multi_run = len(runs) > 1
    defs_by_id = {d.id: d for d in defs}

    # Row identity follows the reader's order; values resolve latest-created-wins.
    index: dict[str, int] = {}
    identity: list[dict[str, Any]] = []
    row_runs: list[uuid.UUID | None] = []
    for row in rows:
        key = _row_key(row)
        if key not in index:
            index[key] = len(identity)
            row_runs.append(row.run_id)
            identity.append(
                _identity_values(
                    row, runs_by_id.get(row.run_id), labels_of_runs.get(row.run_id), multi_run
                )
            )

    n = len(identity)
    # One list per column, allocated on first use (a setdefault default would allocate per row).
    cells: defaultdict[str, list[Any]] = defaultdict(lambda: [None] * n)
    qualifiers: defaultdict[str, list[Any]] = defaultdict(lambda: [None] * n)
    outliers: defaultdict[str, list[Any]] = defaultdict(lambda: [None] * n)
    for row in sorted(rows, key=lambda r: r.created_at):
        rd = defs_by_id.get(row.readout_definition_id)
        if rd is None:
            continue
        layer = row.normalization_applied or RAW_LAYER
        vkey = f"rd:{rd.id}:{layer}"
        i = index[_row_key(row)]
        col = cells[vkey]
        if rd.data_type in _NUMERIC_DATA_TYPES:
            value: Any = finite(row.value_numeric)
        else:
            value = (
                row.value_text
                if row.value_text is not None
                else (None if row.value_numeric is None else str(row.value_numeric))
            )
        # The latest non-null record wins (as on the Heat Map), and its flags come with it.
        if value is None and col[i] is not None:
            continue
        col[i] = value
        qualifiers[vkey][i] = row.value_qualifier or None
        outliers[vkey][i] = "outlier" if row.is_outlier else None

    columns: list[DatasetColumn] = [
        DatasetColumn(key=k, label=label, kind=kind, hidden=hidden)
        for k, label, kind, hidden in IDENTITY_COLUMNS
    ]
    values: dict[str, list[Any]] = {
        k: [ident[k] for ident in identity] for k, *_ in IDENTITY_COLUMNS
    }

    cond_cols, cond_values = condition_columns(runs, row_runs)
    columns += cond_cols
    values |= cond_values

    def _layer_rank(vkey: str) -> tuple[int, int, str]:
        _, rd_id, layer = vkey.split(":", 2)
        rd = defs_by_id[uuid.UUID(rd_id)]
        return (rd.display_order, 0 if layer == RAW_LAYER else 1, rd.name + layer)

    for vkey in sorted(cells, key=_layer_rank):
        _, rd_id, layer = vkey.split(":", 2)
        rd = defs_by_id[uuid.UUID(rd_id)]
        unit = unit_for_normalization(None if layer == RAW_LAYER else layer, rd.unit)
        label = readout_label(rd, layer, unit)
        prov = ColumnProvenance(
            protocol_id=rd.protocol_id, readout_definition_id=rd.id, layer=layer
        )
        kind: ColumnKind = "number" if rd.data_type in _NUMERIC_DATA_TYPES else "category"
        columns.append(
            DatasetColumn(
                key=vkey, label=label, kind=kind, unit=unit, group=rd.name, provenance=prov
            )
        )
        values[vkey] = cells[vkey]
        if any(v is not None for v in qualifiers[vkey]):
            qkey = f"{vkey}:q"
            columns.append(
                DatasetColumn(
                    key=qkey,
                    label=f"{label} qualifier",
                    kind="category",
                    group=rd.name,
                    provenance=replace(prov, stat="qualifier"),
                )
            )
            values[qkey] = qualifiers[vkey]
        if any(v is not None for v in outliers[vkey]):
            okey = f"{vkey}:outlier"
            columns.append(
                DatasetColumn(
                    key=okey,
                    label=f"{label} outlier",
                    kind="category",
                    group=rd.name,
                    provenance=replace(prov, stat="outlier"),
                )
            )
            values[okey] = outliers[vkey]

    if molecules is not None:
        desc_cols, desc_values = descriptor_columns(values["molecule_id"], molecules)
        columns += desc_cols
        values |= desc_values

    latest = max((r.created_at for r in rows), default=None)
    digest = hashlib.sha1(
        (
            "|".join(sorted(str(r.id) for r in runs)) + f"|{latest.isoformat() if latest else ''}"
        ).encode(),
        usedforsecurity=False,
    ).hexdigest()
    return Dataset(
        revision=digest, level="wells", row_ids=list(index), columns=columns, values=values
    )
