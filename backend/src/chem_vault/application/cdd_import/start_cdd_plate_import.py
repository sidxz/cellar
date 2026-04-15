"""StartCddPlateImport command — validate DataSource config for plate import."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.workspace_config.get_data_source_for_import import (
    DataSourceImportConfig,
    GetDataSourceForImport,
    GetDataSourceForImportQuery,
)
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.domain.workspace_config.data_source import DataSourceType


@dataclass(frozen=True, kw_only=True)
class StartCddPlateImportCommand(Command):
    workspace_id: uuid.UUID


@dataclass(frozen=True)
class CddPlateImportConfig:
    """Validated CDD config needed to start the plate import workflow."""

    vault_id: str
    secret_ref: str
    entity_mappings: list[dict]  # serialized EntityMapping dicts for Temporal


class StartCddPlateImport:
    """Validate CDD DataSource config for plate import.

    Returns vault_id + secret_ref. The API route starts the Temporal workflow.
    """

    def __init__(self, get_data_source: GetDataSourceForImport) -> None:
        self._get_data_source = get_data_source

    async def __call__(
        self,
        input: StartCddPlateImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[CddPlateImportConfig, DomainError]:
        require_editor(auth)

        result = await self._get_data_source(
            GetDataSourceForImportQuery(
                workspace_id=input.workspace_id,
                source_type=DataSourceType.CDD_VAULT,
            )
        )
        if isinstance(result, Failure):
            return result

        config: DataSourceImportConfig = result.unwrap()
        vault_id = config.data_source.config.get("vault_id", "")
        if not vault_id:
            return Failure(
                ValidationError("CDD Vault data source has no vault_id configured")
            )

        secret_ref = f"{input.workspace_id}:{config.data_source.api_key_name}"

        return Success(
            CddPlateImportConfig(
                vault_id=str(vault_id),
                secret_ref=secret_ref,
                entity_mappings=[em.to_dict() for em in config.data_source.entity_mappings],
            )
        )
