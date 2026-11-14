"""SearchColumnPlanner — the one place that decides which runs feed each search column.

A search asks for columns by token (``drc:<readout_def>``, ``rd:<protocol>:<readout_def>``
with an optional normalization, ``any``). Each column belongs to one protocol, and that
protocol's activity criterion (if the search has one) supplies its run filter and its
optional split. The plan records, per column, the protocol, the run scope and the groups
the column is cut into; values, sorting, export and SAR all read the same plan.

A split protocol's groups are the same for every page of a search: run splits are the
hand-picked runs; condition splits are the condition's values among the protocol's
non-rejected in-scope runs that measured at least one compound in the whole result set.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from cellar.domain.research_organization.criteria_walker import walk_criteria
from cellar.domain.screening_assay.activity_types import RunHeader
from cellar.domain.screening_assay.column_split import ColumnSplit
from cellar.domain.screening_assay.repository import ProtocolRepository, RunRepository
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.units import KNOWN_UNITS, canonical_unit, comparable_magnitude

NOT_RECORDED = "Not recorded"
ANY_COLUMN = "any"  # the cross-protocol "Active in" column


@dataclass(frozen=True)
class ColumnGroup:
    """One side-by-side group of a split protocol (or the single implicit group)."""

    key: str  # "" unsplit | "run:<uuid>" | "cond:<value>" | "cond:" (not recorded)
    label: str
    run_ids: frozenset[uuid.UUID] | None  # None: no restriction beyond the run scope
    run_count: int
    flags: tuple[str, ...] = ()  # "rejected" / "deleted" for hand-picked runs

    @classmethod
    def unsplit(cls) -> ColumnGroup:
        return cls(key="", label="", run_ids=None, run_count=0)


@dataclass(frozen=True)
class PlannedColumn:
    token: str
    kind: Literal["drc", "rd"]
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    normalization: str | None
    run_scope: RunScope
    groups: tuple[ColumnGroup, ...]

    def key(self, group: ColumnGroup) -> str:
        """The activity-data key of this column's cells in ``group``."""
        return self.token if not group.key else f"{self.token}@{group.key}"


@dataclass(frozen=True)
class ProtocolGroups:
    split: ColumnSplit
    groups: tuple[ColumnGroup, ...]


@dataclass(frozen=True)
class ColumnPlan:
    columns: tuple[PlannedColumn, ...]
    protocol_groups: dict[uuid.UUID, ProtocolGroups]  # split protocols only
    want_any: bool


@dataclass(frozen=True)
class _Token:
    token: str
    kind: Literal["drc", "rd"]
    readout_definition_id: uuid.UUID
    protocol_id: uuid.UUID | None
    normalization: str | None


class SearchColumnPlanner:
    def __init__(self, protocol_repo: ProtocolRepository, run_repo: RunRepository) -> None:
        self._protocols = protocol_repo
        self._runs = run_repo

    async def plan(
        self,
        workspace_id: uuid.UUID,
        tokens: list[str],
        *,
        criteria: list[dict[str, Any]],
        matching_ids: Callable[[], Awaitable[list[uuid.UUID]]],
    ) -> ColumnPlan:
        """Plan the columns of a search from its tokens and activity criteria.

        ``matching_ids`` returns every molecule id the search matches; it is
        awaited at most once, and only when some protocol splits by condition.
        Raises ``ValidationError`` for a split the criterion can't support.
        """
        parsed, want_any = await self._parse(workspace_id, tokens)
        settings, conflicts = _criterion_settings(criteria)
        if conflicts & {t.protocol_id for t in parsed}:
            raise ValidationError(
                "This protocol already has a different run filter or split in this search"
            )

        cached: list[uuid.UUID] | None = None

        async def ids_once() -> list[uuid.UUID]:
            nonlocal cached
            if cached is None:
                cached = await matching_ids()
            return cached

        split_ids = [pid for pid, (_, split) in settings.items() if split.is_split()]
        definitions = {
            p.id: p.condition_definitions
            for p in (
                await self._protocols.find_by_ids(workspace_id, split_ids) if split_ids else []
            )
        }
        protocol_groups: dict[uuid.UUID, ProtocolGroups] = {}
        for pid in split_ids:
            scope, split = settings[pid]
            if split.by == "run":
                groups = await self._run_groups(workspace_id, scope)
            else:
                groups = await self._condition_groups(
                    workspace_id, pid, scope, split, definitions.get(pid, []), ids_once
                )
            protocol_groups[pid] = ProtocolGroups(split=split, groups=groups)

        columns: list[PlannedColumn] = []
        for t in parsed:
            assert t.protocol_id is not None
            scope, _ = settings.get(t.protocol_id, (RunScope.all(), ColumnSplit()))
            split_groups = protocol_groups.get(t.protocol_id)
            columns.append(
                _column(
                    t,
                    scope,
                    split_groups.groups if split_groups else (ColumnGroup.unsplit(),),
                )
            )
        return ColumnPlan(tuple(columns), protocol_groups, want_any)

    async def plan_from_scopes(
        self, workspace_id: uuid.UUID, tokens: list[str], scopes: dict[str, RunScope]
    ) -> ColumnPlan:
        """Plan unsplit columns with per-token scopes (the SAR colour channels)."""
        parsed, want_any = await self._parse(workspace_id, tokens)
        columns = tuple(
            _column(t, scopes.get(t.token, RunScope.all()), (ColumnGroup.unsplit(),))
            for t in parsed
        )
        return ColumnPlan(columns, {}, want_any)

    # -- internals ----------------------------------------------------------

    async def _parse(
        self, workspace_id: uuid.UUID, tokens: list[str]
    ) -> tuple[list[_Token], bool]:
        parsed: list[_Token] = []
        want_any = False
        for column in tokens:
            if column == ANY_COLUMN:
                want_any = True
                continue
            parsed.append(_parse_token(column))
        unknown = [t.readout_definition_id for t in parsed if t.protocol_id is None]
        owners = (
            await self._protocols.find_ids_by_readout_definition_ids(workspace_id, unknown)
            if unknown
            else {}
        )
        resolved: list[_Token] = []
        for t in parsed:
            pid = t.protocol_id or owners.get(t.readout_definition_id)
            if pid is None:
                continue  # a readout of another workspace, or deleted: no column
            resolved.append(_Token(t.token, t.kind, t.readout_definition_id, pid, t.normalization))
        return resolved, want_any

    async def _run_groups(
        self, workspace_id: uuid.UUID, scope: RunScope
    ) -> tuple[ColumnGroup, ...]:
        picked = list(scope.explicit_run_ids)
        headers = await self._runs.find_headers(workspace_id, picked)
        present = sorted(
            (headers[i] for i in picked if i in headers),
            key=lambda h: (h.run_date is None, h.run_date, h.created_at),
        )
        dates = [h.run_date for h in present]
        groups = [
            ColumnGroup(
                key=f"run:{h.id}",
                label=_run_label(h, shared_date=dates.count(h.run_date) > 1),
                run_ids=frozenset({h.id}),
                run_count=1,
                flags=("rejected",) if h.status == "rejected" else (),
            )
            for h in present
        ]
        groups += [
            ColumnGroup(
                key=f"run:{i}",
                label="Run unavailable",
                run_ids=frozenset({i}),
                run_count=1,
                flags=("deleted",),
            )
            for i in picked
            if i not in headers
        ]
        return tuple(groups)

    async def _condition_groups(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        scope: RunScope,
        split: ColumnSplit,
        definitions: list[Any],
        matching_ids: Callable[[], Awaitable[list[uuid.UUID]]],
    ) -> tuple[ColumnGroup, ...]:
        definition = next((d for d in definitions if d.name == split.condition), None)
        if definition is None:
            raise ValidationError(f"Condition '{split.condition}' is not defined on this protocol")
        headers = await self._runs.find_runs_measuring(
            workspace_id, protocol_id, await matching_ids(), run_scope=scope
        )
        buckets: dict[str, tuple[tuple[Any, ...], str, set[uuid.UUID]]] = {}
        for h in headers:
            sort_key, label = _condition_value(
                (h.conditions or {}).get(definition.name), definition
            )
            entry = buckets.setdefault(label, (sort_key, label, set()))
            entry[2].add(h.id)
        return tuple(
            ColumnGroup(
                key="cond:" if label == NOT_RECORDED else f"cond:{label}",
                label=label,
                run_ids=frozenset(ids),
                run_count=len(ids),
            )
            for _, label, ids in sorted(buckets.values(), key=lambda b: b[0])
        )


# -- helpers ----------------------------------------------------------------

_NUMBER_AND_UNIT = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*$")


def _parse_token(token: str) -> _Token:
    parts = token.split(":")
    try:
        if parts[0] == "drc" and len(parts) == 2:
            return _Token(token, "drc", uuid.UUID(parts[1]), None, None)
        if parts[0] == "rd" and len(parts) == 2:
            return _Token(token, "rd", uuid.UUID(parts[1]), None, None)
        if parts[0] == "rd" and len(parts) in (3, 4):
            norm = parts[3] or None if len(parts) == 4 else None
            return _Token(token, "rd", uuid.UUID(parts[2]), uuid.UUID(parts[1]), norm)
    except ValueError as e:
        raise ValidationError(f"Unknown column: {token!r}") from e
    raise ValidationError(f"Unknown column: {token!r}")


def _column(t: _Token, scope: RunScope, groups: tuple[ColumnGroup, ...]) -> PlannedColumn:
    assert t.protocol_id is not None
    return PlannedColumn(
        token=t.token,
        kind=t.kind,
        protocol_id=t.protocol_id,
        readout_definition_id=t.readout_definition_id,
        normalization=t.normalization,
        run_scope=scope,
        groups=groups,
    )


def _criterion_settings(
    criteria: list[dict[str, Any]],
) -> tuple[dict[uuid.UUID, tuple[RunScope, ColumnSplit]], set[uuid.UUID]]:
    """Each protocol's run scope and split, from its activity criteria, and the
    protocols whose criteria disagree. Disagreement only matters for a protocol
    with columns: there is then no single answer to "which runs feed them".
    """
    seen: dict[uuid.UUID, tuple[Any, Any, RunScope, ColumnSplit]] = {}
    conflicts: set[uuid.UUID] = set()

    def visit(c: dict[str, Any]) -> None:
        if c.get("type") != "activity" or not c.get("protocol_id"):
            return
        pid = uuid.UUID(str(c["protocol_id"]))
        raw_scope, raw_split = c.get("run_scope"), c.get("split")
        scope = RunScope.from_wire(raw_scope)
        split = ColumnSplit.from_wire(raw_split)
        if pid in seen:
            _, _, prev_scope, prev_split = seen[pid]
            if (prev_scope, prev_split) != (scope, split):
                conflicts.add(pid)
            return
        if split.by == "run" and not scope.explicit_run_ids:
            raise ValidationError("Splitting by run needs the runs you pick (Specific run)")
        if split.by == "condition" and scope.protocol_latest:
            raise ValidationError(
                "Latest run picks a single run, so it can't be split by condition"
            )
        seen[pid] = (raw_scope, raw_split, scope, split)

    walk_criteria(criteria, visit)
    return {pid: (scope, split) for pid, (_, _, scope, split) in seen.items()}, conflicts


def _run_label(h: RunHeader, *, shared_date: bool) -> str:
    base = h.run_date.isoformat() if h.run_date else "Undated run"
    if not shared_date:
        return base
    tag = h.plate_barcodes[0] if h.plate_barcodes else str(h.id)[:8]
    return f"{base} · {tag}"


def _condition_value(raw: Any, definition: Any) -> tuple[tuple[Any, ...], str]:
    """(sort key, label) for one run's value of the split condition.

    Numbers group by value and canonical unit, so "10 uM", "10 µM" and
    "10.0uM" are one group; pick-list values keep the pick list's order; text
    sorts alphabetically; a blank or missing value is "Not recorded", last.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return (3,), NOT_RECORDED
    picks = list(definition.pick_list_values or [])
    if text in picks:
        return (1, picks.index(text)), text
    if (m := _NUMBER_AND_UNIT.match(text)) and _is_unit(m.group(2), definition.unit):
        number = float(m.group(1))
        unit = canonical_unit(m.group(2)) or canonical_unit(definition.unit) or ""
        label = f"{_plain_number(m.group(1))} {unit}".strip()
        return (0, *comparable_magnitude(number, unit)), label
    return (2, text.casefold()), text


def _is_unit(text: str, definition_unit: str | None) -> bool:
    """Empty (a bare number), a unit the app knows, or the condition's own unit.
    "1:100", "10-15 min" and dates are text, not a number with a unit."""
    if not text:
        return True
    canonical = canonical_unit(text)
    return canonical in KNOWN_UNITS or (
        canonical is not None and canonical == canonical_unit(definition_unit)
    )


def _plain_number(text: str) -> str:
    """The number as written, without trailing zeros: "10.0" → "10", "1234567" kept whole."""
    value = Decimal(text)
    if value == value.to_integral_value():
        return str(value.quantize(Decimal(1)))
    return format(value.normalize(), "f")
