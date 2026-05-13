"""PreviewCddProtocolImport query -- fetch and map a single CDD protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.cdd_import._check_config import check_cdd_configured
from cellar.application.cdd_import.errors import CddAuthError, CddConnectionError, CddNotFoundError
from cellar.application.cdd_import.gateway import CddProtocolGateway
from cellar.application.cdd_import.mapper import (
    CddProtocolMappingResult,
    map_cdd_protocol,
)
from cellar.application.shared.query import Query
from cellar.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class PreviewCddProtocolImportQuery(Query):
    workspace_id: uuid.UUID
    external_protocol_id: int


class PreviewCddProtocolImport:
    def __init__(
        self,
        gateway: CddProtocolGateway,
        get_data_source: GetDataSourceForImport,
    ) -> None:
        self._gateway = gateway
        self._get_data_source = get_data_source

    async def __call__(
        self, input: PreviewCddProtocolImportQuery, auth: AuthContext | None = None
    ) -> Result[CddProtocolMappingResult, DomainError]:
        require_editor(auth)

        config = await check_cdd_configured(input.workspace_id, self._get_data_source)
        if isinstance(config, Failure):
            return config

        vault_id, api_key = config.unwrap()

        try:
            raw = await self._gateway.get_protocol(vault_id, api_key, input.external_protocol_id)
        except CddAuthError:
            return Failure(ValidationError("CDD Vault API key is invalid or expired"))
        except CddNotFoundError:
            return Failure(NotFoundError("CDD Protocol", str(input.external_protocol_id)))
        except CddConnectionError:
            return Failure(ValidationError("Could not connect to CDD Vault"))

        return Success(map_cdd_protocol(raw))
