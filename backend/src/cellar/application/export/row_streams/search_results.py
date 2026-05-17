"""SearchResultsRowStream — cursored re-execution of ExecuteSearch for export."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

from returns.result import Success

from cellar.application.export.row_streams.base import ColumnSpec, ExportRow, RowStream
from cellar.application.research_organization.execute_search import (
    ExecuteSearch,
    ExecuteSearchQuery,
)
from cellar.domain.shared.aggregation_types import SelectionRule


@dataclass
class SearchResultsRowStream:
    """Row source that re-runs a saved search query in pages.

    Implements the ``RowStream`` Protocol. The export workflow calls
    ``total_count()`` once for progress tracking, then streams rows via
    ``iter_batches()``.

    ``payload`` is the wire-shape dict from the saved export job — it carries
    the same fields as ``ExecuteSearchBody`` (query, protocol_columns,
    aggregation, project_ids, sort_by, sort_dir, saved_search_id).

    ``protocols_reader`` is an async callable ``(workspace_id) -> list[Protocol]``
    used to resolve column headers. It is called once lazily.
    """

    workspace_id: uuid.UUID
    payload: dict[str, Any]
    execute_search: ExecuteSearch
    protocols_reader: Any  # async callable: (workspace_id) -> list[Protocol]
    requested_by: uuid.UUID

    def __post_init__(self) -> None:
        self._cached_total: int | None = None
        self._protocols_cache: list | None = None
        self.columns: list[ColumnSpec] = []  # populated lazily by _ensure_columns

    async def total_count(self) -> int:
        # _ensure_columns shares the same lazy prerequisites (protocols lookup +
        # first-page probe) and is idempotent.  Calling it here guarantees that
        # ``self.columns`` is populated before any consumer reads it — in
        # particular before ``RenderExport.__call__`` passes ``stream.columns``
        # to the renderer, which happens right after ``await stream.total_count()``.
        await self._ensure_columns()
        if self._cached_total is None:
            page = await self._fetch_page(cursor=None, limit=1)
            self._cached_total = page.total_count or 0
        return self._cached_total

    async def iter_batches(self, batch_size: int) -> AsyncIterator[list[ExportRow]]:
        await self._ensure_columns()
        cursor: str | None = None
        while True:
            page = await self._fetch_page(cursor=cursor, limit=batch_size)
            if not page.items:
                break
            yield [self._row_for(mol, page.activity_data) for mol in page.items]
            if not page.next_cursor:
                break
            cursor = page.next_cursor

    async def _fetch_page(self, *, cursor: str | None, limit: int):
        cmd = ExecuteSearchQuery(
            workspace_id=self.workspace_id,
            query=self.payload.get("query"),
            saved_search_id=_parse_uuid(self.payload.get("saved_search_id")),
            protocol_columns=self.payload.get("protocol_columns"),
            aggregation=SelectionRule(
                self.payload.get("aggregation", SelectionRule.LATEST_APPROVED_RUN.value)
            ),
            cursor_id=_parse_uuid(cursor) if cursor else None,
            limit=limit,
            project_ids=[_parse_uuid(p) for p in (self.payload.get("project_ids") or [])],
            sort_by=self.payload.get("sort_by"),
            sort_dir=self.payload.get("sort_dir"),
        )
        result = await self.execute_search(
            cmd, auth=_AuthShim(self.workspace_id, self.requested_by)
        )
        if not isinstance(result, Success):
            raise RuntimeError(f"search execution failed: {result.failure()}")
        return result.unwrap()

    async def _ensure_columns(self) -> None:
        if self.columns:
            return
        protocol_cols = self.payload.get("protocol_columns") or []
        self._protocols_cache = await self.protocols_reader(self.workspace_id)
        self.columns = _build_columns(protocol_cols, self._protocols_cache)

    def _row_for(self, mol, activity_data: dict | None) -> ExportRow:
        raw = {
            "id": str(mol.id),
            "registration_number": (
                mol.registration_number.value if mol.registration_number else ""
            ),
            "name": mol.name,
            "smiles": getattr(mol.structure, "smiles", None) if mol.structure else None,
            "inchi_key": getattr(mol.structure, "inchi_key", None) if mol.structure else None,
            "molecular_formula": (
                getattr(mol.descriptors, "molecular_formula", None)
                if mol.descriptors
                else None
            ),
            "molecular_weight": (
                getattr(mol.descriptors, "molecular_weight", None)
                if mol.descriptors
                else None
            ),
            "logp": getattr(mol.descriptors, "logp", None) if mol.descriptors else None,
            "hbd": getattr(mol.descriptors, "hbd", None) if mol.descriptors else None,
            "hba": getattr(mol.descriptors, "hba", None) if mol.descriptors else None,
            "tpsa": getattr(mol.descriptors, "tpsa", None) if mol.descriptors else None,
            "activity": (activity_data or {}).get(str(mol.id)) or {},
        }
        cells: dict[str, Any] = {}
        for spec in self.columns:
            cells[spec.key] = _cell_value(spec, raw)
        return ExportRow(cells=cells, raw=raw)


# ---------------------------------------------------------------------------
# Column building
# ---------------------------------------------------------------------------


def _build_columns(protocol_cols: list[str], protocols: list) -> list[ColumnSpec]:
    base: list[ColumnSpec] = [
        ColumnSpec(key="registration_number", header="Reg #", kind="text"),
        ColumnSpec(key="name", header="Name", kind="text"),
        ColumnSpec(key="smiles", header="SMILES", kind="smiles"),
        ColumnSpec(key="inchi_key", header="InChIKey", kind="text"),
        ColumnSpec(key="molecular_formula", header="Formula", kind="text"),
        ColumnSpec(key="molecular_weight", header="MW", kind="number"),
        ColumnSpec(key="logp", header="LogP", kind="number"),
        ColumnSpec(key="hbd", header="HBD", kind="number"),
        ColumnSpec(key="hba", header="HBA", kind="number"),
        ColumnSpec(key="tpsa", header="TPSA", kind="number"),
    ]
    # Activity columns — one per protocol_column token.
    # DR tokens (drc:*) expand to one group of value/qualifier/unit/run_count/curve_class
    # per intercept, plus a trailing image_curve column for the whole readout.
    # Non-DR tokens (rd:*) emit a single value column.
    by_id = {str(p.id): p for p in protocols}
    for col_token in protocol_cols:
        base.extend(_expand_protocol_column(col_token, by_id))
    return base


def _expand_protocol_column(token: str, by_id: dict) -> list[ColumnSpec]:
    """Expand a protocol_column token into one or more ``ColumnSpec`` objects.

    Token grammar (matches FE ``protocol-column-id.ts``):
      ``rd:<proto_id>:<rd_id>[:<normalization>]`` — scalar readout
      ``drc:<rd_id>``                              — DR readout, all intercepts
      ``drc:<rd_id>:<kind>:<level>``               — DR readout, one intercept
    """
    parts = token.split(":")
    if parts[0] == "rd":
        proto_id = parts[1]
        rd_id = parts[2]
        proto = by_id.get(proto_id)
        rd = next(
            (r for r in (proto.readout_definitions if proto else []) if str(r.id) == rd_id),
            None,
        )
        rd_name = rd.name if rd else "Readout"
        proto_name = proto.name if proto else "Protocol"
        return [
            ColumnSpec(
                key=f"{token}::value",
                header=f"{proto_name}::{rd_name}",
                kind="number",
                unit=getattr(rd, "unit", None),
                group=proto_name,
            )
        ]
    if parts[0] == "drc":
        rd_id = parts[1]
        proto = next(
            (
                p
                for p in by_id.values()
                for r in (p.readout_definitions or [])
                if str(r.id) == rd_id
            ),
            None,
        )
        rd = (
            next(
                (r for r in (proto.readout_definitions or []) if str(r.id) == rd_id),
                None,
            )
            if proto
            else None
        )
        rd_name = rd.name if rd else "Readout"
        proto_name = proto.name if proto else "Protocol"
        intercepts = (
            (getattr(rd, "dose_response_config", None).intercepts
             if rd and getattr(rd, "dose_response_config", None) else [])
            or []
        )
        cols: list[ColumnSpec] = []
        for spec in intercepts:
            label = spec.label or f"{spec.kind.value.upper()}{int(spec.level)}"
            base_key = f"drc:{rd_id}:{spec.kind.value}:{spec.level}"
            cols.extend([
                ColumnSpec(
                    key=f"{base_key}::value",
                    header=f"{proto_name}::{rd_name}::{label}",
                    kind="number",
                    unit=getattr(rd, "unit", None),
                    group=proto_name,
                ),
                ColumnSpec(
                    key=f"{base_key}::qualifier",
                    header=f"{proto_name}::{rd_name}::{label}::qualifier",
                    kind="qualifier",
                    group=proto_name,
                ),
                ColumnSpec(
                    key=f"{base_key}::unit",
                    header=f"{proto_name}::{rd_name}::{label}::unit",
                    kind="text",
                    group=proto_name,
                ),
                ColumnSpec(
                    key=f"{base_key}::run_count",
                    header=f"{proto_name}::{rd_name}::{label}::n",
                    kind="number",
                    group=proto_name,
                ),
                ColumnSpec(
                    key=f"{base_key}::curve_class",
                    header=f"{proto_name}::{rd_name}::{label}::class",
                    kind="text",
                    group=proto_name,
                ),
            ])
        # One Plot column per readout-def (NOT per intercept) — matches the
        # frontend grid. ExcelRenderer + PdfRenderer embed a sparkline PNG/SVG
        # here; CSV + SDF skip image_curve columns.
        if intercepts:
            cols.append(
                ColumnSpec(
                    key=f"drc:{rd_id}::plot",
                    header=f"{proto_name}::{rd_name}::Plot",
                    kind="image_curve",
                    group=proto_name,
                )
            )
        return cols
    return []


# ---------------------------------------------------------------------------
# Cell value resolution
# ---------------------------------------------------------------------------


def _activity_parent_token(col_token: str) -> str:
    """Return the parent activity-dict key for a (possibly narrowed) token.

    DR tokens in the column spec are narrowed to include the intercept kind
    and level — e.g. ``drc:<rd_id>:ec:50.0``.  But ``ExecuteSearch`` keys
    ``activity_data`` by the *parent* readout token ``drc:<rd_id>``, because
    a single ActivityValue covers all intercepts for that readout-def.
    Non-DR tokens are keyed verbatim (no narrowing) so they pass through
    unchanged.

    Token grammar (must match ``_expand_protocol_column`` and
    ``molecule_activity_service._enrich_molecules``):
      ``drc:<rd_id>``               — already the parent; returned as-is
      ``drc:<rd_id>:<kind>:<level>``— narrowed; strip to ``drc:<rd_id>``
      ``rd:<proto_id>:<rd_id>``     — scalar readout; returned as-is
    """
    if not col_token.startswith("drc:"):
        return col_token
    parts = col_token.split(":")
    if len(parts) >= 4:  # drc : <rd_id> : <kind> : <level>
        return ":".join(parts[:2])  # → drc:<rd_id>
    return col_token  # already the parent


def _cell_value(spec: ColumnSpec, raw: dict) -> Any:
    """Resolve a cell value from a molecule's raw dict.

    Top-level fields (registration_number, smiles, …) are read directly.
    Activity fields are read from ``raw["activity"][parent_token]`` and
    further resolved via suffix (``::value``, ``::qualifier``, etc.).

    DR column specs use a *narrowed* token that includes the intercept kind
    and level (e.g. ``drc:<rd_id>:ec:50.0::value``).  The activity dict is
    keyed by the *parent* token ``drc:<rd_id>`` — one ActivityValue per
    readout-def carries all intercepts.  ``_activity_parent_token`` handles
    the translation so the activity lookup always finds its entry.
    """
    if spec.key in raw:
        return raw[spec.key]
    if "::" not in spec.key:
        return None
    col_token, suffix = spec.key.rsplit("::", 1)
    parent_token = _activity_parent_token(col_token)
    av = (raw.get("activity") or {}).get(parent_token)
    if not av:
        return None
    iv = _intercept_for(av, col_token) if col_token.startswith("drc:") else None
    if suffix == "value":
        if iv is not None:
            return None if iv.get("value") is None else iv["value"]
        return av.get("value")
    if suffix == "qualifier":
        return _qualifier_of(av, iv)
    if suffix == "unit":
        return av.get("unit")
    if suffix == "run_count":
        return av.get("run_count") or 1
    if suffix == "curve_class":
        return (av.get("curve_params") or {}).get("curve_class")
    return None


def _intercept_for(av: dict, col_token: str) -> dict | None:
    """Find the intercept entry in ``av["intercept_values"]`` matching the token.

    Token format: ``drc:<rd_id>:<kind>:<level>``
    """
    parts = col_token.split(":")
    if len(parts) < 4:
        return None
    target = (parts[2], float(parts[3]))
    for iv in av.get("intercept_values") or []:
        spec = iv.get("spec") or {}
        if (spec.get("kind"), spec.get("level")) == target:
            return iv
    return None


def _qualifier_of(av: dict, iv: dict | None) -> str:
    """Derive the display qualifier string from an activity value dict.

    Inactive curves → ``"ND"``; at-bound curves → ``">"``; healthy → ``"="``.
    """
    if iv is not None:
        if iv.get("at_bound"):
            return ">"
        if iv.get("value") is None:
            return "ND"
        return "="
    cc = (av.get("curve_params") or {}).get("curve_class")
    if cc == "inactive":
        return "ND"
    return av.get("qualifier") or "="


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_uuid(value: Any) -> uuid.UUID | None:
    """Parse a string, UUID, or None to ``uuid.UUID | None``."""
    if value is None:
        return None
    return uuid.UUID(str(value))


class _AuthShim:
    """Minimal AuthContext stand-in for re-running ExecuteSearch in a worker context.

    ``require_same_workspace`` only reads ``.workspace_id``.
    The other Protocol members are present to satisfy structural typing.
    """

    def __init__(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self._workspace_id = workspace_id
        self._user_id = user_id

    @property
    def workspace_id(self) -> uuid.UUID:
        return self._workspace_id

    @property
    def user_id(self) -> uuid.UUID:
        return self._user_id

    @property
    def workspace_role(self) -> str:
        return "viewer"

    @property
    def is_admin(self) -> bool:
        return False

    def has_role(self, minimum_role: str) -> bool:
        _order = {"viewer": 0, "editor": 1, "admin": 2}
        return _order.get(self.workspace_role, 0) >= _order.get(minimum_role, 0)
