"""Re-derive protocol names after something outside the protocol changed (registry, admin)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog
from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import NameFlag
from cellar.domain.screening_assay.repository import ProtocolRepository
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
