"""SearchResultsRowStream — cursored re-execution of ExecuteSearch for export."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any

from returns.result import Success

from cellar.application.export.renderers.sparkline import MAX_OVERLAY_CURVES, OVERLAY_COLORS
from cellar.application.export.row_streams.base import ColumnSpec, ExportRow
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
    # Export format hint — drives format-specific column shaping (e.g. CSV/SDF
    # always include SMILES regardless of the chemist's visibleFields). When
    # None, falls back to the visibleFields whitelist exactly.
    format: str | None = None

    def __post_init__(self) -> None:
        self._cached_total: int | None = None
        self._protocols_cache: list | None = None
        self.columns: list[ColumnSpec] = []  # populated lazily by _ensure_columns

    async def total_count(self) -> int:
        # _ensure_columns runs the first-page probe that yields both the total
        # and the split column groups, and is idempotent. Calling it here
        # guarantees ``self.columns`` is populated before ``RenderExport``
        # passes ``stream.columns`` to the renderer.
        await self._ensure_columns()
        return self._cached_total or 0

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
                self.payload.get("aggregation", SelectionRule.LATEST_RUN.value)
            ),
            cursor=cursor,
            limit=limit,
            # None (not []) when absent: [] means "unassigned molecules only"
            # to the visibility clause, which would drop every compound that
            # belongs to a project from an export the grid showed in full.
            project_ids=[_parse_uuid(p) for p in (self.payload.get("project_ids") or [])] or None,
            sort_by=self.payload.get("sort_by"),
            sort_dir=self.payload.get("sort_dir"),
        )
        result = await self.execute_search(
            cmd, auth=ExportAuth(self.workspace_id, self.requested_by)
        )
        if not isinstance(result, Success):
            raise RuntimeError(f"search execution failed: {result.failure()}")
        return result.unwrap()

    async def _ensure_columns(self) -> None:
        if self.columns:
            return
        probe = await self._fetch_page(cursor=None, limit=1)
        self._cached_total = probe.total_count or 0
        protocol_cols = self.payload.get("protocol_columns") or []
        report_config = self.payload.get("reportConfig") or self.payload.get("report_config")
        self._protocols_cache = await self.protocols_reader(self.workspace_id)
        self.columns = _build_columns(
            protocol_cols,
            self._protocols_cache,
            report_config=report_config,
            format=self.format,
            column_groups=probe.column_groups,
        )

    def _row_for(self, mol, activity_data: dict | None) -> ExportRow:
        raw = {
            "id": str(mol.id),
            "registration_number": (
                mol.registration_number.value if mol.registration_number else ""
            ),
            "name": mol.name,
            "smiles": getattr(mol.structure, "smiles", None) if mol.structure else None,
            "inchi_key": getattr(mol.structure, "inchi_key", None) if mol.structure else None,
            "lifecycle_stage": str(mol.lifecycle_stage) if mol.lifecycle_stage else None,
            **{
                key: getattr(mol.descriptors, key, None) if mol.descriptors else None
                for key in _PROPERTY_COLUMNS
            },
            "activity": (activity_data or {}).get(str(mol.id)) or {},
        }
        cells: dict[str, Any] = {}
        for spec in self.columns:
            cells[spec.key] = _cell_value(spec, raw)
        return ExportRow(cells=cells, raw=raw)


# ---------------------------------------------------------------------------
# Column building
# ---------------------------------------------------------------------------


# Property column id → (header, kind, decimals). Keys are ``ComputedDescriptors``
# fields — the same ids the FE customizer (report-customizer.tsx PROPERTY_FIELDS)
# and grid use. Listed in the grid's display order with the grid's decimals
# (results-grid.tsx PROPERTY_COLUMNS); headers stay spelled out, since CSV
# consumers read columns by name.
_PROPERTY_COLUMNS: dict[str, tuple[str, str, int | None]] = {
    "molecular_weight": ("MW", "number", 1),
    "logp": ("LogP", "number", 2),
    "tpsa": ("TPSA", "number", 1),
    "hbd": ("HBD", "number", None),
    "hba": ("HBA", "number", None),
    "rotatable_bonds": ("RotB", "number", None),
    "heavy_atom_count": ("Heavy Atoms", "number", None),
    "aromatic_rings": ("Aromatic Rings", "number", None),
    "ring_count": ("Rings", "number", None),
    "ro5_violations": ("Ro5 Violations", "number", None),
    "molecular_formula": ("Formula", "text", None),
}

# The grid's value cells read ``value.toPrecision(4)``.
_VALUE_PRECISION = 4

_NORMALIZATION_LABELS: dict[str | None, str] = {
    "percent_inhibition": "% Inhibition",
    "percent_activation": "% Activation",
    "percent_control": "% Control",
    "z_score": "Z-Score",
}

# Molecule (non-structural) column id → (header, kind).
_MOLECULE_COLUMNS: dict[str, tuple[str, str]] = {
    "name": ("Name", "text"),
    "lifecycle_stage": ("Stage", "text"),
}


def _build_columns(
    protocol_cols: list[str],
    protocols: list,
    *,
    report_config: dict | None = None,
    format: str | None = None,
    column_groups: dict[str, Any] | None = None,
) -> list[ColumnSpec]:
    """Build export columns honoring the FE reportConfig.

    When ``report_config`` is None *or empty* (legacy payload), falls back
    to the static column set that shipped on 2026-05-16.

    Otherwise, columns reflect ``reportConfig.visibleFields``:
      - ``structure`` list — ``"structure"`` emits the image column,
        ``"registration_number"`` emits Reg #, ``"smiles"`` emits SMILES,
        ``"inchi_key"`` emits InChIKey.
      - ``properties`` is whitelist-style; only listed ids show up.
      - ``molecule`` drives Name / Stage / etc.

    ``format`` is the export format ("csv" / "sdf" / "xlsx" / "pdf"). For
    CSV / SDF — machine-readable formats whose primary purpose is being
    fed into downstream tools — we force SMILES on even if the chemist
    didn't tick it in the customize panel. For XLSX / PDF we respect the
    panel exactly.
    """
    fields = None
    if isinstance(report_config, dict):
        candidate = report_config.get("visibleFields")
        if isinstance(candidate, dict):
            fields = candidate
    base: list[ColumnSpec] = []

    machine_format = format in ("csv", "sdf")

    if fields is None:
        # Legacy default — matches the pre-reportConfig column set.
        base.extend(
            [
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
        )
    else:
        structure_fields = list(fields.get("structure") or [])
        if "structure" in structure_fields:
            base.append(ColumnSpec(key="structure", header="Structure", kind="image_structure"))
        if "registration_number" in structure_fields:
            base.append(ColumnSpec(key="registration_number", header="Reg #", kind="text"))
        for mol_field in fields.get("molecule") or []:
            spec = _MOLECULE_COLUMNS.get(mol_field)
            if spec:
                base.append(ColumnSpec(key=mol_field, header=spec[0], kind=spec[1]))  # type: ignore[arg-type]
        if "smiles" in structure_fields or machine_format:
            base.append(ColumnSpec(key="smiles", header="SMILES", kind="smiles"))
        if "inchi_key" in structure_fields:
            base.append(ColumnSpec(key="inchi_key", header="InChIKey", kind="text"))
        wanted = set(fields.get("properties") or [])
        for prop_id, (header, kind, digits) in _PROPERTY_COLUMNS.items():
            if prop_id in wanted:
                base.append(ColumnSpec(key=prop_id, header=header, kind=kind, digits=digits))  # type: ignore[arg-type]

    # The grid's display settings (use-report-config.ts shownPlotLayout):
    # Compact hides every plot; Overlay applies in Detailed only.
    config = report_config if isinstance(report_config, dict) else {}
    show_plots = config.get("displayPreset", "detailed") != "compact"
    overlay = show_plots and config.get("plotLayout") == "overlay"

    # Activity columns. DR tokens expand to one *value* column per intercept
    # (header = label, group = protocol name) plus one Plot column per readout.
    # A protocol's columns sit together, as in the grid.
    by_id = {str(p.id): p for p in protocols}
    for proto_id, tokens in _by_protocol(protocol_cols, by_id):
        specs = [spec for token in tokens for spec in _expand_protocol_column(token, by_id)]
        if not show_plots:
            specs = [s for s in specs if s.kind != "image_curve"]
        split = (column_groups or {}).get(proto_id or "")
        if split is None:
            base.extend(specs)
            continue
        # A split protocol repeats its columns once per group, side by side,
        # under the protocol's header ("EGFR · by ATP") and the group's ("10 µM").
        # Overlaid, each group drops its own plot for one plot per readout after
        # the groups, every group's curve in the colour its header carries.
        groups = split["groups"]
        by = split["split"]
        protocol = f"by {by['condition']}" if by.get("by") == "condition" else "by run"
        specs = [replace(s, group=" · ".join(p for p in (s.group, protocol) if p)) for s in specs]
        plots = [s for s in specs if s.kind == "image_curve"]
        overlaid = overlay and bool(plots) and 0 < len(groups) <= MAX_OVERLAY_CURVES
        for i, group in enumerate(groups):
            base.extend(
                replace(
                    spec,
                    key=_group_key(spec.key, group["key"]),
                    subgroup=_group_header(group),
                    group_color=OVERLAY_COLORS[i] if overlaid else None,
                )
                for spec in specs
                if not (overlaid and spec.kind == "image_curve")
            )
        if overlaid:
            base.extend(
                _overlay_plot(plot, groups, by_id, several=len(plots) > 1) for plot in plots
            )
    return base


def _group_header(group: dict) -> str:
    """A split group's label, marked when its run was rejected (the grid's
    groupHeader without the run count, which a CSV column name shouldn't carry)."""
    return (
        f"{group['label']} (rejected)"
        if "rejected" in (group.get("flags") or [])
        else group["label"]
    )


def _by_protocol(tokens: list[str], by_id: dict[str, Any]) -> list[tuple[str | None, list[str]]]:
    """Tokens grouped by their protocol in first-seen order; a token with no
    protocol (``any``) stands alone."""
    grouped: dict[str, tuple[str | None, list[str]]] = {}
    for token in tokens:
        proto_id = _owning_protocol_id(token, by_id)
        grouped.setdefault(proto_id or token, (proto_id, []))[1].append(token)
    return list(grouped.values())


def _overlay_plot(
    plot: ColumnSpec, groups: list[dict], by_id: dict, *, several: bool
) -> ColumnSpec:
    """One plot of every group's curve for a DR readout (results-grid.tsx
    buildOverlayPlotColumns): "Plot", or "Plot · <readout>" when the protocol
    shows several."""
    parent = plot.key.rsplit("::", 1)[0]  # drc:<rd_id>
    rd_id = parent.split(":")[1]
    name = next(
        (
            r.name
            for p in by_id.values()
            for r in (p.readout_definitions or [])
            if str(r.id) == rd_id
        ),
        None,
    )
    return replace(
        plot,
        key=f"{parent}::overlay",
        header=f"Plot · {name}" if several and name else "Plot",
        overlay_of=tuple(f"{parent}@{g['key']}" for g in groups),
    )


def _owning_protocol_id(token: str, by_id: dict[str, Any]) -> str | None:
    parts = token.split(":")
    if parts[0] == "rd" and len(parts) >= 3:
        return parts[1]
    if parts[0] == "drc" and len(parts) >= 2:
        return next(
            (
                pid
                for pid, p in by_id.items()
                for r in (p.readout_definitions or [])
                if str(r.id) == parts[1]
            ),
            None,
        )
    return None


def _group_key(key: str, group_key: str) -> str:
    """``<column>::<suffix>`` → ``<column>@<group>::<suffix>``."""
    column, sep, suffix = key.rpartition("::")
    return f"{column}@{group_key}{sep}{suffix}" if sep else f"{key}@{group_key}"


def _expand_protocol_column(token: str, by_id: dict) -> list[ColumnSpec]:
    """Expand a protocol_column token into ColumnSpec objects.

    Mirrors the FE search grid layout: one *value* cell per intercept
    (header = intercept label, group = protocol name) and one Plot cell
    per readout (header = "Plot", same group). Qualifier / unit / n /
    curve_class are NOT separate columns — they're folded into the value
    cell's display string ("ND", ">100 µM", "67.4 µM ₂") by the cell
    resolver, matching the chemist's on-screen experience.

    Token grammar (matches FE ``protocol-column-id.ts``):
      ``rd:<proto_id>:<rd_id>[:<normalization>]`` — scalar readout
      ``drc:<rd_id>``                              — DR readout, all intercepts
      ``drc:<rd_id>:<kind>:<level>``               — DR readout, one intercept
      ``any``                                       — all activity entries
    """
    if token == "any":  # noqa: S105  # column-spec token, not a credential
        return [ColumnSpec(key="any::text", header="Active in", kind="text")]
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
        proto_code = proto.code if proto else None
        group_label = f"{proto_code} {proto_name}" if proto_code else proto_name
        # 4-segment token = a normalized layer ("raw AU (% Inhibition)"), whose
        # values are not in the readout's raw unit.
        normalization = parts[3] if len(parts) > 3 else None
        return [
            ColumnSpec(
                key=f"{token}::value",
                header=(
                    f"{rd_name} ({_NORMALIZATION_LABELS.get(normalization, normalization)})"
                    if normalization
                    else rd_name
                ),
                kind="number",
                unit=None if normalization else getattr(rd, "unit", None),
                group=group_label,
                group_code=proto_code,
                precision=_VALUE_PRECISION,
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
        proto_code = proto.code if proto else None
        group_label = f"{proto_code} {proto_name}" if proto_code else proto_name
        # When a protocol has a single DR readout the FE drops the readout
        # name from the header ("EC50" alone is unambiguous). When there
        # are multiple, we disambiguate with "{readout} {label}".
        dr_readouts = (
            [
                r
                for r in (proto.readout_definitions or [])
                if getattr(r, "dose_response_config", None)
            ]
            if proto
            else []
        )
        prefix = "" if len(dr_readouts) <= 1 else f"{rd_name} "
        intercepts = (
            getattr(rd, "dose_response_config", None).intercepts
            if rd and getattr(rd, "dose_response_config", None)
            else []
        ) or []
        cols: list[ColumnSpec] = []
        for spec in intercepts:
            label = spec.label or f"{spec.kind.value.upper()}{int(spec.level)}"
            base_key = f"drc:{rd_id}:{spec.kind.value}:{spec.level}"
            cols.append(
                ColumnSpec(
                    key=f"{base_key}::value",
                    header=f"{prefix}{label}",
                    kind="number",
                    # Fitted potencies are stored in the protocol's dose unit
                    # (the grid shows the same); the readout's own unit field
                    # can disagree (COX-2: "nM" on µM values).
                    unit=str(proto.dose_unit) if proto else getattr(rd, "unit", None),
                    group=group_label,
                    group_code=proto_code,
                    precision=_VALUE_PRECISION,
                )
            )
        # One Plot column per readout-def — matches the frontend grid.
        # ExcelRenderer + PdfRenderer embed a sparkline PNG; CSV + SDF
        # skip image_curve columns.
        if intercepts:
            cols.append(
                ColumnSpec(
                    key=f"drc:{rd_id}::plot",
                    header=f"{prefix}Plot",
                    kind="image_curve",
                    group=group_label,
                    group_code=proto_code,
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
    if col_token == "any":  # noqa: S105  # column-spec token, not a credential
        block = (raw.get("activity") or {}).get("any") or {}
        return _format_any_entries(block.get("entries") or [])
    col_token, at, group_key = col_token.partition("@")
    parent_token = _activity_parent_token(col_token) + (f"@{group_key}" if at else "")
    av = (raw.get("activity") or {}).get(parent_token)
    if not av:
        return None
    value, qualifier = _endpoint(av, col_token)
    if suffix == "value":
        return _display(value, qualifier)
    if suffix == "qualifier":
        return _qualifier_text(value, qualifier)
    if suffix == "unit":
        return av.get("unit")
    if suffix == "run_count":
        return av.get("run_count") or 1
    if suffix == "curve_class":
        return (av.get("curve_params") or {}).get("curve_class")
    return None


def _format_any_entries(entries: list[dict]) -> str:
    """ "Protocol: LABEL value unit" per entry, joined by "; " — the text
    form of the grid's "Active in" cell."""
    parts: list[str] = []
    for e in entries:
        value = e.get("value")
        if value is None:
            shown = "—"
        else:
            q = e.get("qualifier") or ""
            q = "" if q == "=" else q
            num = f"{value:g}"
            unit = e.get("unit") or ""
            shown = f"{q}{num}{' ' + unit if unit else ''}"
        protocol_name = e.get("protocol_name") or "Protocol"
        if e.get("protocol_code"):
            protocol_name = f"{e['protocol_code']} {protocol_name}"
        label = e.get("label") or ""
        parts.append(f"{protocol_name}: {label} {shown}".rstrip())
    return "; ".join(parts)


def _endpoint(av: dict[str, Any], col_token: str) -> tuple[Any, str | None]:
    """The value and qualifier the grid shows for this column.

    An intercept column (``drc:<rd>:<kind>:<level>``) reads the cell's selected
    aggregate for that intercept — what the grid renders under every selection
    rule — never the representative curve's own intercept. Any other column
    reads the cell value.
    """
    parts = col_token.split(":")
    if col_token.startswith("drc:") and len(parts) >= 4:
        target = (parts[2], float(parts[3]))
        for agg in av.get("intercept_aggregates") or []:
            spec = agg.get("spec") or {}
            if (spec.get("kind"), spec.get("level")) == target:
                return agg.get("selected_value"), agg.get("selected_qualifier")
        return None, None
    return av.get("value"), av.get("qualifier")


def _display(value: Any, qualifier: str | None) -> Any:
    """ND for no reportable value, ``>100`` / ``<0.1`` for a bound (numeric in a
    text wrapper so Excel filters still read "compound > X"), the number
    otherwise, None for no data. Run counts are not folded in, so Excel sorts
    and filters the column as numbers."""
    if qualifier == "nd":
        return "ND"
    if value is None:
        return None
    if qualifier in (">", "<"):
        return f"{qualifier}{value}"
    return value


def _qualifier_text(value: Any, qualifier: str | None) -> str:
    if qualifier == "nd" or (value is None and qualifier):
        return "ND"
    return qualifier if qualifier in (">", "<") else "="


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_uuid(value: Any) -> uuid.UUID | None:
    """Parse a string, UUID, or None to ``uuid.UUID | None``."""
    if value is None:
        return None
    return uuid.UUID(str(value))


class ExportAuth:
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
    def org_id(self) -> uuid.UUID | None:
        return None

    @property
    def org_slug(self) -> str | None:
        return None

    @property
    def name(self) -> str:
        return ""  # exports have no display identity

    @property
    def email(self) -> str:
        return ""  # exports have no display identity

    @property
    def is_admin(self) -> bool:
        return False

    def has_role(self, minimum_role: str) -> bool:
        _order = {"viewer": 0, "editor": 1, "admin": 2}
        return _order.get(self.workspace_role, 0) >= _order.get(minimum_role, 0)

    async def check_action(self, action: str) -> bool:
        return False  # exports never check fine-grained actions
