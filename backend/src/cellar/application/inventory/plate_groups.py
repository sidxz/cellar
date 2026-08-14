"""PlateGroup use cases — open hierarchy CRUD, tree read model, plate assignment.

Visibility (spec §5): all reads/writes consume PlateVisibilityService's
excluded_org_ids. A group whose owner org is private-and-foreign 404s exactly
like a missing one; the org-scoped tree read 403s for non-members instead
(the org's existence is public via the directory — only its contents are not).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.events import PlateGroupDeleted
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.inventory.repository import (
    PlateGroupRepository,
    RegisteredPlateRepository,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Commands / Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreatePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    name: str
    created_by: uuid.UUID
    owner_org_id: uuid.UUID | None = None
    parent_group_id: uuid.UUID | None = None
    group_type: str | None = None
    description: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdatePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    name: str | None = None
    group_type: str | None | object = UNSET
    description: str | None | object = UNSET


@dataclass(frozen=True, kw_only=True)
class MovePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    new_parent_group_id: uuid.UUID | None


@dataclass(frozen=True, kw_only=True)
class DeletePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class AssignPlatesToGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    plate_ids: list[uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class RemovePlatesFromGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    plate_ids: list[uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class GetGroupTreeQuery(Query):
    workspace_id: uuid.UUID
    org_id: uuid.UUID | None = None  # None -> caller's own org


# ---------------------------------------------------------------------------
# Tree DTOs + pure helpers (unit-tested directly)
# ---------------------------------------------------------------------------


@dataclass
class GroupTreeNode:
    group: PlateGroup
    plate_count: int
    children: list[GroupTreeNode] = field(default_factory=list)


@dataclass
class GroupTree:
    org_id: uuid.UUID
    roots: list[GroupTreeNode]


def build_tree(
    groups: list[PlateGroup], counts: dict[uuid.UUID, int]
) -> list[GroupTreeNode]:
    """Assemble nested nodes from a flat fetch. A node whose parent isn't in
    the fetched set is promoted to root (defensive — never crash the page)."""
    nodes = {g.id: GroupTreeNode(group=g, plate_count=counts.get(g.id, 0)) for g in groups}
    roots: list[GroupTreeNode] = []
    for g in groups:
        node = nodes[g.id]
        if g.parent_group_id is not None and g.parent_group_id in nodes:
            nodes[g.parent_group_id].children.append(node)
        else:
            roots.append(node)
    for node in nodes.values():
        node.children.sort(key=lambda n: n.group.name.lower())
    roots.sort(key=lambda n: n.group.name.lower())
    return roots


def is_descendant(
    groups_by_id: dict[uuid.UUID, PlateGroup],
    ancestor_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> bool:
    """True iff candidate is ancestor itself or sits anywhere under it.
    Walks parent pointers; tolerates chains that leave the map."""
    seen: set[uuid.UUID] = set()
    current: uuid.UUID | None = candidate_id
    while current is not None and current not in seen:
        if current == ancestor_id:
            return True
        seen.add(current)
        parent = groups_by_id.get(current)
        current = parent.parent_group_id if parent else None
    return False


def _not_found(group_id: uuid.UUID) -> Failure:
    return Failure(NotFoundError("PlateGroup", str(group_id)))


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class CreatePlateGroup:
    """Create a group; owner org defaults to the caller's org."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: CreatePlateGroupCommand, auth: AuthContext | None = None
    ) -> Result[PlateGroup, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        if (
            auth is not None
            and input.owner_org_id is not None
            and input.owner_org_id != auth.org_id
            and not auth.is_admin
        ):
            raise AuthorizationError("Cannot create groups for another organization")

        owner_org_id = input.owner_org_id if input.owner_org_id is not None else (
            auth.org_id if auth else None
        )
        if owner_org_id is None:
            return Failure(
                ValidationError("owner_org_id is required (caller has no organization)")
            )

        async with self._uow:
            if input.parent_group_id is not None:
                parent = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, input.parent_group_id
                )
                if parent is None:
                    return _not_found(input.parent_group_id)
                excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
                if not self._visibility.can_view_owner(parent.owner_org_id, excluded):
                    return _not_found(input.parent_group_id)
                if parent.owner_org_id != owner_org_id:
                    return Failure(
                        ValidationError("Parent group belongs to a different organization")
                    )

            dup = await self._repo.find_by_name(
                input.workspace_id, owner_org_id, input.parent_group_id, input.name.strip()
            )
            if dup is not None:
                return Failure(
                    ConflictError(f"A group named '{input.name.strip()}' already exists here")
                )

            group = PlateGroup.create(
                workspace_id=input.workspace_id,
                owner_org_id=owner_org_id,
                name=input.name,
                created_by=input.created_by,
                parent_group_id=input.parent_group_id,
                group_type=input.group_type,
                description=input.description,
            )
            await self._repo.save(group)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(group)


class UpdatePlateGroup:
    """Rename / retype / redescribe a group."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: UpdatePlateGroupCommand, auth: AuthContext | None = None
    ) -> Result[PlateGroup, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            if input.name is not None and input.name.strip() != group.name:
                dup = await self._repo.find_by_name(
                    input.workspace_id, group.owner_org_id, group.parent_group_id,
                    input.name.strip(),
                )
                if dup is not None and dup.id != group.id:
                    return Failure(
                        ConflictError(
                            f"A group named '{input.name.strip()}' already exists here"
                        )
                    )

            kwargs: dict = {}
            if input.name is not None:
                kwargs["name"] = input.name
            if input.group_type is not UNSET:
                kwargs["group_type"] = input.group_type
            if input.description is not UNSET:
                kwargs["description"] = input.description
            group.update(**kwargs)

            await self._repo.save(group)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(group)


class MovePlateGroup:
    """Reparent a group (None = make root). Rejects cycles and org mixing."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: MovePlateGroupCommand, auth: AuthContext | None = None
    ) -> Result[PlateGroup, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            if input.new_parent_group_id is not None:
                # One flat fetch of the org's groups covers parent lookup +
                # cycle walk (org trees are small; ponytail: no recursive SQL).
                org_groups = await self._repo.find_by_workspace(
                    input.workspace_id, owner_org_id=group.owner_org_id
                )
                by_id = {g.id: g for g in org_groups}
                parent = by_id.get(input.new_parent_group_id)
                if parent is None:
                    # Missing OR belongs to another org — same 404 either way.
                    return _not_found(input.new_parent_group_id)
                if is_descendant(by_id, group.id, parent.id):
                    return Failure(
                        ValidationError("Cannot move a group under its own descendant")
                    )

            dup = await self._repo.find_by_name(
                input.workspace_id, group.owner_org_id, input.new_parent_group_id, group.name
            )
            if dup is not None and dup.id != group.id:
                return Failure(
                    ConflictError(
                        f"A group named '{group.name}' already exists under the target parent"
                    )
                )

            group.move_to(input.new_parent_group_id)
            await self._repo.save(group)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(group)


class DeletePlateGroup:
    """Delete a childless group; member plates auto-ungroup via DB SET NULL."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: DeletePlateGroupCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            children = await self._repo.find_children(input.workspace_id, input.group_id)
            if children:
                return Failure(
                    ConflictError(f"Cannot delete group '{group.name}': it has child groups")
                )

            deleted_event = PlateGroupDeleted(
                aggregate_id=group.id,
                aggregate_type="PlateGroup",
                workspace_id=group.workspace_id,
                name=group.name,
                owner_org_id=group.owner_org_id,
            )
            await self._repo.delete(input.workspace_id, input.group_id)
            await self._uow.commit()

        await self._dispatcher.dispatch_all([deleted_event])
        return Success(None)


class GetGroupTree:
    """Org-scoped group tree with per-group plate counts (spec §5, §10)."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._visibility = visibility

    async def __call__(
        self, input: GetGroupTreeQuery, auth: AuthContext | None = None
    ) -> Result[GroupTree, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        org_id = input.org_id if input.org_id is not None else (auth.org_id if auth else None)
        if org_id is None:
            return Failure(ValidationError("org_id is required (caller has no organization)"))

        async with self._uow:
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if org_id in excluded:
                # Spec §5: org-scoped reads of a private org are member-only.
                raise AuthorizationError("This organization's plates are private")
            groups = await self._repo.find_by_workspace(input.workspace_id, owner_org_id=org_id)
            counts = await self._repo.count_plates_by_group(
                input.workspace_id, owner_org_id=org_id
            )
            return Success(GroupTree(org_id=org_id, roots=build_tree(groups, counts)))


class AssignPlatesToGroup:
    """Set group on plates. Every plate must be visible and share the group's org."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        plate_repo: RegisteredPlateRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._plate_repo = plate_repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: AssignPlatesToGroupCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        if not input.plate_ids:
            return Failure(ValidationError("plate_ids must not be empty"))

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            plates = []
            for plate_id in input.plate_ids:
                plate = await self._plate_repo.find_by_id_in_workspace(
                    input.workspace_id, plate_id
                )
                if plate is None or not self._visibility.can_view(plate, auth, excluded):
                    return Failure(NotFoundError("RegisteredPlate", str(plate_id)))
                if plate.owner_org_id != group.owner_org_id:
                    return Failure(
                        ValidationError(
                            f"Plate '{plate.barcode.value}' belongs to a different "
                            "organization than the group"
                        )
                    )
                plates.append(plate)

            for plate in plates:
                plate.assign_to_group(group.id)
                await self._plate_repo.save(plate)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemovePlatesFromGroup:
    """Clear group on plates currently in the given group."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        plate_repo: RegisteredPlateRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._plate_repo = plate_repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: RemovePlatesFromGroupCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        if not input.plate_ids:
            return Failure(ValidationError("plate_ids must not be empty"))

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            plates = []
            for plate_id in input.plate_ids:
                plate = await self._plate_repo.find_by_id_in_workspace(
                    input.workspace_id, plate_id
                )
                if plate is None or not self._visibility.can_view(plate, auth, excluded):
                    return Failure(NotFoundError("RegisteredPlate", str(plate_id)))
                if plate.group_id != group.id:
                    return Failure(
                        ValidationError(
                            f"Plate '{plate.barcode.value}' is not in this group"
                        )
                    )
                plates.append(plate)

            for plate in plates:
                plate.assign_to_group(None)
                await self._plate_repo.save(plate)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
