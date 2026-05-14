"""GetProtocolActivitySummary query — multi-readout compound-centric results.

Returns ALL aggregatable readouts per compound in a single response,
with scientifically correct aggregation:
  - Numeric readouts: arithmetic mean + max (higher-is-better)
  - Dose-response readouts: geometric mean + min fitted_value (lower-is-better),
    plus best curve params (hill_slope, top, bottom, r_squared)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext
from cellar.application.screening import _condense_raw_data
from cellar.application.screening.protocol_activity_reader import (
    ProtocolActivityReader,
)
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError, NotFoundError

# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

VALID_STATUSES = ("completed", "approved")
_AGGREGATABLE_DATA_TYPES = {"numeric", "dose_response"}


def _hydrate_intercept_payloads(
    raw: list[dict] | None,
) -> list["InterceptValuePayload"]:
    """Hydrate JSONB-serialized intercept_values into payload dataclasses.

    The persistence layer stores intercept_values as a JSONB array of
    ``{spec: {kind, level, basis, label}, value, ci_low, ci_high, at_bound}``
    (see ``dose_response_curve_repository._serialize_intercept_values``).
    """
    if not raw:
        return []
    out: list[InterceptValuePayload] = []
    for d in raw:
        if not isinstance(d, dict):
            continue
        spec = d.get("spec") or {}
        out.append(
            InterceptValuePayload(
                spec=InterceptSpecPayload(
                    kind=str(spec.get("kind", "")),
                    level=float(spec.get("level", 0)),
                    basis=str(spec.get("basis", "relative_percent")),
                    label=spec.get("label"),
                ),
                value=float(d.get("value", 0)),
                confidence_interval_low=d.get("ci_low"),
                confidence_interval_high=d.get("ci_high"),
                at_bound=bool(d.get("at_bound", False)),
            )
        )
    return out


@dataclass(frozen=True, kw_only=True)
class GetProtocolActivityQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True)
class InterceptSpecPayload:
    kind: str  # "ic" | "ec"
    level: float
    basis: str  # "relative_percent" | "absolute"
    label: str | None = None


@dataclass(frozen=True)
class InterceptValuePayload:
    spec: InterceptSpecPayload
    value: float
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    at_bound: bool = False


@dataclass(frozen=True)
class CurveParams:
    hill_slope: float
    top: float
    bottom: float
    fitted_value: float
    r_squared: float
    # Per-spec intercepts (EC50, EC90, IC10, ...). Empty list on legacy
    # curves; the FE column factory falls back to a single "Fitted Value"
    # column when intercept_values is empty.
    intercept_values: list[InterceptValuePayload] = field(default_factory=list)


@dataclass(frozen=True)
class ReadoutValue:
    best: float | None = None
    mean: float | None = None
    curve_class: str | None = None
    curve_params: CurveParams | None = None
    data_points: list[dict[str, float]] | None = None
    n: int | None = None
    sd: float | None = None


@dataclass(frozen=True)
class ReadoutDefInfo:
    id: uuid.UUID
    name: str
    data_type: str
    unit: str | None
    best_direction: str  # "high" or "low"
    # For ``dose_response`` readouts, the protocol's declared intercept
    # specs (one per column on the activity grid). Empty for numeric
    # readouts. Drives dynamic column headers — never hardcode "EC50".
    intercepts: list[InterceptSpecPayload] = field(default_factory=list)


@dataclass(frozen=True)
class CompoundActivity:
    molecule_id: uuid.UUID
    molecule_name: str
    registration_number: str
    run_count: int
    last_tested: str | None
    smiles: str | None = None
    batch_number: str | None = None
    synonyms: list[str] = field(default_factory=list)
    readouts: dict[str, ReadoutValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivitySummaryV2:
    items: list[CompoundActivity]
    readout_definitions: list[ReadoutDefInfo]
    total_compounds: int


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class GetProtocolActivitySummary:
    """Aggregate compound results across all runs for a protocol.

    Delegates raw SA queries to ProtocolActivityReader (infrastructure).
    The use case owns business logic: auth, readout definition filtering,
    and the Python merge of query results into DTOs.
    """

    def __init__(self, reader: ProtocolActivityReader) -> None:
        self._reader = reader

    async def __call__(
        self,
        input: GetProtocolActivityQuery,
        auth: AuthContext | None = None,
    ) -> Result[ActivitySummaryV2, DomainError]:
        from cellar.application.auth import require_same_workspace

        require_same_workspace(auth, input.workspace_id)

        ws = input.workspace_id
        pid = input.protocol_id

        # Fetch all raw data from the reader
        data = await self._reader.get_activity_data(ws, pid, VALID_STATUSES)

        # --- Protocol existence check (business logic) ---
        if data.protocol is None:
            return Failure(NotFoundError(f"Protocol {pid} not found in workspace"))

        # Build readout_defs (only numeric + dose_response). For DR rows
        # we key by the readout-def UUID — curve_type was ambiguous when
        # two DR readouts on one protocol shared it.
        readout_defs: list[ReadoutDefInfo] = []

        for rd in data.protocol.readout_definitions:
            if rd.data_type not in _AGGREGATABLE_DATA_TYPES:
                continue

            best_direction = "low" if rd.data_type == "dose_response" else "high"
            intercept_specs: list[InterceptSpecPayload] = []
            if rd.data_type == "dose_response":
                cfg = rd.dose_response_config
                # ``rd`` is a ``ProtocolRow.readout_definitions`` entry — the
                # read-model carries the SA model, where dose_response_config
                # is a JSONB dict (not the domain VO). Defensively handle both.
                cfg_dict = cfg if isinstance(cfg, dict) else getattr(cfg, "__dict__", None)
                raw_intercepts = (
                    (cfg_dict or {}).get("intercepts") if isinstance(cfg_dict, dict) else None
                )
                if isinstance(raw_intercepts, list):
                    for spec in raw_intercepts:
                        if not isinstance(spec, dict):
                            continue
                        intercept_specs.append(
                            InterceptSpecPayload(
                                kind=str(spec.get("kind", "")),
                                level=float(spec.get("level", 0)),
                                basis=str(spec.get("basis", "relative_percent")),
                                label=spec.get("label"),
                            )
                        )

            readout_defs.append(
                ReadoutDefInfo(
                    id=rd.id,
                    name=rd.name,
                    data_type=rd.data_type,
                    unit=rd.unit,
                    best_direction=best_direction,
                    intercepts=intercept_specs,
                )
            )

        if not readout_defs:
            return Success(
                ActivitySummaryV2(
                    items=[],
                    readout_definitions=[],
                    total_compounds=0,
                )
            )

        if not data.molecule_rows:
            return Success(
                ActivitySummaryV2(
                    items=[],
                    readout_definitions=readout_defs,
                    total_compounds=0,
                )
            )

        # ----------------------------------------------------------
        # Python merge
        # ----------------------------------------------------------

        # Index numeric rows: (molecule_id, readout_name) -> row
        numeric_map: dict[tuple[uuid.UUID, str], object] = {
            (row.molecule_id, row.readout_name): row for row in data.numeric_rows
        }

        # Index DR agg rows: (molecule_id, readout_definition_id) -> row
        dr_agg_map: dict[tuple[uuid.UUID, uuid.UUID], object] = {
            (row.molecule_id, row.readout_definition_id): row for row in data.dr_agg_rows
        }

        # Index best params rows: (molecule_id, readout_definition_id) -> row
        best_params_map: dict[tuple[uuid.UUID, uuid.UUID], object] = {
            (row.molecule_id, row.readout_definition_id): row for row in data.best_params_rows
        }

        items: list[CompoundActivity] = []
        for mol in data.molecule_rows:
            readouts: dict[str, ReadoutValue] = {}
            best_batch_number: str | None = None

            for rd_info in readout_defs:
                if rd_info.data_type == "dose_response":
                    dr_key = (mol.molecule_id, rd_info.id)
                    dr_row = dr_agg_map.get(dr_key)
                    bp_row = best_params_map.get(dr_key)

                    if dr_row is None:
                        continue

                    curve_params: CurveParams | None = None
                    curve_class: str | None = None
                    data_points: list[dict[str, float]] | None = None
                    if bp_row is not None:
                        curve_class = bp_row.curve_class
                        if best_batch_number is None:
                            best_batch_number = getattr(bp_row, "batch_number", None)
                        intercepts_payload = _hydrate_intercept_payloads(bp_row.intercept_values)
                        curve_params = CurveParams(
                            hill_slope=float(bp_row.hill_slope),
                            top=float(bp_row.top),
                            bottom=float(bp_row.bottom),
                            fitted_value=float(bp_row.fitted_value),
                            r_squared=float(bp_row.r_squared),
                            intercept_values=intercepts_payload,
                        )
                        # Extract condensed data points from raw_data JSONB
                        raw = bp_row.raw_data
                        if raw and isinstance(raw, list):
                            data_points = _condense_raw_data(raw)

                    readouts[rd_info.name] = ReadoutValue(
                        best=float(dr_row.best) if dr_row.best is not None else None,
                        mean=round(float(dr_row.geo_mean), 6)
                        if dr_row.geo_mean is not None
                        else None,
                        curve_class=curve_class,
                        curve_params=curve_params,
                        data_points=data_points,
                    )
                else:
                    # Numeric readout
                    num_key = (mol.molecule_id, rd_info.name)
                    num_row = numeric_map.get(num_key)
                    if num_row is None:
                        continue

                    readouts[rd_info.name] = ReadoutValue(
                        best=float(num_row.best) if num_row.best is not None else None,
                        mean=round(float(num_row.mean), 4) if num_row.mean is not None else None,
                        n=int(num_row.n) if num_row.n is not None else None,
                        sd=round(float(num_row.sd), 4) if num_row.sd is not None else None,
                    )

            items.append(
                CompoundActivity(
                    molecule_id=mol.molecule_id,
                    molecule_name=mol.molecule_name or "",
                    registration_number=mol.registration_number or "",
                    run_count=mol.run_count,
                    last_tested=(
                        mol.last_tested.isoformat() if mol.last_tested is not None else None
                    ),
                    smiles=mol.smiles,
                    batch_number=best_batch_number,
                    synonyms=data.synonym_map.get(mol.molecule_id, []),
                    readouts=readouts,
                )
            )

        return Success(
            ActivitySummaryV2(
                items=items,
                readout_definitions=readout_defs,
                total_compounds=len(items),
            )
        )
