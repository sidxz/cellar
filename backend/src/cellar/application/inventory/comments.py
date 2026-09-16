"""Comment use cases — append-only feed on loans / groups / plates (spec 2026-08-25 §7)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.plate_loans import _loan_visible
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.comment import Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.domain.inventory.repository import (
    CommentRepository,
    PlateGroupRepository,
    PlateLoanRepository,
    RegisteredPlateRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class AddCommentCommand(Command):
    workspace_id: uuid.UUID
    target_type: CommentTarget
    target_id: uuid.UUID
    body: str
    loan_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class ListCommentsQuery(Query):
    workspace_id: uuid.UUID
    target_type: CommentTarget | None = None
    target_id: uuid.UUID | None = None
    loan_id: uuid.UUID | None = None


@dataclass
class TargetRepos:
    plate_repo: RegisteredPlateRepository
    group_repo: PlateGroupRepository
    loan_repo: PlateLoanRepository


async def resolve_target_visible(
    *,
    repos: TargetRepos,
    visibility: PlateVisibilityService,
    workspace_id: uuid.UUID,
    auth: AuthContext | None,
    target_type: CommentTarget,
    target_id: uuid.UUID,
) -> DomainError | None:
    """None when the caller may see the target; NotFoundError otherwise (hidden == missing).
    Plate targets use the borrowed carve-out on purpose: a borrower annotates the
    plates it holds (documented exception to plate_visibility's write narrowing)."""
    excluded = await visibility.excluded_org_ids(workspace_id, auth)
    if target_type is CommentTarget.PLATE:
        plate = await repos.plate_repo.find_by_id_in_workspace(workspace_id, target_id)
        borrowed = await visibility.borrowed_plate_ids(workspace_id, auth)
        if plate is None or not visibility.can_view(plate, auth, excluded, borrowed):
            return NotFoundError("RegisteredPlate", str(target_id))
        return None
    if target_type is CommentTarget.PLATE_GROUP:
        group = await repos.group_repo.find_by_id_in_workspace(workspace_id, target_id)
        if group is None or not visibility.can_view_owner(group.owner_org_id, excluded):
            return NotFoundError("PlateGroup", str(target_id))
        return None
    loan = await repos.loan_repo.find_by_id_in_workspace(workspace_id, target_id)
    if loan is None or not _loan_visible(loan, auth, excluded):
        return NotFoundError("PlateLoan", str(target_id))
    return None


async def _loan_contains_target(
    repos: TargetRepos,
    workspace_id: uuid.UUID,
    loan_id: uuid.UUID,
    target_type: CommentTarget,
    target_id: uuid.UUID,
) -> bool:
    loan = await repos.loan_repo.find_by_id_in_workspace(workspace_id, loan_id)
    if loan is None:
        return False
    plate_ids = [i.plate_id for i in loan.items]
    if target_type is CommentTarget.PLATE_LOAN:
        return loan.id == target_id
    if target_type is CommentTarget.PLATE:
        return target_id in plate_ids
    plates = await repos.plate_repo.find_by_ids(workspace_id, plate_ids)
    return any(p.group_id == target_id for p in plates)


class AddComment:
    def __init__(
        self,
        uow: UnitOfWork,
        comment_repo: CommentRepository,
        repos: TargetRepos,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._comments = comment_repo
        self._repos = repos
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: AddCommentCommand, auth: AuthContext | None = None
    ) -> Result[Comment, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None

        async with self._uow:
            err = await resolve_target_visible(
                repos=self._repos,
                visibility=self._visibility,
                workspace_id=input.workspace_id,
                auth=auth,
                target_type=input.target_type,
                target_id=input.target_id,
            )
            if err is not None:
                return Failure(err)
            if input.loan_id is not None:
                loan_err = await resolve_target_visible(
                    repos=self._repos,
                    visibility=self._visibility,
                    workspace_id=input.workspace_id,
                    auth=auth,
                    target_type=CommentTarget.PLATE_LOAN,
                    target_id=input.loan_id,
                )
                if loan_err is not None:
                    return Failure(loan_err)
                if not await _loan_contains_target(
                    self._repos,
                    input.workspace_id,
                    input.loan_id,
                    input.target_type,
                    input.target_id,
                ):
                    return Failure(ValidationError("The loan does not contain this target"))
            # A comment made directly on a loan is trivially in that loan's own
            # context: denormalize loan_id = target_id here so list_for_loan
            # (which filters on the loan_id column) surfaces it too.
            loan_id = input.loan_id
            if loan_id is None and input.target_type is CommentTarget.PLATE_LOAN:
                loan_id = input.target_id
            comment = Comment.create(
                workspace_id=input.workspace_id,
                target_type=input.target_type,
                target_id=input.target_id,
                body=input.body,
                author_id=auth.user_id,
                author_name=auth.name or auth.email,
                loan_id=loan_id,
            )
            await self._comments.save(comment)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(comment)


class ListComments:
    def __init__(
        self,
        uow: UnitOfWork,
        comment_repo: CommentRepository,
        repos: TargetRepos,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._comments = comment_repo
        self._repos = repos
        self._visibility = visibility

    async def __call__(
        self, input: ListCommentsQuery, auth: AuthContext | None = None
    ) -> Result[list[Comment], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        by_target = input.target_type is not None and input.target_id is not None
        by_loan = input.loan_id is not None
        if by_target == by_loan:
            return Failure(ValidationError("Provide target_type+target_id or loan_id (not both)"))
        async with self._uow:
            if by_loan:
                assert input.loan_id is not None
                err = await resolve_target_visible(
                    repos=self._repos,
                    visibility=self._visibility,
                    workspace_id=input.workspace_id,
                    auth=auth,
                    target_type=CommentTarget.PLATE_LOAN,
                    target_id=input.loan_id,
                )
                if err is not None:
                    return Failure(err)
                return Success(
                    await self._comments.list_for_loan(input.workspace_id, input.loan_id)
                )
            assert input.target_type is not None and input.target_id is not None
            err = await resolve_target_visible(
                repos=self._repos,
                visibility=self._visibility,
                workspace_id=input.workspace_id,
                auth=auth,
                target_type=input.target_type,
                target_id=input.target_id,
            )
            if err is not None:
                return Failure(err)
            return Success(
                await self._comments.list_for_target(
                    input.workspace_id, input.target_type, input.target_id
                )
            )
