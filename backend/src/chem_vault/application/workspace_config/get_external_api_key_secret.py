"""GetExternalApiKeySecret — internal use case to retrieve a secret for service clients."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.domain.shared.secret_provider import SecretProvider


@dataclass(frozen=True, kw_only=True)
class GetExternalApiKeySecretQuery(Query):
    workspace_id: uuid.UUID
    key_name: str


class GetExternalApiKeySecret:
    def __init__(self, secret_provider: SecretProvider) -> None:
        self._secret_provider = secret_provider

    async def __call__(
        self, input: GetExternalApiKeySecretQuery
    ) -> Result[str, DomainError]:
        secret_key = f"{input.workspace_id}:{input.key_name}"
        secret = await self._secret_provider.get_secret(secret_key)
        if secret is None:
            return Failure(NotFoundError("SecretValue", input.key_name))
        return Success(secret)
