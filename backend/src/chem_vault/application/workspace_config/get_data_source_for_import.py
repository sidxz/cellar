"""GetDataSourceForImport — resolve active data source + API key for import pipelines.

Replaces the previous _check_config.py pattern. Returns the DataSource
aggregate with its entity_mappings, plus the resolved API key secret.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.domain.workspace_config.data_source import DataSource
from chem_vault.domain.workspace_config.repository import (
    DataSourceRepository,
    ExternalApiKeyRepository,
)


@dataclass(frozen=True, kw_only=True)
class GetDataSourceForImportQuery(Query):
    workspace_id: uuid.UUID
    source_type: str


@dataclass(frozen=True)
class DataSourceImportConfig:
    """Resolved config for an import pipeline."""

    data_source: DataSource
    api_key: str | None  # resolved secret value (None for public sources)


class GetDataSourceForImport:
    def __init__(
        self,
        uow: UnitOfWork,
        ds_repo: DataSourceRepository,
        api_key_repo: ExternalApiKeyRepository,
        secret_provider: SecretProvider,
    ) -> None:
        self._uow = uow
        self._ds_repo = ds_repo
        self._api_key_repo = api_key_repo
        self._secret_provider = secret_provider

    async def __call__(
        self, input: GetDataSourceForImportQuery
    ) -> Result[DataSourceImportConfig, DomainError]:
        async with self._uow:
            ds = await self._ds_repo.find_active_by_source_type(
                input.workspace_id, input.source_type
            )
            if ds is None:
                return Failure(
                    NotFoundError(
                        "DataSource",
                        f"No active data source of type '{input.source_type}' configured",
                    )
                )

            api_key: str | None = None
            if ds.api_key_name:
                key_entry = await self._api_key_repo.find_by_key_name(
                    input.workspace_id, ds.api_key_name
                )
                if key_entry is None or not key_entry.is_active:
                    return Failure(
                        ValidationError(
                            f"API key '{ds.api_key_name}' not found or inactive"
                        )
                    )
                secret_ref = f"{input.workspace_id}:{ds.api_key_name}"
                api_key = await self._secret_provider.get_secret(secret_ref)
                if not api_key:
                    return Failure(
                        ValidationError(
                            f"API key secret for '{ds.api_key_name}' is empty"
                        )
                    )

            return Success(DataSourceImportConfig(data_source=ds, api_key=api_key))
