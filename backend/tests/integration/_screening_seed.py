"""Raw-SQL seeding for screening read-model tests: protocols, runs, readouts, curves.

Each helper inserts one row and returns its id, so a test states exactly the
data its assertion depends on. No domain construction — these exercise SQL.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

USER = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")


async def org(s: AsyncSession, ws: uuid.UUID) -> uuid.UUID:
    oid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :name, 'internal', true, 1)"
        ),
        {"id": oid, "ws": ws, "name": f"Org-{oid.hex[:6]}"},
    )
    return oid


async def protocol(
    s: AsyncSession,
    ws: uuid.UUID,
    *,
    dose_unit: str = "uM",
    conditions: list[tuple[str, str, str | None]] = (),  # type: ignore[assignment]
) -> uuid.UUID:
    """``conditions``: (name, data_type, unit) condition definitions."""
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO protocols (id, workspace_id, name, name_base, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, :name, 'biochemical', 'active', false, :du, 'high', 1, 1, "
            ":user)"
        ),
        {"id": pid, "ws": ws, "name": f"Protocol-{pid.hex[:8]}", "du": dose_unit, "user": USER},
    )
    for name, data_type, unit in conditions:
        await s.execute(
            sa.text(
                "INSERT INTO condition_definitions (id, protocol_id, name, data_type, unit) "
                "VALUES (:id, :p, :name, :dt, :unit)"
            ),
            {"id": uuid.uuid4(), "p": pid, "name": name, "dt": data_type, "unit": unit},
        )
    return pid


# A minimal IC50 fit config; the domain requires one on dose-response readouts.
DR_CONFIG = {
    "curve_type": "ic50",
    "intercepts": [{"kind": "ic", "basis": "relative_percent", "label": None, "level": 50.0}],
    "y_readout_name": "Signal",
    "y_normalization": "percent_inhibition",
}


async def readout_def(
    s: AsyncSession,
    protocol_id: uuid.UUID,
    *,
    name: str = "Readout",
    data_type: str = "numeric",
    unit: str | None = None,
    aggregation: str = "mean",
) -> uuid.UUID:
    rid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO readout_definitions (id, protocol_id, name, data_type, unit, "
            "aggregation, display_order, is_calculated, dose_response_config) "
            "VALUES (:id, :p, :name, :dt, :unit, :agg, 0, false, cast(:cfg as jsonb))"
        ),
        {
            "id": rid,
            "p": protocol_id,
            "name": name,
            "dt": data_type,
            "unit": unit,
            "agg": aggregation,
            "cfg": json.dumps(DR_CONFIG) if data_type == "dose_response" else None,
        },
    )
    return rid


async def run(
    s: AsyncSession,
    ws: uuid.UUID,
    protocol_id: uuid.UUID,
    run_date: date,
    *,
    status: str = "draft",
    conditions: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    rid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO runs (id, workspace_id, protocol_id, run_date, operator, status, "
            "is_locked, version, conditions, created_at) "
            "VALUES (:id, :ws, :p, :d, :user, :status, false, 1, cast(:c as jsonb), "
            "coalesce(:created, now()))"
        ),
        {
            "id": rid,
            "ws": ws,
            "p": protocol_id,
            "d": run_date,
            "user": USER,
            "status": status,
            "c": json.dumps(conditions) if conditions is not None else None,
            "created": created_at,
        },
    )
    return rid


async def readout(
    s: AsyncSession,
    ws: uuid.UUID,
    run_id: uuid.UUID,
    rd_id: uuid.UUID,
    molecule_id: uuid.UUID,
    value: float,
    *,
    qualifier: str | None = None,
    wellless: bool = False,
    outlier: bool = False,
    normalization: str | None = None,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO readout_data (id, workspace_id, run_id, well_id, molecule_id, "
            "readout_definition_id, value_numeric, value_qualifier, is_outlier, "
            "normalization_applied) VALUES (:id, :ws, :run, :well, :m, :rd, :v, :q, :o, :n)"
        ),
        {
            "id": uuid.uuid4(),
            "ws": ws,
            "run": run_id,
            "well": None if wellless else uuid.uuid4(),
            "m": molecule_id,
            "rd": rd_id,
            "v": value,
            "q": qualifier,
            "o": outlier,
            "n": normalization,
        },
    )


async def curve(
    s: AsyncSession,
    ws: uuid.UUID,
    protocol_id: uuid.UUID,
    run_id: uuid.UUID,
    molecule_id: uuid.UUID,
    rd_id: uuid.UUID,
    *,
    fitted_value: float = 10.0,
    r_squared: float = 0.95,
    curve_class: str | None = "full",
    with_well: bool = True,
    intercept_values: list[dict[str, Any]] | None = None,
    max_dose: float = 1.0,
) -> uuid.UUID:
    """A fitted curve, plus (``with_well``) one per-well response reading on the
    same readout — real dose-response runs always carry their well data, and
    search matching finds tested compounds through it."""
    cid = uuid.uuid4()
    if with_well:
        await readout(s, ws, run_id, rd_id, molecule_id, 50.0)
    await s.execute(
        sa.text(
            "INSERT INTO dose_response_curves (id, workspace_id, molecule_id, batch_id, "
            "protocol_id, run_id, readout_definition_id, curve_type, fitted_value, hill_slope, "
            "top, bottom, r_squared, num_points, curve_class, raw_data, intercept_values) "
            "VALUES (:id, :ws, :m, :b, :p, :run, :rd, 'ic50', :fv, 1.0, 100, 0, :r2, 3, :cc, "
            "cast(:raw as jsonb), cast(:ivs as jsonb))"
        ),
        {
            "id": cid,
            "ws": ws,
            "m": molecule_id,
            "b": uuid.uuid4(),
            "p": protocol_id,
            "run": run_id,
            "rd": rd_id,
            "fv": fitted_value,
            "r2": r_squared,
            "cc": curve_class,
            "raw": json.dumps([{"concentration": max_dose, "response": 50.0}]),
            "ivs": json.dumps(intercept_values) if intercept_values is not None else None,
        },
    )
    return cid


def descriptors(molecular_weight: float) -> dict[str, Any]:
    """A full descriptor set (the domain requires all or none) with one chosen MW."""
    return {
        "molecular_formula": "C10H10",
        "molecular_weight": molecular_weight,
        "exact_mass": molecular_weight,
        "logp": 1.0,
        "tpsa": 20.0,
        "hbd": 1,
        "hba": 2,
        "rotatable_bonds": 3,
        "aromatic_rings": 1,
        "ring_count": 1,
        "heavy_atom_count": 10,
        "ro5_violations": 0,
    }


async def molecule(
    s: AsyncSession, ws: uuid.UUID, org_id: uuid.UUID, name: str, **columns: Any
) -> uuid.UUID:
    """A registered molecule row; ``columns`` sets descriptor columns (molecular_weight=…)."""
    mid = uuid.uuid4()
    extra = "".join(f", {k}" for k in columns)
    extra_vals = "".join(f", :{k}" for k in columns)
    await s.execute(
        sa.text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, molecule_type, "
            "smiles, cxsmiles, inchi, inchi_key, molfile, structure_status, registration_status, synthesis_status, lifecycle_stage, "
            f"originating_org_id, version{extra}) "  # noqa: S608 - column names from the test
            "VALUES (:id, :ws, :reg, :name, 'small_molecule', 'CCO', 'CCO', 'InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3', "
            ":ik, 'mol', 'disclosed', 'approved', "
            f"'virtual', 'active', :org, 1{extra_vals})"
        ),
        {
            "id": mid,
            "ws": ws,
            "reg": f"CV-{mid.hex[:6]}",
            "name": name,
            "org": org_id,
            "ik": "LFQSCWFLJHTTHZ-" + "".join(chr(65 + int(c, 16)) for c in mid.hex[:10]) + "-N",
            **columns,
        },
    )
    return mid
