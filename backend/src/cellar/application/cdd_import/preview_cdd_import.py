"""PreviewCddImport query -- a sample of vault molecules, mapped as a run would map them.

Reads up to ``SAMPLE_SIZE`` molecules (the named ones, else the vault's first) and returns
them as the same preview rows a file upload gets: one row per CDD batch, or one for a
molecule without batches. Nothing is stored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.cdd_import.errors import CddAuthError, CddConnectionError, CddNotFoundError
from cellar.application.cdd_import.gateway import CddSampleGateway
from cellar.application.cdd_import.molecule_identifiers import (
    clean_identifiers,
    match_identifiers,
)
from cellar.application.cdd_import.molecule_mapper import (
    compute_labels,
    compute_names,
    map_cdd_molecules,
)
from cellar.application.chemical_registration.bulk_column_mapping import ColumnMapping
from cellar.application.chemical_registration.preview_bulk_registration_file import (
    ParsedItemDTO,
    PreviewBulkRegistrationFileOutcome,
)
from cellar.application.shared.query import Query
from cellar.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
    GetDataSourceForImportQuery,
)
from cellar.domain.shared.errors import DomainError, ValidationError
from cellar.domain.workspace_config.data_source import DataSourceType, EntityMapping

SAMPLE_SIZE = 20


@dataclass(frozen=True, kw_only=True)
class PreviewCddImportQuery(Query):
    workspace_id: uuid.UUID
    names: list[str] | None = None  # molecule names or synonyms; None = the vault's first


class PreviewCddImport:
    def __init__(self, gateway: CddSampleGateway, get_data_source: GetDataSourceForImport) -> None:
        self._gateway = gateway
        self._get_data_source = get_data_source

    async def __call__(
        self, input: PreviewCddImportQuery, auth: AuthContext | None = None
    ) -> Result[PreviewBulkRegistrationFileOutcome, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        ds_result = await self._get_data_source(
            GetDataSourceForImportQuery(
                workspace_id=input.workspace_id, source_type=DataSourceType.CDD_VAULT
            )
        )
        if isinstance(ds_result, Failure):
            return ds_result
        config = ds_result.unwrap()
        ds = config.data_source
        vault_id = str(ds.config.get("vault_id", ""))
        if not vault_id:
            return Failure(ValidationError("CDD Vault data source has no vault_id configured"))
        if not ds.registration_mapping:
            return Failure(
                ValidationError(
                    "The CDD Vault data source has no field mapping yet. "
                    "An admin sets it on the data source page."
                )
            )
        mappings = {em.entity_type: em for em in ds.entity_mappings}
        id_mapping: EntityMapping | None = mappings.get("molecule")
        if id_mapping is None:
            return Failure(ValidationError("CDD Vault data source has no molecule ID mapping"))
        api_key = config.api_key or ""

        try:
            molecule_ids: list[int] | None = None
            names = clean_identifiers(input.names or [])
            if names:
                found = await self._gateway.find_molecules_by_names(vault_id, api_key, names)
                # As a run attributes them: a looser vault match is left out.
                molecule_ids = match_identifiers(names, found).molecule_ids[:SAMPLE_SIZE]
                if not molecule_ids:
                    return Failure(ValidationError("None of those molecules are in the vault"))
            objects = await self._gateway.sample_molecules(
                vault_id, api_key, molecule_ids, SAMPLE_SIZE
            )
        except CddAuthError:
            return Failure(ValidationError("CDD Vault API key is invalid or expired"))
        except CddNotFoundError:
            return Failure(ValidationError("CDD Vault ID not found"))
        except CddConnectionError:
            return Failure(ValidationError("Could not connect to CDD Vault"))

        mapping = ColumnMapping.from_dict({"columns": ds.registration_mapping})
        mapped, _ = map_cdd_molecules(
            objects,
            mapping,
            id_mapping=id_mapping,
            batch_id_mapping=mappings.get("batch"),
            labels=compute_labels(objects, mapping),
            names=compute_names(objects, mapping, id_mapping),
        )

        items: list[ParsedItemDTO] = []
        for mol in mapped:
            base = {
                "name": mol.name,
                "smiles": mol.smiles,
                "molecule_type": mol.molecule_type,
                "external_ids": mol.external_ids,
            }
            if not mol.batches:
                items.append(
                    ParsedItemDTO(
                        row_index=len(items),
                        file_row=len(items) + 1,
                        warnings=mol.warnings,
                        **base,
                    )
                )
            for i, b in enumerate(mol.batches):
                items.append(
                    ParsedItemDTO(
                        row_index=len(items),
                        file_row=len(items) + 1,
                        batch_ids=b.batch_ids,
                        amount_value=b.amount_value,
                        amount_unit=b.amount_unit,
                        salt_code=b.salt_code,
                        salt_stoichiometry=b.salt_stoichiometry,
                        purity=b.purity,
                        batch_source=b.batch_source,
                        appearance=b.appearance,
                        warnings=[*(mol.warnings if i == 0 else ()), *b.warnings],
                        **base,
                    )
                )
        return Success(PreviewBulkRegistrationFileOutcome(items, len(items), 0))
