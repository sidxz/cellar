"""StartCddMoleculeImport command — validate config and dispatch the import workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.cdd_import.cdd_molecule_import_orchestrator import (
    CddMoleculeImportOrchestrator,
    StartCddMoleculeImportRequest,
)
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
    submitted_by: uuid.UUID
    originating_org_id: uuid.UUID
    import_mode: str = "full_vault"
    filter_criteria: dict | None = None
    max_molecules: int | None = None  # limit for testing; None = import all


@dataclass(frozen=True)
class StartCddMoleculeImportResult:
    workflow_id: str


class StartCddMoleculeImport:
    """Validate CDD config and dispatch the import workflow.

    Steps:
    1. Validate import_mode + CDD vault DataSource config.
    2. Build engine-agnostic StartCddMoleculeImportRequest.
    3. Hand off to ``CddMoleculeImportOrchestrator.start`` and return its
       workflow_id.
    """

    def __init__(
        self,
        get_data_source: GetDataSourceForImport,
        orchestrator: CddMoleculeImportOrchestrator,
    ) -> None:
        self._get_data_source = get_data_source
        self._orchestrator = orchestrator

    async def __call__(
        self,
        input: StartCddMoleculeImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[StartCddMoleculeImportResult, DomainError]:
        require_editor(auth)

        if input.import_mode not in ("full_vault", "filtered", "sync"):
            return Failure(ValidationError(f"Invalid import_mode: {input.import_mode}"))

        ds_result = await self._get_data_source(
            GetDataSourceForImportQuery(
                workspace_id=input.workspace_id,
                source_type=DataSourceType.CDD_VAULT,
            )
        )
        if isinstance(ds_result, Failure):
            return ds_result

        config = ds_result.unwrap()
        vault_id = str(config.data_source.config.get("vault_id", ""))
        if not vault_id:
            return Failure(ValidationError("CDD Vault data source has no vault_id configured"))

        secret_ref = f"{input.workspace_id}:{config.data_source.api_key_name}"

        request = StartCddMoleculeImportRequest(
            workspace_id=input.workspace_id,
            cdd_vault_id=vault_id,
            import_mode=input.import_mode,
            submitted_by=input.submitted_by,
            originating_org_id=input.originating_org_id,
            secret_ref=secret_ref,
            entity_mappings=[em.to_dict() for em in config.data_source.entity_mappings],
            filter_criteria=input.filter_criteria,
            max_molecules=input.max_molecules,
        )

        workflow_id = await self._orchestrator.start(request)
        return Success(StartCddMoleculeImportResult(workflow_id=workflow_id))
