"""UpdateExternalApiKey command — update metadata and optionally rotate secret."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError
from cellar.domain.shared.secret_provider import SecretProvider
from cellar.domain.workspace_config.external_api_key import ExternalApiKey
from cellar.domain.workspace_config.repository import ExternalApiKeyRepository


@dataclass(frozen=True, kw_only=True)
class UpdateExternalApiKeyCommand(Command):
    workspace_id: uuid.UUID
    key_id: uuid.UUID
    label: str | object = UNSET
    description: str | None | object = UNSET
    secret_value: str | None | object = UNSET
    is_active: bool | object = UNSET


class UpdateExternalApiKey:
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
        self, input: UpdateExternalApiKeyCommand, auth: AuthContext | None = None
    ) -> Result[ExternalApiKey, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            entry = await self._repo.find_by_id_in_workspace(input.workspace_id, input.key_id)
            if entry is None:
                return Failure(NotFoundError("ExternalApiKey", str(input.key_id)))

            # Update metadata fields
            update_kwargs: dict = {}
            if input.label is not UNSET:
                update_kwargs["label"] = input.label
            if input.description is not UNSET:
                update_kwargs["description"] = input.description
            if update_kwargs:
                entry.update(**update_kwargs)

            # Handle is_active separately
            if input.is_active is not UNSET:
                if input.is_active:
                    entry.activate()
                else:
                    entry.deactivate()

            # Rotate secret if provided
            if input.secret_value is not UNSET and input.secret_value is not None:
                secret = str(input.secret_value).strip()
                prefix = secret[:6] + "..." if len(secret) > 6 else secret
                entry.update_prefix(prefix)
                secret_key = f"{input.workspace_id}:{entry.key_name}"
                await self._secret_provider.set_secret(secret_key, secret)

            await self._repo.save(entry)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(entry)
