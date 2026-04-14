"""StartCddMoleculeImport command — validate config and start the Temporal workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.cdd_import._check_config import check_cdd_configured
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.domain.workspace_config.repository import (
    ExternalApiKeyRepository,
    WorkspaceSettingsRepository,
)


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


class StartCddMoleculeImport:
    """Validate CDD config and start the import workflow.

    The actual import runs in a Temporal workflow. This use case:
    1. Validates CDD vault config (vault_id + API key)
    2. Returns the secret_ref + vault_id for the workflow to use

    The API route layer starts the Temporal workflow.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        secret_provider: SecretProvider,
        settings_repo: WorkspaceSettingsRepository,
        api_key_repo: ExternalApiKeyRepository,
    ) -> None:
        self._uow = uow
        self._secret_provider = secret_provider
        self._settings_repo = settings_repo
        self._api_key_repo = api_key_repo

    async def __call__(
        self,
        input: StartCddMoleculeImportCommand,
        auth: AuthContext | None = None,
    ) -> Result[CddImportConfig, DomainError]:
        """Validate CDD config. Returns CddImportConfig on success."""
        require_editor(auth)

        if input.import_mode not in ("full_vault", "filtered"):
            return Failure(ValidationError(f"Invalid import_mode: {input.import_mode}"))

        async with self._uow:
            config_result = await check_cdd_configured(
                workspace_id=input.workspace_id,
                settings_repo=self._settings_repo,
                api_key_repo=self._api_key_repo,
                secret_provider=self._secret_provider,
            )

        if isinstance(config_result, Failure):
            return config_result

        vault_id, _api_key = config_result.unwrap()
        secret_ref = f"{input.workspace_id}:cdd_vault"

        return Success(CddImportConfig(vault_id=vault_id, secret_ref=secret_ref))
