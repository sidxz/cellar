"""CreateExternalApiKey command — create a new external API key."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import ConflictError, DomainError
from cellar.domain.shared.secret_provider import SecretProvider
from cellar.domain.workspace_config.external_api_key import ExternalApiKey
from cellar.domain.workspace_config.repository import ExternalApiKeyRepository


@dataclass(frozen=True, kw_only=True)
class CreateExternalApiKeyCommand(Command):
    workspace_id: uuid.UUID
    key_name: str
    label: str
    description: str | None = None
    secret_value: str  # the actual API key — stored via SecretProvider


class CreateExternalApiKey:
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
        self, input: CreateExternalApiKeyCommand, auth: AuthContext | None = None
    ) -> Result[ExternalApiKey, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            # Check for duplicate key_name in this workspace
            existing = await self._repo.find_by_key_name(
                input.workspace_id, input.key_name.strip()
            )
            if existing is not None:
                return Failure(
                    ConflictError(
                        f"API key with name '{input.key_name.strip()}' "
                        "already exists in this workspace"
                    )
                )

            # Build display prefix (first 6 chars + "...")
            secret = input.secret_value.strip()
            prefix = secret[:6] + "..." if len(secret) > 6 else secret

            entry = ExternalApiKey.create(
                workspace_id=input.workspace_id,
                key_name=input.key_name,
                label=input.label,
                description=input.description,
                key_prefix=prefix,
                created_by=auth.user_id if auth else uuid.UUID(int=0),
            )
            await self._repo.save(entry)

            # Store the secret externally
            secret_key = f"{input.workspace_id}:{input.key_name.strip()}"
            await self._secret_provider.set_secret(secret_key, secret)

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(entry)
