"""StartCddMoleculeImport command — validate config and start the Temporal workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
    GetDataSourceForImportQuery,
)
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.domain.workspace_config.data_source import DataSourceType


@dataclass(frozen=True, kw_only=True)
class StartCddMoleculeImportCommand(Command):
    workspace_id: uuid.UUID
    import_mode: str = "full_vault"
    filter_criteria: dict | None = None


@dataclass(frozen=True)
class CddImportConfig:
    """Validated CDD config needed to start the import workflow."""

    vault_id: str
    secret_ref: str
    entity_mappings: list[dict]  # serialized EntityMapping dicts for Temporal


class StartCddMoleculeImport:
    """Validate CDD config and start the import workflow.

    The actual import runs in a Temporal workflow. This use case:
    1. Validates CDD vault config via DataSource
    2. Returns the secret_ref + vault_id for the workflow to use

    The API route layer starts the Temporal workflow.
    """

    def __init__(self, get_data_source: GetDataSourceForImport) -> None:
        self._get_data_source = get_data_source

    async def __call__(
        self,
        input: StartCddMoleculeImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[CddImportConfig, DomainError]:
        """Validate CDD config. Returns CddImportConfig on success."""
        require_editor(auth)

        if input.import_mode not in ("full_vault", "filtered", "sync"):
            return Failure(ValidationError(f"Invalid import_mode: {input.import_mode}"))

        result = await self._get_data_source(
            GetDataSourceForImportQuery(
                workspace_id=input.workspace_id,
                source_type=DataSourceType.CDD_VAULT,
            )
        )
        if isinstance(result, Failure):
            return result

        config = result.unwrap()
        vault_id = str(config.data_source.config.get("vault_id", ""))
        if not vault_id:
            return Failure(ValidationError("CDD Vault data source has no vault_id configured"))

        secret_ref = f"{input.workspace_id}:{config.data_source.api_key_name}"

        return Success(
            CddImportConfig(
                vault_id=vault_id,
                secret_ref=secret_ref,
                entity_mappings=[em.to_dict() for em in config.data_source.entity_mappings],
            )
        )
