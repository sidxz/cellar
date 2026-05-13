"""Shared CDD vault configuration check for import use cases.

Delegates to GetDataSourceForImport (DataSource config system).
Returns (vault_id, api_key) for backward compatibility with molecule import.
"""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from cellar.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
    GetDataSourceForImportQuery,
)
from cellar.domain.shared.errors import DomainError
from cellar.domain.workspace_config.data_source import DataSourceType


async def check_cdd_configured(
    workspace_id: uuid.UUID,
    get_data_source: GetDataSourceForImport,
) -> Result[tuple[str, str], DomainError]:
    """Verify CDD Vault integration is configured. Returns (vault_id, api_key) on success."""
    result = await get_data_source(
        GetDataSourceForImportQuery(
            workspace_id=workspace_id,
            source_type=DataSourceType.CDD_VAULT,
        )
    )

    if isinstance(result, Failure):
        return result

    config = result.unwrap()
    vault_id = str(config.data_source.config.get("vault_id", ""))
    if not vault_id:
        from cellar.domain.shared.errors import ValidationError

        return Failure(ValidationError("CDD Vault data source has no vault_id configured"))

    return Success((vault_id, config.api_key or ""))
