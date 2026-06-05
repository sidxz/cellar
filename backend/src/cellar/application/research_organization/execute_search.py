"""ExecuteSearch -- run a compound query (inline or from SavedSearch)."""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.chemical_registration.molecule_reader import MoleculeReader
from cellar.application.screening.molecule_activity_service import MoleculeActivityService
from cellar.application.shared.pagination import EnrichedPageResult
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.research_organization.criteria_walker import (
    any_match,
    walk_criteria,
)
from cellar.domain.research_organization.repository import SavedSearchRepository
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.aggregation_types import SelectionRule
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ExecuteSearchQuery(Query):
    workspace_id: uuid.UUID
    saved_search_id: uuid.UUID | None = None
    query: dict[str, Any] | None = None
    protocol_columns: list[str] | None = None
    aggregation: SelectionRule = SelectionRule.LATEST_APPROVED_RUN
    cursor_id: uuid.UUID | None = None
    limit: int = 50
    project_ids: list[uuid.UUID] | None = None
    sort_by: str | None = None
    sort_dir: str | None = None


class ExecuteSearch:
    """Execute a compound search -- either by saved_search_id or inline query dict.

    Resolves the query dict (from SavedSearch or inline), then delegates
    the composed query execution to MoleculeRepository.search_by_query().
    Optionally enriches results with activity data for the requested protocol columns.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        molecule_reader: MoleculeReader,
        saved_search_repo: SavedSearchRepository,
        activity_service: MoleculeActivityService | None = None,
    ) -> None:
        self._uow = uow
        self._mol_reader = molecule_reader
        self._ss_repo = saved_search_repo
        self._activity_service = activity_service

    async def __call__(
        self, input: ExecuteSearchQuery, auth: AuthContext | None = None
    ) -> Result[EnrichedPageResult[Molecule], DomainError]:
        require_same_workspace(auth, input.workspace_id)
        if input.saved_search_id is None and input.query is None:
            return Failure(ValidationError("Provide either saved_search_id or query."))

        async with self._uow:
            # Resolve query dict
            if input.saved_search_id is not None:
                ss = await self._ss_repo.find_by_id_in_workspace(
                    input.workspace_id, input.saved_search_id
                )
                if ss is None:
                    return Failure(NotFoundError("SavedSearch", str(input.saved_search_id)))
                query_dict = ss.query
            else:
                query_dict = input.query  # type: ignore[assignment]

            has_similarity = _query_has_similarity(query_dict.get("criteria", []))

            # Delegate to reader — fetch limit + 1 for next_cursor detection
            fetch_limit = input.limit + 1
            try:
                raw_results = await self._mol_reader.search_by_query(
                    input.workspace_id,
                    query_dict,
                    cursor_id=input.cursor_id,
                    limit=fetch_limit,
                    project_ids=input.project_ids,
                    sort_by=input.sort_by,
                    sort_dir=input.sort_dir,
                    include_similarity_score=has_similarity,
                )
            except ValueError as e:
                return Failure(ValidationError(str(e)))

            # Unpack tuples when similarity scores are present
            similarity_scores: dict[uuid.UUID, float] | None = None
            if has_similarity:
                pairs = raw_results  # list[tuple[Molecule, float | None]]
                molecules: list[Molecule] = []
                sim_map: dict[uuid.UUID, float] = {}
                for mol, score in pairs:  # type: ignore[misc]
                    molecules.append(mol)
                    if score is not None:
                        sim_map[mol.id] = score
                similarity_scores = sim_map if sim_map else None
            else:
                molecules = raw_results  # type: ignore[assignment]

            # Total count — only on first page to avoid repeated full scans
            total_count: int | None = None
            if input.cursor_id is None:
                # Non-critical — skip count on composer errors
                with contextlib.suppress(ValueError):
                    total_count = await self._mol_reader.count_by_query(
                        input.workspace_id,
                        query_dict,
                        project_ids=input.project_ids,
                    )

            # Determine next_cursor
            next_cursor: str | None = None
            if len(molecules) > input.limit:
                molecules = molecules[: input.limit]
                if similarity_scores:
                    # Trim scores to match the trimmed molecule list
                    kept_ids = {m.id for m in molecules}
                    similarity_scores = {
                        k: v for k, v in similarity_scores.items() if k in kept_ids
                    }
                next_cursor = str(molecules[-1].id)

            # Saved-search write-back: record run metadata on first page only.
            # Pagination requests skip this so we don't re-stamp last_run_at on
            # every cursor scroll.
            if input.saved_search_id is not None and input.cursor_id is None:
                ss.record_execution(
                    result_count=total_count if total_count is not None else len(molecules)
                )
                await self._ss_repo.save(ss)

            # Enrich with activity data if requested
            activity_data = None
            if input.protocol_columns and self._activity_service and molecules:
                mol_ids = [m.id for m in molecules]
                # Per-column run scopes — pulled from each activity criterion
                # and keyed by ``drc:<rd_id>`` to feed enrich_molecules.
                drc_cols = [c for c in (input.protocol_columns or []) if c.startswith("drc:")]
                criteria = query_dict.get("criteria", []) if query_dict else []
                run_scopes = _collect_run_scopes(criteria, drc_cols)
                activity_data_raw = await self._activity_service.enrich_molecules(
                    input.workspace_id,
                    mol_ids,
                    input.protocol_columns,
                    selection_rule=input.aggregation,
                    run_scopes=run_scopes or None,
                )
                # Convert UUID keys to strings and ActivityValue to dicts for JSON
                activity_data = {
                    str(k): {ck: asdict(v) for ck, v in cv.items()}
                    for k, cv in activity_data_raw.items()
                }

            return Success(
                EnrichedPageResult(
                    items=molecules,
                    next_cursor=next_cursor,
                    activity_data=activity_data,
                    total_count=total_count,
                    similarity_scores=similarity_scores,
                )
            )


# ---------------------------------------------------------------------------
# Private helpers
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


def _collect_run_scopes(
    criteria: list[dict],
    drc_col_keys: list[str],
) -> dict[str, RunScope]:
    """Map each requested ``drc:<rd_id>`` col_key to its criterion's run_scope.

    A search has at most one activity criterion per protocol on the same
    query, and the FE explicitly lists the drc col_keys it wants in
    ``protocol_columns``. Each drc col_key corresponds to a readout-def
    on some protocol; we attach the scope from the matching activity
    criterion. Criteria without an explicit ``run_scope`` (or with
    ``mode=any``) contribute nothing and the cell falls back to
    ``RunScope.all()`` in ``enrich_molecules``.

    Pragmatic mapping: without an async DB lookup we can't pair every
    drc col_key with its owning protocol, so:
      * single activity criterion with a scope → apply uniformly to all
        requested drc col_keys (the common chemist workflow).
      * multiple criteria with scopes → the LAST one in tree-walk order
        wins (deterministic, since dict preserves insertion order). In
        practice chemists rarely mix multiple scoped activity criteria
        on the same search; the conservative narrowing is the safer
        default if they do.
    """
    scopes: dict[str, RunScope] = {}
    activity_scopes_by_protocol: dict[str, RunScope] = {}

    def _visit(c: dict) -> None:
        if c.get("type") != "activity":
            return
        proto_id = c.get("protocol_id")
        rs_raw = c.get("run_scope")
        if proto_id is None or not rs_raw:
            return
        parsed = _parse_run_scope(rs_raw)
        if parsed.is_all():
            return
        activity_scopes_by_protocol[str(proto_id)] = parsed

    walk_criteria(criteria, _visit)
    if not activity_scopes_by_protocol or not drc_col_keys:
        return {}

    if len(activity_scopes_by_protocol) == 1:
        scope = next(iter(activity_scopes_by_protocol.values()))
    else:
        # Multiple criteria with scopes — the LAST is preserved by
        # insertion order. Documented above.
        scope = next(reversed(activity_scopes_by_protocol.values()))

    for col_key in drc_col_keys:
        scopes[col_key] = scope
    return scopes


def _parse_run_scope(raw: dict[str, Any]) -> RunScope:
    """Thin alias around the domain VO's single parser.

    Kept as a module-level helper so the call site (`_collect_run_scopes`)
    reads as a verb. The actual wire-shape interpretation lives in
    ``RunScope.from_wire``.
    """
    return RunScope.from_wire(raw)
