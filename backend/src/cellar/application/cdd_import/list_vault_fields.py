"""ListVaultFields query -- the fields a CDD vault offers the registration mapper.

Built-in molecule/batch fields plus the vault's own (``molecule_fields.<Name>`` /
``batch.batch_fields.<Name>``). If CDD's answer has an unexpected shape the
built-ins are returned alone and the shape is logged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.cdd_import.errors import CddAuthError, CddConnectionError, CddNotFoundError
from cellar.application.cdd_import.gateway import CddFieldsGateway
from cellar.application.cdd_import.registration_mapping import BATCH_PREFIX
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError
from cellar.domain.shared.secret_provider import SecretProvider
from cellar.domain.workspace_config.data_source import DataSourceType
from cellar.domain.workspace_config.repository import DataSourceRepository

log = structlog.get_logger()


@dataclass(frozen=True)
class VaultField:
    path: str
    label: str


@dataclass(frozen=True)
class VaultFields:
    molecule: list[VaultField]
    batch: list[VaultField]


_MOLECULE_BUILTINS = [
    VaultField("name", "Name"),
    VaultField("synonyms", "Synonyms"),
    VaultField("smiles|cxsmiles", "SMILES"),
    VaultField("cdd_registry_number", "CDD registry number"),
]
_BATCH_BUILTINS = [
    VaultField(f"{BATCH_PREFIX}name", "Batch name"),
    VaultField(f"{BATCH_PREFIX}molecule_batch_identifier", "Molecule-Batch ID"),
    VaultField(f"{BATCH_PREFIX}salt_name", "Salt name"),
    VaultField(f"{BATCH_PREFIX}formula_weight", "Formula weight"),
]


def _names(group: object) -> list[str] | None:
    """Field names of one group: a list of {name} objects or of strings; None = unknown shape."""
    if not isinstance(group, list):
        return None
    names: list[str] = []
    for item in group:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
        else:
            return None
    return [n for n in names if n.strip()]


def build_vault_fields(raw: Any) -> VaultFields:
    molecule = list(_MOLECULE_BUILTINS)
    batch = list(_BATCH_BUILTINS)
    if not isinstance(raw, dict):
        log.warning("cdd_vault_fields_unexpected_shape", got=type(raw).__name__)
        return VaultFields(molecule, batch)
    for group, prefix, out in (
        ("molecule", "molecule_fields.", molecule),
        ("batch", f"{BATCH_PREFIX}batch_fields.", batch),
    ):
        names = _names(raw.get(group))
        if names is None:
            log.warning("cdd_vault_fields_unexpected_shape", group=group)
            continue
        # "|" separates alternative fields in a path, so a name holding one can't be read.
        unreadable = [n for n in names if "|" in n]
        if unreadable:
            log.warning("cdd_vault_fields_unreadable_names", group=group, names=unreadable)
        out.extend(VaultField(f"{prefix}{n}", n) for n in names if "|" not in n)
    return VaultFields(molecule, batch)


@dataclass(frozen=True, kw_only=True)
class ListVaultFieldsQuery(Query):
    workspace_id: uuid.UUID
    data_source_id: uuid.UUID


class ListVaultFields:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: DataSourceRepository,
        gateway: CddFieldsGateway,
        secret_provider: SecretProvider,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._gateway = gateway
        self._secret_provider = secret_provider

    async def __call__(
        self, input: ListVaultFieldsQuery, auth: AuthContext | None = None
    ) -> Result[VaultFields, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            ds = await self._repo.find_by_id_in_workspace(input.workspace_id, input.data_source_id)
        if ds is None:
            return Failure(NotFoundError("DataSource", str(input.data_source_id)))
        vault_id = str(ds.config.get("vault_id", ""))
        if ds.source_type != DataSourceType.CDD_VAULT or not vault_id or not ds.api_key_name:
            return Failure(ValidationError("Not a configured CDD Vault data source"))
        api_key = await self._secret_provider.get_secret(f"{input.workspace_id}:{ds.api_key_name}")
        if not api_key:
            return Failure(
                ValidationError(f"API key secret for '{ds.api_key_name}' is missing or unreadable")
            )
        try:
            raw = await self._gateway.list_fields(vault_id, api_key)
        except CddAuthError:
            return Failure(ValidationError("CDD Vault API key is invalid or expired"))
        except CddNotFoundError:
            return Failure(ValidationError("CDD Vault ID not found"))
        except CddConnectionError:
            return Failure(ValidationError("Could not connect to CDD Vault"))
        return Success(build_vault_fields(raw))
