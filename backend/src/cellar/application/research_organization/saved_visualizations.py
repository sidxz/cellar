"""Saved visualizations — create, open, list, change and delete named workbench views.

A view's ``source`` is stored in the wire shape of the dataset request's source: a run
(``{kind: "run", run_id}``) or a protocol (``{kind: "protocol", protocol_id, run_ids}``, plus the
protocols compared beside it in ``compare``, each ``{protocol_id, run_ids}``). Saving checks
every id strictly; opening keeps what still exists and says, in words, what was left out.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.research_organization.project_links import ProjectAccess
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.visualization.dataset_reader import VisualizationDatasetReader
from cellar.domain.research_organization.enums import SearchVisibility
from cellar.domain.research_organization.repository import (
    ProjectMemberRepository,
    SavedVisualizationRepository,
)
from cellar.domain.research_organization.saved_visualization import SavedVisualization
from cellar.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    StaleEditError,
    ValidationError,
)

OWNER_RULE = "Only the owner or a workspace admin can change this view."


# --- sources


def _ids(values: Any) -> list[uuid.UUID] | None:
    return None if values is None else list(dict.fromkeys(uuid.UUID(str(v)) for v in values))


def _protocol_parts(source: dict[str, Any]) -> list[dict[str, Any]]:
    """The source's protocol, then each compared protocol."""
    return [source, *(source.get("compare") or [])]


async def check_saved_source(
    reader: VisualizationDatasetReader, workspace_id: uuid.UUID, source: dict[str, Any]
) -> list[uuid.UUID] | NotFoundError:
    """The protocols ``source`` reads, or NotFound for any protocol or run outside the
    workspace (or a run of another protocol)."""
    if source["kind"] == "run":
        run_id = uuid.UUID(str(source["run_id"]))
        found = await reader.runs_by_ids(workspace_id, [run_id])
        return [found[0].protocol_id] if found else NotFoundError("Run", str(run_id))
    protocol_ids: list[uuid.UUID] = []
    for part in _protocol_parts(source):
        protocol_id = uuid.UUID(str(part["protocol_id"]))
        runs = await reader.runs_for_protocol(workspace_id, protocol_id)
        if runs is None:
            return NotFoundError("Protocol", str(protocol_id))
        known = {r.id for r in runs}
        missing = [r for r in _ids(part.get("run_ids")) or [] if r not in known]
        if missing:
            return NotFoundError("Run", str(missing[0]))
        protocol_ids.append(protocol_id)
    return list(dict.fromkeys(protocol_ids))


def _runs_left_out(saved: int, kept: int, whose: str) -> str | None:
    gone = saved - kept
    if gone == 0:
        return None
    if kept == 0:
        every = "showing every current run of the protocol."
        if saved == 1:
            return f"The run {whose} was saved with no longer exists; {every}"
        return f"None of the {saved} runs {whose} was saved with exist any more; {every}"
    exist, were = ("exists", "it was") if gone == 1 else ("exist", "they were")
    return f"{gone} of the {saved} runs {whose} was saved with no longer {exist}; {were} left out."


async def _live_part(
    reader: VisualizationDatasetReader,
    workspace_id: uuid.UUID,
    part: dict[str, Any],
    whose: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """``part`` with its deleted runs dropped (none left → every current run), or None when
    its protocol is gone; plus the line saying what was dropped."""
    runs = await reader.runs_for_protocol(workspace_id, uuid.UUID(str(part["protocol_id"])))
    if runs is None:
        return None, None
    saved = _ids(part.get("run_ids"))
    if saved is None:
        return part, None
    known = {r.id for r in runs}
    kept = [r for r in saved if r in known]
    line = _runs_left_out(len(saved), len(kept), whose)
    if line is None:
        return part, None
    return {**part, "run_ids": [str(r) for r in kept] if kept else None}, line


async def resolve_saved_source(
    reader: VisualizationDatasetReader, workspace_id: uuid.UUID, source: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    """What still exists of ``source`` (None when its run or protocol is gone) and a
    plain-language line for everything left out."""
    if source["kind"] == "run":
        if await reader.runs_by_ids(workspace_id, [uuid.UUID(str(source["run_id"]))]):
            return source, []
        return None, ["The run this view was built on no longer exists."]

    main, line = await _live_part(reader, workspace_id, source, "this view")
    if main is None:
        return None, ["The protocol this view was built on no longer exists."]
    lines = [line] if line else []
    if "compare" not in source:
        return main, lines

    compare: list[dict[str, Any]] = []
    gone = 0
    for part in source["compare"] or []:
        live, line = await _live_part(reader, workspace_id, part, "an added protocol")
        if live is None:
            gone += 1
            continue
        compare.append(live)
        lines += [line] if line else []
    if gone:
        lines.append(
            "1 added protocol no longer exists; its columns were left out."
            if gone == 1
            else f"{gone} added protocols no longer exist; their columns were left out."
        )
    return {**main, "compare": compare}, lines


# --- use cases


class _SavedVisualizationUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: SavedVisualizationRepository,
        members: ProjectMemberRepository,
        access: ProjectAccess,
        reader: VisualizationDatasetReader,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._members = members
        self._access = access
        self._reader = reader
        self._dispatcher = dispatcher

    async def _find_visible(
        self, workspace_id: uuid.UUID, view_id: uuid.UUID, auth: AuthContext
    ) -> SavedVisualization | NotFoundError:
        """Run inside the unit of work. Views the caller may not see are simply not found."""
        view = await self._repo.find_by_id_in_workspace(workspace_id, view_id)
        if view is not None:
            is_member = (
                view.project_id is not None
                and await self._members.get_role(workspace_id, view.project_id, auth.user_id)
                is not None
            )
            if view.is_visible_to(auth.user_id, is_admin=auth.is_admin, is_member=is_member):
                return view
        return NotFoundError("SavedVisualization", str(view_id))

    async def _find_editable(
        self, workspace_id: uuid.UUID, view_id: uuid.UUID, auth: AuthContext
    ) -> SavedVisualization | DomainError:
        view = await self._find_visible(workspace_id, view_id, auth)
        if isinstance(view, NotFoundError):
            return view
        if not view.can_be_edited_by(auth.user_id, is_admin=auth.is_admin):
            return AuthorizationError(OWNER_RULE)
        return view


@dataclass(frozen=True, kw_only=True)
class CreateSavedVisualizationCommand(Command):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    source: dict[str, Any]
    level: str
    config: dict[str, Any]
    visibility: SearchVisibility = SearchVisibility.PRIVATE
    project_id: uuid.UUID | None = None
    created_by: uuid.UUID


class CreateSavedVisualization(_SavedVisualizationUseCase):
    async def __call__(
        self, input: CreateSavedVisualizationCommand, auth: AuthContext | None = None
    ) -> Result[SavedVisualization, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        protocol_ids = await check_saved_source(self._reader, input.workspace_id, input.source)
        if isinstance(protocol_ids, NotFoundError):
            return Failure(protocol_ids)
        async with self._uow:
            if input.visibility == SearchVisibility.PROJECT and input.project_id is not None:
                denied = await self._access.check_editable(
                    input.workspace_id, [input.project_id], auth
                )
                if denied is not None:
                    return Failure(denied)
            try:
                view = SavedVisualization.create(
                    workspace_id=input.workspace_id,
                    name=input.name,
                    description=input.description,
                    source=input.source,
                    protocol_ids=protocol_ids,
                    level=input.level,
                    config=input.config,
                    visibility=input.visibility,
                    project_id=input.project_id,
                    created_by=input.created_by,
                )
            except ValidationError as exc:
                return Failure(exc)
            await self._repo.save(view)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(view)


@dataclass(frozen=True, kw_only=True)
class UpdateSavedVisualizationCommand(Command):
    """None (UNSET for the nullable description and project) leaves a field as it is."""

    workspace_id: uuid.UUID
    view_id: uuid.UUID
    expected_version: int
    name: str | None = None
    description: str | object | None = UNSET
    source: dict[str, Any] | None = None
    level: str | None = None
    config: dict[str, Any] | None = None
    visibility: SearchVisibility | None = None
    project_id: uuid.UUID | object | None = UNSET


def _given(value: object) -> Any:
    """UNSET as the domain's "leave as is" (``...``)."""
    return ... if value is UNSET else value


class UpdateSavedVisualization(_SavedVisualizationUseCase):
    async def __call__(
        self, input: UpdateSavedVisualizationCommand, auth: AuthContext | None = None
    ) -> Result[SavedVisualization, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None

        async with self._uow:
            view = await self._find_editable(input.workspace_id, input.view_id, auth)
            if isinstance(view, DomainError):
                return Failure(view)
            protocol_ids: list[uuid.UUID] | None = None
            if input.source is not None:
                checked = await check_saved_source(self._reader, input.workspace_id, input.source)
                if isinstance(checked, NotFoundError):
                    return Failure(checked)
                protocol_ids = checked
            visibility = input.visibility or view.visibility
            project_id = view.project_id if input.project_id is UNSET else input.project_id
            if (
                visibility == SearchVisibility.PROJECT
                and isinstance(project_id, uuid.UUID)
                and (visibility, project_id) != (view.visibility, view.project_id)
            ):
                denied = await self._access.check_editable(input.workspace_id, [project_id], auth)
                if denied is not None:
                    return Failure(denied)
            try:
                changed = view.update(
                    expected_version=input.expected_version,
                    name=input.name,
                    description=_given(input.description),
                    source=input.source,
                    protocol_ids=protocol_ids,
                    level=input.level,
                    config=input.config,
                    visibility=input.visibility,
                    project_id=_given(input.project_id),
                )
            except (StaleEditError, ValidationError) as exc:
                return Failure(exc)
            if changed:  # saving bumps the version: another tab's edit would turn stale
                await self._repo.save(view)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(view)


@dataclass(frozen=True, kw_only=True)
class DeleteSavedVisualizationCommand(Command):
    workspace_id: uuid.UUID
    view_id: uuid.UUID


class DeleteSavedVisualization(_SavedVisualizationUseCase):
    async def __call__(
        self, input: DeleteSavedVisualizationCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None

        async with self._uow:
            view = await self._find_editable(input.workspace_id, input.view_id, auth)
            if isinstance(view, DomainError):
                return Failure(view)
            view.mark_deleted()
            await self._repo.delete(input.workspace_id, view.id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


@dataclass(frozen=True)
class OpenedView:
    """A view with what still exists of its source (None: its run or protocol is gone) and
    a line for everything left out."""

    view: SavedVisualization
    source: dict[str, Any] | None
    unresolved: list[str]


@dataclass(frozen=True, kw_only=True)
class GetSavedVisualizationQuery(Query):
    workspace_id: uuid.UUID
    view_id: uuid.UUID


class GetSavedVisualization(_SavedVisualizationUseCase):
    async def __call__(
        self, input: GetSavedVisualizationQuery, auth: AuthContext | None = None
    ) -> Result[OpenedView, DomainError]:
        require_authenticated(auth)
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None

        async with self._uow:
            view = await self._find_visible(input.workspace_id, input.view_id, auth)
        if isinstance(view, NotFoundError):
            return Failure(view)
        source, unresolved = await resolve_saved_source(
            self._reader, input.workspace_id, view.source
        )
        return Success(OpenedView(view, source, unresolved))


@dataclass(frozen=True, kw_only=True)
class ListSavedVisualizationsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID | None = None


class ListSavedVisualizations(_SavedVisualizationUseCase):
    async def __call__(
        self, input: ListSavedVisualizationsQuery, auth: AuthContext | None = None
    ) -> Result[list[SavedVisualization], DomainError]:
        require_authenticated(auth)
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None

        async with self._uow:
            project_ids = (
                None
                if auth.is_admin
                else await self._members.find_accessible_project_ids(
                    input.workspace_id, auth.user_id
                )
            )
            views = await self._repo.find_visible(
                input.workspace_id,
                auth.user_id,
                project_ids=project_ids,
                protocol_id=input.protocol_id,
            )
        return Success(views)
