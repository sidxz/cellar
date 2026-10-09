"""Re-derive protocol names after something outside the protocol changed (registry, admin)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog
from returns.result import Result, Success

from cellar.application.auth import (
    AuthContext,
    require_admin,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import NameFlag
from cellar.domain.screening_assay.repository import FlaggedProtocol, ProtocolRepository
from cellar.domain.shared.errors import ConcurrencyConflictError, DomainError, ValidationError

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class RederiveProtocolNamesCommand(Command):
    workspace_id: uuid.UUID
    protocol_ids: list[uuid.UUID]
    reason: str


@dataclass(frozen=True)
class RederiveReport:
    renamed: int
    flagged: int
    failed: list[str]


class RederiveProtocolNames:
    """System path: never refuses. Each protocol is its own unit of work so one concurrent
    edit cannot sink the whole batch; a version conflict is retried once."""

    def __init__(
        self,
        *,
        uow_factory: Callable[[], UnitOfWork],
        names_factory: Callable[[Any], ProtocolNameService],
        repo_factory: Callable[[Any], ProtocolRepository],
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow_factory = uow_factory
        self._names_factory = names_factory
        self._repo_factory = repo_factory
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RederiveProtocolNamesCommand, auth: AuthContext | None = None
    ) -> Result[RederiveReport, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        renamed = flagged = 0
        failed: list[str] = []
        for protocol_id in input.protocol_ids:
            for attempt in (1, 2):
                try:
                    outcome = await self._one(input.workspace_id, protocol_id, input.reason)
                except ConcurrencyConflictError:
                    if attempt == 2:
                        failed.append(str(protocol_id))
                        _log.warning(
                            "protocol.name.rederive_conflict", protocol_id=str(protocol_id)
                        )
                    continue
                renamed += outcome == "renamed"
                flagged += outcome == "flagged"
                break
        return Success(RederiveReport(renamed=renamed, flagged=flagged, failed=failed))

    async def _one(self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, reason: str) -> str:
        uow = self._uow_factory()
        async with uow:
            repo = self._repo_factory(uow)
            protocol = await repo.find_by_id_in_workspace(workspace_id, protocol_id)
            if protocol is None:
                return "missing"
            before = protocol.name
            try:
                await self._names_factory(uow).apply(
                    protocol, reason=reason, person=False, allow_incomplete=True
                )
            except ValidationError:
                # The new name is over the length limit: keep the old one, flag it.
                protocol.flag_name(NameFlag.NEEDS_FACTS)
                _log.warning("protocol.name.too_long", protocol_id=str(protocol_id))
            await repo.save(protocol)
            events = await uow.commit()
        await self._dispatcher.dispatch_all(events)
        if protocol.name != before:
            return "renamed"
        return "flagged" if protocol.name_flag else "unchanged"


@dataclass(frozen=True)
class NameCheck:
    """What re-deriving one protocol would do: its name now, after, and the flag it would get."""

    protocol_id: uuid.UUID
    code: str | None
    before: str
    after: str
    flag: str | None


@dataclass(frozen=True, kw_only=True)
class RederiveAllProtocolNamesCommand(Command):
    workspace_id: uuid.UUID
    dry_run: bool
    reason: str


@dataclass(frozen=True)
class RederiveAllResult:
    changes: list[NameCheck]
    report: RederiveReport | None  # None on a dry run


class RederiveAllProtocolNames:
    """Admin: check every protocol's name against its facts (dry run), then apply."""

    def __init__(
        self,
        *,
        uow_factory: Callable[[], UnitOfWork],
        names_factory: Callable[[Any], ProtocolNameService],
        repo_factory: Callable[[Any], ProtocolRepository],
        rederive: RederiveProtocolNames,
    ) -> None:
        self._uow_factory = uow_factory
        self._names_factory = names_factory
        self._repo_factory = repo_factory
        self._rederive = rederive

    async def __call__(
        self, input: RederiveAllProtocolNamesCommand, auth: AuthContext | None = None
    ) -> Result[RederiveAllResult, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        if not input.dry_run:
            uow = self._uow_factory()
            async with uow:
                ids = await self._repo_factory(uow).list_ids(input.workspace_id)
            report = await self._rederive(
                RederiveProtocolNamesCommand(
                    workspace_id=input.workspace_id, protocol_ids=ids, reason=input.reason
                ),
                auth=auth,
            )
            return report.map(lambda r: RederiveAllResult(changes=[], report=r))
        checks: list[NameCheck] = []
        uow = self._uow_factory()
        async with uow:
            repo = self._repo_factory(uow)
            names = self._names_factory(uow)
            # ponytail: one derive per protocol; fine for hundreds, batch if thousands.
            for protocol_id in await repo.list_lineage_ids(input.workspace_id):
                p = await repo.find_by_id_in_workspace(input.workspace_id, protocol_id)
                if p is None:
                    continue
                d = await names.derive(
                    input.workspace_id,
                    category=p.category,
                    target_ids=await repo.find_direct_target_ids(input.workspace_id, p.id),
                    annotations=p.ontology_annotations,
                    discriminator=p.discriminator,
                    exclude_code=p.code,
                )
                flag = names.check(d, person=False, allow_incomplete=True).unwrap()
                after = d.rendered.name if d.rendered.complete else p.name
                if after != p.name or flag != p.name_flag:
                    checks.append(
                        NameCheck(
                            protocol_id=p.id,
                            code=p.code,
                            before=p.name,
                            after=after,
                            flag=flag.value if flag else None,
                        )
                    )
        return Success(RederiveAllResult(changes=checks, report=None))


@dataclass(frozen=True, kw_only=True)
class ListNameFlagsQuery(Query):
    workspace_id: uuid.UUID


class ListNameFlags:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListNameFlagsQuery, auth: AuthContext | None = None
    ) -> Result[list[FlaggedProtocol], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            return Success(await self._repo.find_flagged(input.workspace_id))
