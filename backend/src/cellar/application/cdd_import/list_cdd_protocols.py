"""ListCddProtocols query -- fetch available protocols from CDD Vault."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.cdd_import._check_config import check_cdd_configured
from cellar.application.cdd_import.errors import CddAuthError, CddConnectionError, CddNotFoundError
from cellar.application.cdd_import.gateway import CddProtocolGateway
from cellar.application.cdd_import.mapper import (
    CddProtocolSummary,
    map_cdd_protocol_list,
)
from cellar.application.shared.query import Query
from cellar.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
)
from cellar.domain.shared.errors import DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ListCddProtocolsQuery(Query):
    workspace_id: uuid.UUID


class ListCddProtocols:
    def __init__(
        self,
        gateway: CddProtocolGateway,
        get_data_source: GetDataSourceForImport,
    ) -> None:
        self._gateway = gateway
        self._get_data_source = get_data_source

    async def __call__(
        self, input: ListCddProtocolsQuery, auth: AuthContext | None = None
    ) -> Result[list[CddProtocolSummary], DomainError]:
        require_editor(auth)

        config = await check_cdd_configured(input.workspace_id, self._get_data_source)
        if isinstance(config, Failure):
            return config

        vault_id, api_key = config.unwrap()

        try:
            raw = await self._gateway.list_protocols(vault_id, api_key)
        except CddAuthError:
            return Failure(ValidationError("CDD Vault API key is invalid or expired"))
        except CddNotFoundError:
            return Failure(ValidationError("CDD Vault ID not found"))
        except CddConnectionError:
            return Failure(ValidationError("Could not connect to CDD Vault"))

        return Success(map_cdd_protocol_list(raw))
