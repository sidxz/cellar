"""ListExternalProtocols query -- fetch available protocols from external vault."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.vault_import._check_config import check_vault_configured
from chem_vault.application.vault_import.gateway import ExternalProtocolGateway
from chem_vault.application.vault_import.mapper import (
    ExternalProtocolSummary,
    map_external_protocol_list,
)
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.domain.workspace_config.repository import (
    ExternalApiKeyRepository,
    WorkspaceSettingsRepository,
)
from chem_vault.application.vault_import.errors import VaultAuthError, VaultConnectionError, VaultNotFoundError


@dataclass(frozen=True, kw_only=True)
class ListExternalProtocolsQuery(Query):
    workspace_id: uuid.UUID


class ListExternalProtocols:
    def __init__(
        self,
        gateway: ExternalProtocolGateway,
        secret_provider: SecretProvider,
        settings_repo: WorkspaceSettingsRepository,
        api_key_repo: ExternalApiKeyRepository,
        uow: UnitOfWork,
    ) -> None:
        self._gateway = gateway
        self._secret_provider = secret_provider
        self._settings_repo = settings_repo
        self._api_key_repo = api_key_repo
        self._uow = uow

    async def __call__(
        self, input: ListExternalProtocolsQuery, auth: AuthContext | None = None
    ) -> Result[list[ExternalProtocolSummary], DomainError]:
        require_editor(auth)

        async with self._uow:
            config = await check_vault_configured(
                input.workspace_id, self._settings_repo, self._api_key_repo, self._secret_provider
            )
            if isinstance(config, Failure):
                return config

            vault_id, api_key = config.unwrap()

        try:
            raw = await self._gateway.list_protocols(vault_id, api_key)
        except VaultAuthError:
            return Failure(ValidationError("Vault API key is invalid or expired"))
        except VaultNotFoundError:
            return Failure(ValidationError("Vault ID not found"))
        except VaultConnectionError:
            return Failure(ValidationError("Could not connect to external vault"))

        return Success(map_external_protocol_list(raw))
