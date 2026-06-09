"""Run hit-criteria use cases — set and reset a run's hit threshold.

Distinct from the protocol's ``recommended_hit_criteria`` (the SOP suggestion):
these record an *attributable per-run analytical decision* — who set this run's
hit threshold and when. The protocol value is only ever recommended in the UI;
it is never applied to a run automatically.

Setting an empty criteria list is a valid, recorded decision meaning "no
threshold — show all compounds". Resetting reverts the run to "unset" so the
protocol recommendation is shown again as a suggestion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.repository import RunRepository
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.shared.hit_criterion import HitCriterion


@dataclass(frozen=True, kw_only=True)
class SetRunHitCriteriaCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    # Empty list is a valid, recorded "show all" decision. The route maps the
    # request payload into these domain value objects.
    criteria: list[HitCriterion] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ResetRunHitCriteriaCommand(Command):
    workspace_id: uuid.UUID
    run_id: uuid.UUID


class SetRunHitCriteria:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: SetRunHitCriteriaCommand,
        auth: AuthContext | None = None,
    ) -> Result[Run, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            run.set_hit_criteria(input.criteria, set_by=auth.user_id)
            await self._repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(run)


class ResetRunHitCriteria:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: RunRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: ResetRunHitCriteriaCommand,
        auth: AuthContext | None = None,
    ) -> Result[Run, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            run = await self._repo.find_by_id_in_workspace(input.workspace_id, input.run_id)
            if run is None:
                return Failure(NotFoundError("Run", str(input.run_id)))
            run.clear_hit_criteria(cleared_by=auth.user_id)
            await self._repo.save(run)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(run)
