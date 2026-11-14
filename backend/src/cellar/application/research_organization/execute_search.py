"""ExecuteSearch -- run a compound query (inline or from SavedSearch)."""

from __future__ import annotations

import contextlib
import json
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.chemical_registration.molecule_reader import MoleculeReader
from cellar.application.research_organization.search_reference_resolution import (
    SearchReferenceResolver,
)
from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.application.screening.search_column_plan import (
    ANY_COLUMN,
    ColumnPlan,
    PlannedColumn,
    ProtocolGroups,
)
from cellar.application.shared.pagination import EnrichedPageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.research_organization.criteria_walker import (
    any_match,
    walk_criteria,
)
from cellar.domain.research_organization.repository import SavedSearchRepository
from cellar.domain.screening_assay.activity_types import ActivityValue, AnyProtocolActivity
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.units import canonical_unit

# Molecules enriched per round-trip when ranking a whole result set by an
# activity column.
_RANK_CHUNK = 5_000
_RANKED_CURSOR = "r1"
_STALE_CURSOR = "Results changed — run the search again"


@dataclass(frozen=True, kw_only=True)
class ExecuteSearchQuery(Query):
    workspace_id: uuid.UUID
    saved_search_id: uuid.UUID | None = None
    query: dict[str, Any] | None = None
    protocol_columns: list[str] | None = None
    aggregation: SelectionRule = SelectionRule.LATEST_RUN
    # Opaque: a molecule id for id-ordered pages, "r1:<index>:<id>" for ranked ones.
    cursor: str | None = None
    limit: int = 50
    project_ids: list[uuid.UUID] | None = None
    sort_by: str | None = None
    sort_dir: str | None = None


class ExecuteSearch:
    """Execute a compound search -- either by saved_search_id or inline query dict.

    Unsorted searches page by molecule id. A sort (molecule column, similarity,
    or any activity column) or a similarity criterion ranks the WHOLE result
    set and pages through that ranking, so the top row is the top of every
    match, not of the rows loaded so far. Activity columns rank by the same
    values their cells show: one column plan feeds both.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_reader: MoleculeReader,
        saved_search_repo: SavedSearchRepository,
        activity_service: MoleculeActivityService | None = None,
        reference_resolver: SearchReferenceResolver | None = None,
    ) -> None:
        self._uow = uow
        self._mol_reader = molecule_reader
        self._ss_repo = saved_search_repo
        self._activity_service = activity_service
        self._reference_resolver = reference_resolver
        # Ranked orders by request (everything but cursor and page size). One
        # instance serves one HTTP request, or one export walking its pages —
        # which then ranks once instead of once per batch.
        self._orders: dict[str, list[tuple[uuid.UUID, float | None]]] = {}

    async def __call__(
        self, input: ExecuteSearchQuery, auth: AuthContext | None = None
    ) -> Result[EnrichedPageResult[Molecule], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        if input.saved_search_id is None and input.query is None:
            return Failure(ValidationError("Provide either saved_search_id or query."))

        async with self._uow:
            ss = None
            if input.saved_search_id is not None:
                ss = await self._ss_repo.find_by_id_in_workspace(
                    input.workspace_id, input.saved_search_id
                )
                if ss is None:
                    return Failure(NotFoundError("SavedSearch", str(input.saved_search_id)))
                query_dict = ss.query
            else:
                query_dict = input.query  # type: ignore[assignment]

            try:
                if self._reference_resolver is not None:
                    query_dict = await self._reference_resolver(input.workspace_id, query_dict)
                page = await self._page(input, query_dict)
            except ValueError as e:
                return Failure(ValidationError(str(e)))
            except ValidationError as e:
                return Failure(e)

            # Saved-search write-back: record run metadata on first page only.
            # Pagination requests skip this so we don't re-stamp last_run_at on
            # every cursor scroll.
            if ss is not None and input.cursor is None:
                ss.record_execution(
                    result_count=page.total_count
                    if page.total_count is not None
                    else len(page.items)
                )
                await self._ss_repo.save(ss)

            return Success(page)

    async def _page(
        self, input: ExecuteSearchQuery, query_dict: dict[str, Any]
    ) -> EnrichedPageResult[Molecule]:
        ws = input.workspace_id
        criteria = query_dict.get("criteria", [])
        any_groups = _collect_any_readout_groups(criteria) or None
        all_ids_cache: list[tuple[uuid.UUID, float | None]] | None = None

        async def all_matches() -> list[tuple[uuid.UUID, float | None]]:
            """Every match, most-similar first when the query has a similarity
            criterion, else by id — fetched once per request."""
            nonlocal all_ids_cache
            if all_ids_cache is None:
                all_ids_cache = await self._mol_reader.ranked_ids_by_query(
                    ws, query_dict, project_ids=input.project_ids
                )
            return all_ids_cache

        async def matching_ids() -> list[uuid.UUID]:
            return [i for i, _ in await all_matches()]

        sort_target = _parse_activity_sort(input.sort_by)
        tokens = list(input.protocol_columns or [])
        if sort_target is not None and sort_target.token not in tokens:
            tokens.append(sort_target.token)
        plan: ColumnPlan | None = None
        if tokens and self._activity_service is not None:
            plan = await self._activity_service.planner.plan(
                ws, tokens, criteria=criteria, matching_ids=matching_ids
            )

        similarity_scores: dict[uuid.UUID, float] | None = None
        total_count: int | None = None
        if input.sort_by is None and not _query_has_similarity(criteria):
            fetched = await self._mol_reader.search_by_query(
                ws,
                query_dict,
                cursor_id=_id_cursor(input.cursor),
                limit=input.limit + 1,
                project_ids=input.project_ids,
            )
            molecules = list(fetched[: input.limit])
            next_cursor = str(molecules[-1].id) if len(fetched) > input.limit else None
            if input.cursor is None:
                # Non-critical — skip count on composer errors
                with contextlib.suppress(ValueError):
                    total_count = await self._mol_reader.count_by_query(
                        ws, query_dict, project_ids=input.project_ids
                    )
        else:
            key = _order_key(input, query_dict)
            order = self._orders.get(key)
            if order is None:
                if sort_target is not None:
                    if plan is None:
                        raise ValidationError(f"Unknown sort column: {input.sort_by!r}")
                    order = await self._activity_order(
                        input, plan, sort_target, await all_matches(), any_groups
                    )
                elif input.sort_by is None:
                    order = await all_matches()
                else:
                    order = await self._mol_reader.ranked_ids_by_query(
                        ws,
                        query_dict,
                        project_ids=input.project_ids,
                        sort_by=input.sort_by,
                        sort_dir=input.sort_dir,
                    )
                self._orders[key] = order
            start = _resume(order, input.cursor)
            page = order[start : start + input.limit]
            more = start + input.limit < len(order)
            next_cursor = (
                f"{_RANKED_CURSOR}:{start + len(page) - 1}:{page[-1][0]}"
                if more and page
                else None
            )
            molecules = await self._mol_reader.find_by_ids_ordered(ws, [i for i, _ in page])
            similarity_scores = {i: s for i, s in page if s is not None} or None
            if input.cursor is None:
                total_count = len(order)

        activity_data = None
        if plan is not None and input.protocol_columns and molecules:
            assert self._activity_service is not None
            raw = await self._activity_service.enrich_plan(
                ws,
                [m.id for m in molecules],
                plan,
                selection_rule=input.aggregation,
                qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
                any_readout_groups=any_groups,
            )
            activity_data = {
                str(k): {ck: asdict(v) for ck, v in cv.items()} for k, cv in raw.items()
            }

        return EnrichedPageResult(
            items=molecules,
            next_cursor=next_cursor,
            activity_data=activity_data,
            total_count=total_count,
            similarity_scores=similarity_scores,
            column_groups=_column_groups(plan.protocol_groups) if plan else None,
        )

    async def _activity_order(
        self,
        input: ExecuteSearchQuery,
        plan: ColumnPlan,
        target: _ActivitySort,
        matches: list[tuple[uuid.UUID, float | None]],
        any_groups: list[tuple[str, str | None]] | None,
    ) -> list[tuple[uuid.UUID, float | None]]:
        """Every match ranked by an activity column's cell values (spec §5.4)."""
        assert self._activity_service is not None
        sort_plan, key = _sort_plan(plan, target)
        # ponytail: re-ranks the whole result set on every page; for a 100k-
        # compound HTS column expect ~1 s per page. Upgrade: cache the ranked
        # id list in Valkey keyed by (query hash, plan, sort, rule).
        cells: dict[uuid.UUID, ActivityValue | AnyProtocolActivity | None] = {}
        ids = [i for i, _ in matches]
        for at in range(0, len(ids), _RANK_CHUNK):
            chunk = ids[at : at + _RANK_CHUNK]
            found = await self._activity_service.enrich_plan(
                input.workspace_id,
                chunk,
                sort_plan,
                selection_rule=input.aggregation,
                qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
                any_readout_groups=any_groups,
                lean=True,
            )
            for mol_id in chunk:
                cells[mol_id] = found.get(mol_id, {}).get(key)
        descending = input.sort_dir == "desc"
        return sorted(
            matches,
            key=lambda m: _rank_key(cells.get(m[0]), target.intercept, descending, m[0]),
        )


# ---------------------------------------------------------------------------
# Sorting and paging helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ActivitySort:
    token: str  # the planned column's token
    group_key: str  # "" for an unsplit column
    intercept: tuple[str, float] | None  # (kind, level) for an intercept column


def _parse_activity_sort(sort_by: str | None) -> _ActivitySort | None:
    """``drc:<rd>[:<kind>:<level>][@<group>]``, ``rd:…[@<group>]`` or ``any``;
    None for a molecule-column or similarity sort."""
    if sort_by is None:
        return None
    base, _, group = sort_by.partition("@")
    if base == ANY_COLUMN:
        return _ActivitySort(ANY_COLUMN, "", None)
    if base.startswith("rd:"):
        return _ActivitySort(base, group, None)
    if base.startswith("drc:"):
        parts = base.split(":")
        if len(parts) == 2:
            return _ActivitySort(base, group, None)
        if len(parts) == 4:
            try:
                level = float(parts[3])
            except ValueError as e:
                raise ValidationError(f"Unknown sort column: {sort_by!r}") from e
            return _ActivitySort(f"drc:{parts[1]}", group, (parts[2], level))
        raise ValidationError(f"Unknown sort column: {sort_by!r}")
    return None


def _sort_plan(plan: ColumnPlan, target: _ActivitySort) -> tuple[ColumnPlan, str]:
    """A plan holding only the sorted column's group, and that cell's key."""
    if target.token == ANY_COLUMN:
        return ColumnPlan((), {}, want_any=True), ANY_COLUMN
    column: PlannedColumn | None = next((c for c in plan.columns if c.token == target.token), None)
    group = next((g for g in column.groups if g.key == target.group_key), None) if column else None
    if column is None or group is None:
        raise ValidationError("Unknown sort column for this search")
    return ColumnPlan((replace(column, groups=(group,)),), {}, want_any=False), column.key(group)


_QUALIFIER_ORDER = {"<": 0, "=": 1, None: 1, ">": 2}


def _rank_key(
    cell: ActivityValue | AnyProtocolActivity | None,
    intercept: tuple[str, float] | None,
    descending: bool,
    mol_id: uuid.UUID,
) -> tuple[int, float, int, str]:
    """Values first (by value, then < = >), then ND, then no data; ties by id.
    Descending reverses the value and its qualifier only."""
    value, qualifier = _cell_value(cell, intercept)
    if value is None:
        return (2 if cell is None else 1, 0.0, 0, str(mol_id))
    q = _QUALIFIER_ORDER.get(qualifier, 1)
    if descending:
        return (0, -value, -q, str(mol_id))
    return (0, value, q, str(mol_id))


def _cell_value(
    cell: ActivityValue | AnyProtocolActivity | None, intercept: tuple[str, float] | None
) -> tuple[float | None, str | None]:
    if cell is None:
        return None, None
    if isinstance(cell, AnyProtocolActivity):
        best = next((e for e in cell.entries if e.value_um is not None), None)
        return (best.value_um, None) if best else (None, None)
    if intercept is not None:
        kind, level = intercept
        agg = next(
            (
                a
                for a in cell.intercept_aggregates or []
                if a.spec.get("kind") == kind and a.spec.get("level") == level
            ),
            None,
        )
        if agg is None or agg.selected_value is None:
            return None, None
        return agg.selected_value, agg.selected_qualifier
    return cell.value, cell.qualifier


def _order_key(input: ExecuteSearchQuery, query_dict: dict[str, Any]) -> str:
    """Everything that decides a ranked order — not the cursor or page size."""
    return json.dumps(
        {
            "ws": str(input.workspace_id),
            "query": query_dict,
            "columns": input.protocol_columns,
            "aggregation": input.aggregation.value,
            "projects": sorted(str(p) for p in input.project_ids or []),
            "sort": [input.sort_by, input.sort_dir],
        },
        sort_keys=True,
        default=str,
    )


def _id_cursor(cursor: str | None) -> uuid.UUID | None:
    if cursor is None:
        return None
    try:
        return uuid.UUID(cursor)
    except ValueError as e:
        raise ValidationError(_STALE_CURSOR) from e


def _resume(order: list[tuple[uuid.UUID, float | None]], cursor: str | None) -> int:
    """Index of the first row after a ranked cursor ``r1:<index>:<id>``."""
    if cursor is None:
        return 0
    prefix, _, rest = cursor.partition(":")
    index_text, _, id_text = rest.partition(":")
    try:
        if prefix != _RANKED_CURSOR:
            raise ValueError(cursor)
        index, last = int(index_text), uuid.UUID(id_text)
    except ValueError as e:
        raise ValidationError(_STALE_CURSOR) from e
    if 0 <= index < len(order) and order[index][0] == last:
        return index + 1
    for i, (mol_id, _) in enumerate(order):
        if mol_id == last:
            return i + 1
    raise ValidationError(_STALE_CURSOR)


def _column_groups(groups: dict[uuid.UUID, ProtocolGroups]) -> dict[str, Any] | None:
    if not groups:
        return None
    return {
        str(pid): {
            "split": {"by": pg.split.by, "condition": pg.split.condition},
            "groups": [
                {
                    "key": g.key,
                    "label": g.label,
                    "run_ids": sorted(str(r) for r in g.run_ids or ()),
                    "run_count": g.run_count,
                    "flags": list(g.flags),
                }
                for g in pg.groups
            ],
        }
        for pid, pg in groups.items()
    }


# ---------------------------------------------------------------------------
# Criteria helpers
# ---------------------------------------------------------------------------


def _query_has_similarity(criteria: list[dict]) -> bool:
    """Return True if any criterion (recursively) is a similarity structure search."""
    return any_match(
        criteria,
        lambda c: (
            c.get("type") == "structure"
            and (c.get("kind") or c.get("search_type")) == "similarity"
        ),
    )


def _collect_any_readout_groups(criteria: list[dict]) -> list[tuple[str, str | None]]:
    """``(readout_name, unit)`` groups named by any-protocol activity criteria
    (``protocol_id`` None + ``readout_data`` where with ``readout_name``).
    Feeds the ``any`` column so readout entries appear only when asked for. Units by
    canonical spelling, so "uM" and "µM" are one group."""
    groups: list[tuple[str, str | None]] = []

    def _visit(c: dict) -> None:
        if c.get("type") != "activity" or c.get("protocol_id"):
            return
        where = c.get("where") if isinstance(c.get("where"), list) else []
        for w in where:
            if not isinstance(w, dict) or w.get("source") != "readout_data":
                continue
            name = w.get("readout_name")
            if isinstance(name, str) and name.strip():
                key = (name, canonical_unit(w.get("unit")))
                if key not in groups:
                    groups.append(key)

    walk_criteria(criteria, _visit)
    return groups
