"""Shared CDD vault configuration check for import use cases."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.domain.workspace_config.repository import (
    ExternalApiKeyRepository,
    WorkspaceSettingsRepository,
)


async def check_cdd_configured(
    workspace_id: uuid.UUID,
    settings_repo: WorkspaceSettingsRepository,
    api_key_repo: ExternalApiKeyRepository,
    secret_provider: SecretProvider,
) -> Result[tuple[str, str], DomainError]:
    """Verify CDD Vault integration is configured. Returns (vault_id, api_key) on success."""
    settings = await settings_repo.find_by_id(workspace_id)
    if settings is None or not settings.cdd_vault_id:
        return Failure(
            ValidationError("CDD Vault ID is not configured. Go to Admin > Workspace Settings.")
        )

    api_key_entry = await api_key_repo.find_by_key_name(workspace_id, "cdd_vault")
    if api_key_entry is None or not api_key_entry.is_active:
        return Failure(
            ValidationError("CDD Vault API key is not configured or inactive. Go to Admin > API Keys.")
        )

    secret_key = f"{workspace_id}:cdd_vault"
    api_key = await secret_provider.get_secret(secret_key)
    if api_key is None:
        return Failure(
            ValidationError("CDD Vault API key secret not found. Re-add the key in Admin > API Keys.")
        )

    return Success((settings.cdd_vault_id, api_key))
