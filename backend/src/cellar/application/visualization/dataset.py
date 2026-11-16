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
from dataclasses import dataclass, field
from typing import Any, Literal

from cellar.application.visualization.dataset_reader import ReadoutDefInfo, RunInfo, WellValueRow
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
_IDENTITY: list[tuple[str, str, ColumnKind, bool]] = [
    ("compound", "Compound", "category", False),
    ("structure", "Structure", "structure", False),
    ("molecule_id", "Molecule id", "text", True),
    ("batch", "Batch", "category", False),
    ("run", "Run", "category", False),
    ("run_date", "Run date", "category", False),
    ("operator", "Operator", "user", False),
    ("run_status", "Run status", "category", False),
    ("plate", "Plate", "category", False),
    ("well", "Well", "text", False),
    ("well_row", "Row", "category", False),
    ("well_column", "Column", "number", False),
    ("well_order", "Well order", "number", False),
    ("well_type", "Well type", "category", False),
    ("dose", "Dose", "number", False),
    ("label", "Well label", "text", False),
]


def _run_labels(runs: list[RunInfo]) -> dict[uuid.UUID, str]:
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


def _finite(v: float | None) -> float | None:
    return v if v is not None and math.isfinite(v) else None


def _identity_values(
    row: WellValueRow, run: RunInfo | None, run_label: str | None
) -> dict[str, Any]:
    order = None
    if row.well_row is not None and row.well_column is not None:
        dims = plate_dimensions(row.plate_format, row.holder_rows, row.holder_columns)
        if dims is not None:
            order = well_order(row.well_row, row.well_column, dims[1])
    plate = None
    if row.plate_id is not None:
        plate = row.plate_barcode or f"Plate {row.plate_number}"
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
        "well": well,
        "well_row": row.well_row,
        "well_column": row.well_column,
        "well_order": order,
        "well_type": row.well_type,
        "dose": _finite(row.dose),
        "label": row.well_label,
    }


def build_wells_dataset(
    runs: list[RunInfo], defs: list[ReadoutDefInfo], rows: list[WellValueRow]
) -> Dataset:
    runs_by_id = {r.id: r for r in runs}
    run_labels = _run_labels(runs)
    defs_by_id = {d.id: d for d in defs}

    # Row identity follows the reader's order; values resolve latest-created-wins.
    index: dict[str, int] = {}
    identity: list[dict[str, Any]] = []
    for row in rows:
        key = _row_key(row)
        if key not in index:
            index[key] = len(identity)
            identity.append(
                _identity_values(row, runs_by_id.get(row.run_id), run_labels.get(row.run_id))
            )

    n = len(identity)
    cells: dict[str, list[Any]] = {}
    qualifiers: dict[str, list[Any]] = {}
    outliers: dict[str, list[Any]] = {}
    for row in sorted(rows, key=lambda r: r.created_at):
        rd = defs_by_id.get(row.readout_definition_id)
        if rd is None:
            continue
        layer = row.normalization_applied or RAW_LAYER
        vkey = f"rd:{rd.id}:{layer}"
        i = index[_row_key(row)]
        col = cells.setdefault(vkey, [None] * n)
        if rd.data_type in _NUMERIC_DATA_TYPES:
            col[i] = _finite(row.value_numeric)
        else:
            col[i] = (
                row.value_text
                if row.value_text is not None
                else (None if row.value_numeric is None else str(row.value_numeric))
            )
        if row.value_qualifier:
            qualifiers.setdefault(vkey, [None] * n)[i] = row.value_qualifier
        if row.is_outlier:
            outliers.setdefault(vkey, [None] * n)[i] = "outlier"

    columns: list[DatasetColumn] = [
        DatasetColumn(key=k, label=label, kind=kind, hidden=hidden)
        for k, label, kind, hidden in _IDENTITY
    ]
    values: dict[str, list[Any]] = {k: [ident[k] for ident in identity] for k, *_ in _IDENTITY}

    cond_names = sorted({name for r in runs for name in (r.conditions or {})})
    for name in cond_names:
        key = f"cond:{name}"
        columns.append(DatasetColumn(key=key, label=name, kind="category", group="Conditions"))
        values[key] = [None] * n
    for row in rows:
        run = runs_by_id.get(row.run_id)
        if run and run.conditions:
            i = index[_row_key(row)]
            for name, v in run.conditions.items():
                values[f"cond:{name}"][i] = None if v is None else str(v)

    def _layer_rank(vkey: str) -> tuple[int, int, str]:
        _, rd_id, layer = vkey.split(":", 2)
        rd = defs_by_id[uuid.UUID(rd_id)]
        return (rd.display_order, 0 if layer == RAW_LAYER else 1, rd.name + layer)

    for vkey in sorted(cells, key=_layer_rank):
        _, rd_id, layer = vkey.split(":", 2)
        rd = defs_by_id[uuid.UUID(rd_id)]
        unit = unit_for_normalization(None if layer == RAW_LAYER else layer, rd.unit)
        if layer == RAW_LAYER:
            label = f"{rd.name} ({unit})" if unit else rd.name
        else:
            label = f"{rd.name} · {_LAYER_LABELS.get(layer, layer.replace('_', ' '))}"
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
        if vkey in qualifiers:
            qkey = f"{vkey}:q"
            columns.append(
                DatasetColumn(
                    key=qkey,
                    label=f"{label} qualifier",
                    kind="category",
                    group=rd.name,
                    provenance=prov,
                )
            )
            values[qkey] = qualifiers[vkey]
        if vkey in outliers:
            okey = f"{vkey}:outlier"
            columns.append(
                DatasetColumn(
                    key=okey,
                    label=f"{label} outlier",
                    kind="category",
                    group=rd.name,
                    provenance=prov,
                )
            )
            values[okey] = outliers[vkey]

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
