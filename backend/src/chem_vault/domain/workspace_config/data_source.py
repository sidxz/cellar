"""DataSource aggregate — external data source integration configuration.

Defines how an external system (CDD Vault, ChEMBL, PubChem, etc.) maps
its fields and IDs to internal Chem-Vault entities.  Admin-configurable
via entity mappings; import pipelines read this config at runtime.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.events import (
    DataSourceCreated,
    DataSourceDeactivated,
    DataSourceUpdated,
)

__all__ = [
    "DataSource",
    "DataSourceType",
    "EntityMapping",
    "FieldMapping",
    "IdStorageConfig",
]

# Sentinel for "not provided" in update()
UNSET = object()


class DataSourceType(StrEnum):
    CDD_VAULT = "cdd_vault"
    CHEMBL = "chembl"
    PUBCHEM = "pubchem"
    CUSTOM = "custom"


@dataclass(frozen=True)
class IdStorageConfig:
    """How to store the source's entity ID on our entity."""

    storage_type: str  # "identifier" | "custom_field"
    identifier_type: str | None = None  # for MoleculeIdentifier
    custom_field_name: str | None = None  # for custom_fields JSONB

    def to_dict(self) -> dict[str, Any]:
        return {
            "storage_type": self.storage_type,
            "identifier_type": self.identifier_type,
            "custom_field_name": self.custom_field_name,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IdStorageConfig:
        return cls(
            storage_type=d.get("storage_type", "identifier"),
            identifier_type=d.get("identifier_type"),
            custom_field_name=d.get("custom_field_name"),
        )


@dataclass(frozen=True)
class FieldMapping:
    """Maps one source field to one target field.

    Source fields support pipe-separated fallback chains
    (``"smiles|cxsmiles"``) and dot notation for nested access
    (``"batch_fields.Amount"``).
    """

    source_field: str  # e.g. "name|cdd_registry_number", "batch_fields.Amount"
    target_field: str  # e.g. "name", "amount_value"
    target_type: str  # "core" | "custom_field" | "identifier"

    def to_dict(self) -> dict[str, str]:
        return {
            "source_field": self.source_field,
            "target_field": self.target_field,
            "target_type": self.target_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FieldMapping:
        return cls(
            source_field=d["source_field"],
            target_field=d["target_field"],
            target_type=d["target_type"],
        )


@dataclass
class EntityMapping:
    """Mapping config for one entity type within a data source.

    ``parent_path`` tells the mapper where to find this entity within
    its parent's JSON.  For example a batch mapping with
    ``parent_path="batches"`` means the mapper looks up
    ``parent_obj["batches"]`` to get the list of batch objects.
    Supports the same dot-notation and pipe-fallback syntax as
    ``FieldMapping.source_field``.
    """

    entity_type: str  # "molecule" | "batch" | "plate"
    id_field: str  # source field holding the external ID
    id_storage: IdStorageConfig
    field_mappings: list[FieldMapping] = field(default_factory=list)
    parent_path: str | None = None  # where this entity lives in parent JSON

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "entity_type": self.entity_type,
            "id_field": self.id_field,
            "id_storage": self.id_storage.to_dict(),
            "field_mappings": [fm.to_dict() for fm in self.field_mappings],
        }
        if self.parent_path is not None:
            d["parent_path"] = self.parent_path
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EntityMapping:
        return cls(
            entity_type=d["entity_type"],
            id_field=d["id_field"],
            id_storage=IdStorageConfig.from_dict(d.get("id_storage", {})),
            field_mappings=[
                FieldMapping.from_dict(fm) for fm in d.get("field_mappings", [])
            ],
            parent_path=d.get("parent_path"),
        )


class DataSource(AggregateRoot):
    """Aggregate root for external data source integration configuration.

    Each DataSource represents a linked external system (e.g. a CDD Vault,
    ChEMBL).  It holds connection config, an optional API key reference,
    and per-entity field mappings that import pipelines use at runtime.

    Invariants:
        - name is unique per workspace
        - source_type is immutable after creation
        - entity_mappings JSONB is the single source of truth for field mapping
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        name: str,
        source_type: str,
        config: dict[str, Any] | None = None,
        api_key_name: str | None = None,
        is_active: bool = True,
        entity_mappings: list[EntityMapping] | None = None,
        created_by: uuid.UUID,
        version: int = 1,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(
            id=id,
            version=version,
            created_at=created_at,
            updated_at=updated_at,
        )
        self.workspace_id = workspace_id
        self.name = name
        self.source_type = source_type
        self.config = config or {}
        self.api_key_name = api_key_name
        self.is_active = is_active
        self.entity_mappings = entity_mappings or []
        self.created_by = created_by

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        source_type: str,
        config: dict[str, Any] | None = None,
        api_key_name: str | None = None,
        entity_mappings: list[EntityMapping] | None = None,
        created_by: uuid.UUID,
    ) -> DataSource:
        """Generic factory — used for custom source types or when caller
        provides explicit entity_mappings."""
        if not name or not name.strip():
            raise ValidationError("name must not be empty")
        if not source_type or not source_type.strip():
            raise ValidationError("source_type must not be empty")

        ds = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            name=name.strip(),
            source_type=source_type.strip(),
            config=config,
            api_key_name=api_key_name.strip() if api_key_name else None,
            entity_mappings=entity_mappings or [],
            created_by=created_by,
        )
        ds.register_event(
            DataSourceCreated(
                aggregate_id=ds.id,
                aggregate_type="DataSource",
                workspace_id=workspace_id,
                name=ds.name,
                source_type=ds.source_type,
            )
        )
        return ds

    @classmethod
    def create_cdd_vault(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        vault_id: str,
        api_key_name: str,
        created_by: uuid.UUID,
    ) -> DataSource:
        """Factory with CDD Vault default entity mappings."""
        if not vault_id or not vault_id.strip():
            raise ValidationError("vault_id must not be empty")
        if not api_key_name or not api_key_name.strip():
            raise ValidationError("api_key_name must not be empty")

        return cls.create(
            workspace_id=workspace_id,
            name=name,
            source_type=DataSourceType.CDD_VAULT,
            config={"vault_id": vault_id.strip()},
            api_key_name=api_key_name,
            entity_mappings=_cdd_vault_defaults(),
            created_by=created_by,
        )

    @classmethod
    def create_chembl(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        created_by: uuid.UUID,
    ) -> DataSource:
        """Factory with ChEMBL default entity mappings (public, no API key)."""
        return cls.create(
            workspace_id=workspace_id,
            name=name,
            source_type=DataSourceType.CHEMBL,
            config={},
            api_key_name=None,
            entity_mappings=_chembl_defaults(),
            created_by=created_by,
        )

    # ------------------------------------------------------------------
    # Mutation commands
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str | object = UNSET,
        is_active: bool | object = UNSET,
        config: dict[str, Any] | object = UNSET,
        api_key_name: str | None | object = UNSET,
        entity_mappings: list[EntityMapping] | object = UNSET,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if name is not UNSET:
            name_str = str(name).strip()
            if not name_str:
                raise ValidationError("name must not be empty")
            self.name = name_str
        if is_active is not UNSET:
            self.is_active = bool(is_active)
        if config is not UNSET:
            self.config = dict(config)  # type: ignore[arg-type]
        if api_key_name is not UNSET:
            if api_key_name is None:
                self.api_key_name = None
            else:
                self.api_key_name = str(api_key_name).strip() or None
        if entity_mappings is not UNSET:
            self.entity_mappings = list(entity_mappings)  # type: ignore[arg-type]

        self.updated_at = datetime.now(timezone.utc)
        self.register_event(
            DataSourceUpdated(
                aggregate_id=self.id,
                aggregate_type="DataSource",
                workspace_id=self.workspace_id,
                name=self.name,
            )
        )

    def deactivate(self) -> None:
        """Soft-disable this data source."""
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)
        self.register_event(
            DataSourceDeactivated(
                aggregate_id=self.id,
                aggregate_type="DataSource",
                workspace_id=self.workspace_id,
                name=self.name,
            )
        )

    def activate(self) -> None:
        """Re-enable a previously deactivated data source."""
        self.is_active = True
        self.updated_at = datetime.now(timezone.utc)
        self.register_event(
            DataSourceUpdated(
                aggregate_id=self.id,
                aggregate_type="DataSource",
                workspace_id=self.workspace_id,
                name=self.name,
            )
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_entity_mapping(self, entity_type: str) -> EntityMapping | None:
        """Return the EntityMapping for a given entity type, or None."""
        for em in self.entity_mappings:
            if em.entity_type == entity_type:
                return em
        return None


# ======================================================================
# Default templates — kept as module-level functions for testability
# ======================================================================


def _cdd_vault_defaults() -> list[EntityMapping]:
    """Default entity mappings for a CDD Vault data source.

    Maps standard CDD fields that are present in all vault exports.
    Vault-specific custom fields (``batch_fields.*``, ``molecule_fields.*``)
    should be added by the admin via the Data Source UI.

    Source fields use pipe syntax for fallback chains:
    ``"smiles|cxsmiles"`` means try ``smiles`` first, fall back to ``cxsmiles``.
    Dot notation accesses nested dicts: ``"batch_fields.Purity >"``.
    """
    return [
        EntityMapping(
            entity_type="molecule",
            id_field="id",
            id_storage=IdStorageConfig("custom_field", None, "cdd_molecule_id"),
            field_mappings=[
                FieldMapping("name|cdd_registry_number", "name", "core"),
                FieldMapping("smiles|cxsmiles", "smiles", "core"),
                FieldMapping("synonyms", "custom", "identifier"),
                FieldMapping("modified_at", "modified_at", "core"),
            ],
        ),
        EntityMapping(
            entity_type="batch",
            id_field="id",
            id_storage=IdStorageConfig("custom_field", None, "cdd_batch_id"),
            parent_path="batches",
            field_mappings=[
                FieldMapping("molecule_batch_identifier|name", "vendor_catalog_number", "core"),
                FieldMapping("salt_name", "salt_name", "core"),
            ],
        ),
        EntityMapping(
            entity_type="plate",
            id_field="id",
            id_storage=IdStorageConfig("custom_field", None, "cdd_plate_id"),
            parent_path="plates",
            field_mappings=[
                FieldMapping("name", "barcode", "core"),
                FieldMapping("name", "plate_label", "core"),
            ],
        ),
        EntityMapping(
            entity_type="well",
            id_field="",
            id_storage=IdStorageConfig("custom_field", None, None),
            parent_path="wells",
            field_mappings=[
                FieldMapping("row", "row", "core"),
                FieldMapping("col", "col", "core"),
                FieldMapping("batch", "cdd_batch_id", "core"),
            ],
        ),
    ]


def _chembl_defaults() -> list[EntityMapping]:
    """Default entity mappings for a ChEMBL data source."""
    return [
        EntityMapping(
            entity_type="molecule",
            id_field="molecule_chembl_id",
            id_storage=IdStorageConfig("identifier", "chembl_id", None),
            field_mappings=[
                FieldMapping("pref_name", "name", "core"),
                FieldMapping("canonical_smiles", "smiles", "core"),
            ],
        ),
    ]


def get_default_template(source_type: str) -> list[EntityMapping]:
    """Return the default entity mappings for a source type.

    Used by the API templates endpoint so the UI can preview defaults
    before the admin commits to creating a DataSource.
    """
    templates: dict[str, Any] = {
        DataSourceType.CDD_VAULT: _cdd_vault_defaults,
        DataSourceType.CHEMBL: _chembl_defaults,
    }
    factory = templates.get(source_type)
    if factory is None:
        return []
    return factory()
