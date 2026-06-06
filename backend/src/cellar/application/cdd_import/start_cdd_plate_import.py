"""StartCddPlateImport command — validate config and dispatch the plate-import workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.cdd_import.cdd_plate_import_orchestrator import (
    CddPlateImportOrchestrator,
    StartCddPlateImportRequest,
)
from cellar.application.shared.command import Command
from cellar.application.workspace_config.get_data_source_for_import import (
    DataSourceImportConfig,
    GetDataSourceForImport,
    GetDataSourceForImportQuery,
)
from cellar.domain.shared.errors import DomainError, ValidationError
from cellar.domain.workspace_config.data_source import DataSourceType


@dataclass(frozen=True, kw_only=True)
class StartCddPlateImportCommand(Command):
    workspace_id: uuid.UUID
    submitted_by: uuid.UUID


@dataclass(frozen=True)
class StartCddPlateImportResult:
    workflow_id: str


class StartCddPlateImport:
    """Validate CDD DataSource config and dispatch the plate-import workflow."""

    def __init__(
        self,
        get_data_source: GetDataSourceForImport,
        orchestrator: CddPlateImportOrchestrator,
    ) -> None:
        self._get_data_source = get_data_source
        self._orchestrator = orchestrator

    async def __call__(
        self,
        input: StartCddPlateImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[StartCddPlateImportResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        ds_result = await self._get_data_source(
            GetDataSourceForImportQuery(
                workspace_id=input.workspace_id,
                source_type=DataSourceType.CDD_VAULT,
            )
        )
        if isinstance(ds_result, Failure):
            return ds_result

        config: DataSourceImportConfig = ds_result.unwrap()
        vault_id = config.data_source.config.get("vault_id", "")
        if not vault_id:
            return Failure(ValidationError("CDD Vault data source has no vault_id configured"))

        secret_ref = f"{input.workspace_id}:{config.data_source.api_key_name}"

        request = StartCddPlateImportRequest(
            workspace_id=input.workspace_id,
            cdd_vault_id=str(vault_id),
            submitted_by=input.submitted_by,
            secret_ref=secret_ref,
            entity_mappings=[em.to_dict() for em in config.data_source.entity_mappings],
        )

        workflow_id = await self._orchestrator.start(request)
        return Success(StartCddPlateImportResult(workflow_id=workflow_id))
