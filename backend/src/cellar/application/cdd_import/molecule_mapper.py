"""Pure mapper: CDD Vault molecule JSON -> BulkRegistrationItem DTOs.

No I/O. Maps CDD molecule objects (with embedded batches) into the
application-layer DTOs that the registration pipeline expects.

Field extraction is driven entirely by ``EntityMapping`` config from the
DataSource aggregate.  Source fields support:
  - Dot notation for nested access: ``"batch_fields.Amount"``
  - Pipe-separated fallback chains: ``"smiles|cxsmiles"``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cellar.domain.workspace_config.data_source import EntityMapping

__all__ = [
    "MappedMolecule",
    "MappedBatch",
    "MoleculeMapWarning",
    "map_cdd_molecules",
]


@dataclass(frozen=True)
class MappedBatch:
    """A single batch extracted from a CDD molecule's ``batches`` array."""

    cdd_batch_id: int
    batch_name: str | None = None
    amount_value: float | None = None
    amount_unit: str = "mg"
    purity: float | None = None
    batch_source: str = "purchased"
    salt_code: str | None = None
    salt_stoichiometry: int = 1
    appearance: str | None = None


@dataclass(frozen=True)
class MoleculeMapWarning:
    """A non-fatal mapping issue for a CDD molecule."""

    cdd_molecule_id: int
    reason: str


@dataclass(frozen=True)
class MappedMolecule:
    """A CDD molecule mapped to registration-ready fields."""

    cdd_molecule_id: int
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[dict[str, str]] = field(default_factory=list)
    batches: list[MappedBatch] = field(default_factory=list)
    cdd_modified_at: str | None = None  # ISO timestamp from source
    skipped: bool = False
    skip_reason: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def map_cdd_molecules(
    objects: list[dict[str, Any]],
    molecule_mapping: EntityMapping,
    batch_mapping: EntityMapping | None = None,
) -> tuple[list[MappedMolecule], list[MoleculeMapWarning]]:
    """Map a list of CDD molecule JSON objects to registration DTOs.

    Returns (mapped_molecules, warnings).
    """
    mapped: list[MappedMolecule] = []
    warnings: list[MoleculeMapWarning] = []

    for obj in objects:
        mol, mol_warnings = _map_single(obj, molecule_mapping, batch_mapping)
        mapped.append(mol)
        warnings.extend(mol_warnings)

    return mapped, warnings


# ---------------------------------------------------------------------------
# Field resolution helpers
# ---------------------------------------------------------------------------


def _resolve_field(obj: dict[str, Any], source_field: str) -> Any:
    """Resolve a potentially dotted, pipe-separated field path.

    ``"batch_fields.Amount|batch_fields.amount"`` tries:
      1. obj["batch_fields"]["Amount"]
      2. obj["batch_fields"]["amount"]
    Returns the first non-None value, or None.
    """
    for path in source_field.split("|"):
        val: Any = obj
        for part in path.strip().split("."):
            if isinstance(val, dict):
                val = val.get(part)
            else:
                val = None
                break
        if val is not None:
            return val
    return None


def _collect_fields(
    obj: dict[str, Any],
    mapping: EntityMapping,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Extract core fields and identifier-type fields from *mapping*.

    Returns ``(core_fields, identifier_entries)`` where core_fields is a
    dict keyed by target_field, and identifier_entries is a list of
    ``{"identifier": ..., "identifier_type": ...}`` dicts.
    """
    core: dict[str, Any] = {}
    identifiers: list[dict[str, str]] = []

    for fm in mapping.field_mappings:
        val = _resolve_field(obj, fm.source_field)
        if fm.target_type == "core":
            core[fm.target_field] = val
        elif fm.target_type == "identifier":
            # Value may be a list (e.g. synonyms) or a single string
            items = val if isinstance(val, list) else ([val] if val else [])
            for item in items:
                if item:
                    identifiers.append(
                        {"identifier": str(item), "identifier_type": fm.target_field}
                    )

    return core, identifiers


# ---------------------------------------------------------------------------
# Molecule mapping
# ---------------------------------------------------------------------------


def _map_single(
    obj: dict[str, Any],
    mol_mapping: EntityMapping,
    batch_mapping: EntityMapping | None,
) -> tuple[MappedMolecule, list[MoleculeMapWarning]]:
    """Map a single CDD molecule object."""
    warnings: list[MoleculeMapWarning] = []

    # External ID from id_field
    entity_id: int = _resolve_field(obj, mol_mapping.id_field) or 0

    # Collect mapped fields
    core, extra_ids = _collect_fields(obj, mol_mapping)

    name: str | None = core.get("name")
    smiles: str | None = core.get("smiles")
    modified_at: str | None = core.get("modified_at")

    if not name:
        name = f"EXT-{entity_id}"
        warnings.append(MoleculeMapWarning(entity_id, "No name field; using external ID"))

    if not smiles:
        warnings.append(MoleculeMapWarning(entity_id, "No SMILES — registering as undisclosed"))

    # Build external identifiers list from id_storage config
    external_ids: list[dict[str, str]] = []
    storage = mol_mapping.id_storage
    if storage.storage_type == "identifier" and storage.identifier_type:
        external_ids.append(
            {"identifier": str(entity_id), "identifier_type": storage.identifier_type}
        )
    elif storage.storage_type == "custom_field" and storage.custom_field_name:
        external_ids.append(
            {"identifier": str(entity_id), "identifier_type": storage.custom_field_name}
        )

    # Filter out identifiers that duplicate the name
    for eid in extra_ids:
        if eid["identifier"] != name:
            external_ids.append(eid)

    # Map embedded child entities (e.g. batches) via parent_path
    batches: list[MappedBatch] = []
    if batch_mapping:
        raw = _resolve_field(obj, batch_mapping.parent_path) if batch_mapping.parent_path else []
        batches = _map_batches(raw or [], batch_mapping)

    return (
        MappedMolecule(
            cdd_molecule_id=entity_id,
            name=name,
            smiles=smiles,
            external_ids=external_ids,
            batches=batches,
            cdd_modified_at=modified_at,
        ),
        warnings,
    )


# ---------------------------------------------------------------------------
# Batch mapping
# ---------------------------------------------------------------------------


def _map_batches(
    raw_batches: list[dict[str, Any]],
    batch_mapping: EntityMapping,
) -> list[MappedBatch]:
    """Map batch objects using the batch EntityMapping."""
    mapped: list[MappedBatch] = []

    for b in raw_batches:
        batch_id: int = _resolve_field(b, batch_mapping.id_field) or 0

        core, _ = _collect_fields(b, batch_mapping)

        # Salt: filter placeholder values like "Unknown Salt"
        salt_name = core.get("salt_name")
        salt_code = salt_name if salt_name and salt_name != "Unknown Salt" else None

        mapped.append(
            MappedBatch(
                cdd_batch_id=batch_id,
                batch_name=core.get("vendor_catalog_number"),
                amount_value=_safe_float(core.get("amount_value")),
                amount_unit=core.get("amount_unit") or "mg",
                purity=_safe_float(core.get("purity")),
                batch_source="purchased",
                salt_code=salt_code,
                appearance=core.get("appearance"),
            )
        )
    return mapped


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
