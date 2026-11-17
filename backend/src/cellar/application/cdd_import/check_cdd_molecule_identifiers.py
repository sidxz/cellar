"""CheckCddMoleculeIdentifiers query -- which listed identifiers name a molecule in CDD Vault."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.cdd_import._check_config import check_cdd_configured
from cellar.application.cdd_import.errors import CddAuthError, CddConnectionError, CddNotFoundError
from cellar.application.cdd_import.gateway import CddMoleculeLookupGateway
from cellar.application.cdd_import.molecule_identifiers import (
    MAX_IDENTIFIERS,
    IdentifierMatch,
    match_identifiers,
    parse_identifiers,
)
from cellar.application.shared.query import Query
from cellar.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
)
from cellar.domain.shared.errors import DomainError, ValidationError


@dataclass(frozen=True, kw_only=True)
class CheckCddMoleculeIdentifiersQuery(Query):
    workspace_id: uuid.UUID
    text: str  # as pasted: one identifier per line, or separated by commas, semicolons or tabs


class CheckCddMoleculeIdentifiers:
    """Look the identifiers up by molecule name or synonym. Imports nothing."""

    def __init__(
        self,
        gateway: CddMoleculeLookupGateway,
        get_data_source: GetDataSourceForImport,
    ) -> None:
        self._gateway = gateway
        self._get_data_source = get_data_source

    async def __call__(
        self, input: CheckCddMoleculeIdentifiersQuery, auth: AuthContext | None = None
    ) -> Result[IdentifierMatch, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        identifiers = parse_identifiers(input.text)
        if not identifiers:
            return Failure(ValidationError("Enter at least one identifier"))
        if len(identifiers) > MAX_IDENTIFIERS:
            return Failure(
                ValidationError(f"At most {MAX_IDENTIFIERS} identifiers can be checked at once")
            )

        config = await check_cdd_configured(input.workspace_id, self._get_data_source)
        if isinstance(config, Failure):
            return config

        vault_id, api_key = config.unwrap()

        try:
            molecules = await self._gateway.find_molecules_by_names(vault_id, api_key, identifiers)
        except CddAuthError:
            return Failure(ValidationError("CDD Vault API key is invalid or expired"))
        except CddNotFoundError:
            return Failure(ValidationError("CDD Vault ID not found"))
        except CddConnectionError:
            return Failure(ValidationError("Could not connect to CDD Vault"))

        return Success(match_identifiers(identifiers, molecules))
