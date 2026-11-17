"""Compounds datasets of several protocols joined into one, for selectivity work.

The first protocol owns the rows: their order, identity and descriptor columns. Every
other protocol's columns are mapped onto those rows by compound (blank where it was
not tested there), and a ``tested:<protocol id>`` column per added protocol tells
"not tested" apart from "tested, no value". For every pair of p columns (first
protocol × added protocol) a ``sel:`` column holds the difference in log units.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

from cellar.application.visualization.dataset import (
    ColumnProvenance,
    Dataset,
    DatasetColumn,
    DatasetProtocol,
)


def delta_qualifier(qa: str | None, qb: str | None) -> tuple[bool, str | None]:
    """(ok, qualifier) of a - b from the qualifiers of a and b.

    A censored a pushes the difference its own way, a censored b the other way; pushes
    in both directions bound nothing (not ok). The bound is inclusive only when every
    censored side is.
    """
    up = down = strict = False
    for q, sign in ((qa, 1), (qb, -1)):
        if not q or q[0] not in "<>":
            continue
        if (q[0] == ">") == (sign == 1):
            up = True
        else:
            down = True
        strict = strict or not q.endswith("=")
    if up and down:
        return False, None
    if not (up or down):
        return True, None
    return True, (">" if up else "<") + ("" if strict else "=")


def _owned(col: DatasetColumn) -> bool:
    return col.provenance.readout_definition_id is not None


def _is_p(col: DatasetColumn) -> bool:
    return _owned(col) and col.provenance.aggregation == "p" and col.provenance.stat is None


def _prefixed(col: DatasetColumn, proto: DatasetProtocol) -> DatasetColumn:
    return replace(
        col,
        label=f"{proto.name} · {col.label}",
        group=proto.name,
        provenance=replace(col.provenance, protocol_id=proto.id),
    )


def join_protocol_datasets(parts: list[tuple[DatasetProtocol, Dataset]]) -> Dataset:
    (first_proto, first), *added = parts
    protocols = [proto for proto, _ in parts]
    if not added:
        return replace(first, protocols=protocols)

    columns = [_prefixed(c, first_proto) if _owned(c) else c for c in first.columns]
    values = dict(first.values)
    first_ps = [c for c in columns if _is_p(c)]
    selectivity: list[DatasetColumn] = []
    for proto, part in added:
        at = {row_id: j for j, row_id in enumerate(part.row_ids)}
        where = [at.get(row_id) for row_id in first.row_ids]
        tested = DatasetColumn(
            key=f"tested:{proto.id}",
            label=f"Tested in {proto.name}",
            kind="category",
            group=proto.name,
            provenance=ColumnProvenance(protocol_id=proto.id),
        )
        columns.append(tested)
        values[tested.key] = ["Not tested" if j is None else "Tested" for j in where]
        part_ps: list[DatasetColumn] = []
        for col in filter(_owned, part.columns):
            src = part.values[col.key]
            mapped = [None if j is None else src[j] for j in where]
            if col.provenance.stat is not None and all(v is None for v in mapped):
                continue  # a sibling only shows when some row has a value
            col = _prefixed(col, proto)
            columns.append(col)
            values[col.key] = mapped
            if _is_p(col):
                part_ps.append(col)
        for b in part_ps:  # after the part's qualifier siblings are mapped
            selectivity += _selectivity(first_ps, b, values)

    columns += selectivity
    digest = hashlib.sha1(
        "|".join(part.revision for _, part in parts).encode(), usedforsecurity=False
    ).hexdigest()
    return replace(first, revision=digest, columns=columns, values=values, protocols=protocols)


def _selectivity(
    first_ps: list[DatasetColumn], b: DatasetColumn, values: dict[str, list[Any]]
) -> list[DatasetColumn]:
    """Δ = a - b for each first-protocol p column a (null unless both are present and
    bounded), each with its qualifier sibling when some Δ is censored. Writes the
    values into ``values``."""
    out: list[DatasetColumn] = []
    none: list[Any] = [None] * len(values[b.key])
    qb = values.get(f"{b.key}:q", none)
    for a in first_ps:
        qa = values.get(f"{a.key}:q", none)
        deltas: list[Any] = []
        quals: list[Any] = []
        for va, vb, q1, q2 in zip(values[a.key], values[b.key], qa, qb, strict=True):
            ok, q = delta_qualifier(q1, q2)
            present = ok and va is not None and vb is not None
            deltas.append(va - vb if present else None)
            quals.append(q if present else None)
        col = DatasetColumn(
            key=f"sel:{a.key}|{b.key}",
            label=f"Δ ({a.label}) − ({b.label})",  # noqa: RUF001 -- typographic minus
            kind="number",
            unit="log units",
            group="Selectivity",
            provenance=ColumnProvenance(aggregation="selectivity"),
        )
        out.append(col)
        values[col.key] = deltas
        if any(quals):
            q_col = DatasetColumn(
                key=f"{col.key}:q",
                label=f"{col.label} qualifier",
                kind="category",
                group="Selectivity",
                provenance=ColumnProvenance(aggregation="selectivity", stat="qualifier"),
            )
            out.append(q_col)
            values[q_col.key] = quals
    return out
