"""DeleteExternalApiKey command — remove an API key and its secret."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.shared.secret_provider import SecretProvider
from cellar.domain.workspace_config.repository import ExternalApiKeyRepository


@dataclass(frozen=True, kw_only=True)
class DeleteExternalApiKeyCommand(Command):
    workspace_id: uuid.UUID
    key_id: uuid.UUID


class DeleteExternalApiKey:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ExternalApiKeyRepository,
        dispatcher: EventDispatcherProtocol,
        secret_provider: SecretProvider,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._secret_provider = secret_provider

    async def __call__(
        self, input: DeleteExternalApiKeyCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            entry = await self._repo.find_by_id_in_workspace(input.workspace_id, input.key_id)
            if entry is None:
                return Failure(NotFoundError("ExternalApiKey", str(input.key_id)))

            # Delete secret
            secret_key = f"{input.workspace_id}:{entry.key_name}"
            await self._secret_provider.delete_secret(secret_key)

            await self._repo.delete(input.workspace_id, input.key_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
