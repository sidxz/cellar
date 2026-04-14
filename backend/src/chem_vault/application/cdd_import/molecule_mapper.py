"""Pure mapper: CDD Vault molecule JSON -> BulkRegistrationItem DTOs.

No I/O. Maps CDD molecule objects (with embedded batches) into the
application-layer DTOs that the registration pipeline expects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
    skipped: bool = False
    skip_reason: str | None = None


def map_cdd_molecules(
    objects: list[dict[str, Any]],
) -> tuple[list[MappedMolecule], list[MoleculeMapWarning]]:
    """Map a list of CDD molecule JSON objects to registration DTOs.

    Returns (mapped_molecules, warnings).
    """
    mapped: list[MappedMolecule] = []
    warnings: list[MoleculeMapWarning] = []

    for obj in objects:
        mol, mol_warnings = _map_single(obj)
        mapped.append(mol)
        warnings.extend(mol_warnings)

    return mapped, warnings


def _map_single(
    obj: dict[str, Any],
) -> tuple[MappedMolecule, list[MoleculeMapWarning]]:
    """Map a single CDD molecule object."""
    warnings: list[MoleculeMapWarning] = []
    cdd_id: int = obj.get("id", 0)

    # Structure: prefer SMILES, fall back to cxsmiles
    smiles = obj.get("smiles") or obj.get("cxsmiles")

    name = obj.get("name")
    if not name:
        name = obj.get("cdd_registry_number") or f"CDD-{cdd_id}"
        warnings.append(
            MoleculeMapWarning(cdd_id, "No name field; using registry number or CDD ID")
        )

    if not smiles:
        warnings.append(
            MoleculeMapWarning(cdd_id, "No SMILES — registering as undisclosed")
        )

    # External identifiers — CDD molecule ID + synonyms
    external_ids: list[dict[str, str]] = [
        {"identifier": str(cdd_id), "identifier_type": "custom"},
    ]
    # Synonyms often include alternate IDs
    for syn in obj.get("synonyms", []):
        if syn and syn != name:
            external_ids.append({"identifier": syn, "identifier_type": "custom"})

    # Map embedded batches
    batches = _map_batches(obj.get("batches", []))

    return (
        MappedMolecule(
            cdd_molecule_id=cdd_id,
            name=name,
            smiles=smiles,
            external_ids=external_ids,
            batches=batches,
        ),
        warnings,
    )


def _map_batches(raw_batches: list[dict[str, Any]]) -> list[MappedBatch]:
    """Map CDD batch objects to MappedBatch DTOs.

    CDD batch fields (from async export):
        id, class, name, molecule_batch_identifier, owner,
        salt_name, batch_fields (custom dict), projects
    """
    mapped: list[MappedBatch] = []
    for b in raw_batches:
        # CDD uses salt_name (e.g. "Unknown Salt", "HCl"), not salt_code
        salt_name = b.get("salt_name")
        salt_code = salt_name if salt_name and salt_name != "Unknown Salt" else None

        # Custom batch fields may contain purity, amount, etc.
        batch_fields = b.get("batch_fields", {}) or {}

        mapped.append(
            MappedBatch(
                cdd_batch_id=b.get("id", 0),
                batch_name=b.get("molecule_batch_identifier") or b.get("name"),
                amount_value=_safe_float(batch_fields.get("Amount") or batch_fields.get("amount")),
                amount_unit=batch_fields.get("Amount Unit", "mg") or "mg",
                purity=_safe_float(batch_fields.get("Purity") or batch_fields.get("purity")),
                batch_source="purchased",
                salt_code=salt_code,
                appearance=batch_fields.get("Appearance") or batch_fields.get("appearance"),
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
