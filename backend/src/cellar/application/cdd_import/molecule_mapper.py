"""Pure mapper: CDD Vault molecule JSON -> registration rows.

No I/O. Which vault field goes where is the CDD data source's registration mapping
(``ColumnMapping``; headers are vault field paths, ``batch.<path>`` for batch fields),
applied by the file importer's ``extract_row``. The molecule/batch ``EntityMapping``s
only say where the vault ids and the batches are.

Only the vault's own IDs decide which compound or batch a row is (CDD mapper spec
2026-11-18 §3a): the molecule's vault id and name, the batch's vault id and CDD batch
name. Every other mapped ID is stored only (``"decides": False``).

``_resolve_field`` / ``_collect_fields`` also serve the plate mapper.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from cellar.application.cdd_import.registration_mapping import BATCH_PREFIX
from cellar.application.chemical_registration.bulk_column_mapping import (
    ColumnMapping,
    ColumnTarget,
    ExtractedRow,
    MappedColumn,
    extract_row,
)
from cellar.domain.workspace_config.data_source import EntityMapping

__all__ = [
    "MappedBatch",
    "MappedMolecule",
    "MoleculeMapWarning",
    "compute_labels",
    "compute_names",
    "map_cdd_molecules",
]

# The batch field whose value decides which batch a row is: the CDD batch name.
DECIDING_BATCH_PATH = f"{BATCH_PREFIX}molecule_batch_identifier"

# CDD defaults as columns read before the mapping's own, so a mapped value wins: a
# molecule without a name is "EXT-<vault id>", a batch's source is "purchased".
_EXT_NAME = MappedColumn("\0ext-name", ColumnTarget.NAME)
_PURCHASED = MappedColumn("\0purchased", ColumnTarget.BATCH_SOURCE)


@dataclass(frozen=True)
class MappedBatch:
    """One batch from a CDD molecule's ``batches`` array."""

    cdd_batch_id: int | None
    # {"identifier", "source", "identifier_type"?, "decides"} — see row_batch.py
    batch_ids: list[dict[str, Any]] = field(default_factory=list)
    amount_value: float | None = None
    amount_unit: str = "mg"
    purity: float | None = None
    batch_source: str = "purchased"
    salt_code: str | None = None
    salt_stoichiometry: int = 1
    appearance: str | None = None
    warnings: list[str] = field(default_factory=list)  # values not stored, and why


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
    # {"identifier", "identifier_type", "source"?, "decides"?}
    external_ids: list[dict[str, Any]] = field(default_factory=list)
    batches: list[MappedBatch] = field(default_factory=list)
    cdd_modified_at: str | None = None  # ISO timestamp from source (the sync watermark)
    warnings: list[str] = field(default_factory=list)  # values not stored, and why


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def map_cdd_molecules(
    objects: list[dict[str, Any]],
    mapping: ColumnMapping,
    *,
    id_mapping: EntityMapping,
    batch_id_mapping: EntityMapping | None,
    labels: Mapping[str, int] | None = None,
    names: Mapping[str, int] | None = None,
) -> tuple[list[MappedMolecule], list[MoleculeMapWarning]]:
    """Map CDD molecule objects with the registration ``mapping``.

    ``id_mapping`` / ``batch_id_mapping``: the molecule / batch ``EntityMapping``
    (vault id field, its storage, where batches are); no batch mapping, no batches.
    ``labels``: ``compute_labels`` of the run — those compound IDs are not stored.
    ``names``: ``compute_names`` of the run — a compound ID that is another molecule's
    name or vault id is not stored.
    """
    cols = _split(mapping)
    mapped: list[MappedMolecule] = []
    warnings: list[MoleculeMapWarning] = []
    for obj in objects:
        mol, mol_warnings = _map_single(
            obj, cols, id_mapping, batch_id_mapping, labels or {}, names or {}
        )
        mapped.append(mol)
        warnings.extend(mol_warnings)
    return mapped, warnings


def compute_labels(objects: list[dict[str, Any]], mapping: ColumnMapping) -> dict[str, int]:
    """Compound-ID values (lower-cased) on 2+ of ``objects`` → on how many: series
    labels such as "Benzimidazole series", not IDs (spec §3b). Case-insensitive, as
    compound lookup by identifier is."""
    molecule_cols, _, _ = _split(mapping)
    counts: Counter[str] = Counter()
    for obj in objects:
        row = _row(_getter(obj, 0), molecule_cols)
        counts.update({e["identifier"].lower() for e in _compound_ids(row)})
    return {v: n for v, n in counts.items() if n > 1}


def compute_names(
    objects: list[dict[str, Any]], mapping: ColumnMapping, id_mapping: EntityMapping
) -> dict[str, int]:
    """Each molecule's deciding values — its name and vault id, lower-cased — → its vault
    id. Stored on another compound, such a value would make that molecule's own row
    find (or conflict with) the wrong compound, whichever is read first.

    ponytail: only the run's own molecules are known; a value equal to the name of a
    molecule outside the run (an earlier Sync / Specific run, or one not read yet) is
    still stored when free. A Full run sees every name; a vault-wide name index would
    close the gap for the others.
    """
    molecule_cols, _, _ = _split(mapping)
    names: dict[str, int] = {}
    for obj in objects:
        entity_id: int = _resolve_field(obj, id_mapping.id_field) or 0
        row = _row(_getter(obj, entity_id), molecule_cols)
        for value in (row.name, str(entity_id) if entity_id else None):
            if value:
                names.setdefault(value.lower(), entity_id)
    return names


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


def _split(mapping: ColumnMapping) -> tuple[ColumnMapping, ColumnMapping, ColumnMapping]:
    """(molecule columns, deciding batch-ID columns, other batch columns), each
    behind the CDD defaults. Levels never mix within a header (validated on save)."""
    molecule: list[MappedColumn] = []
    deciding: list[MappedColumn] = []
    other: list[MappedColumn] = []
    for c in mapping.columns:
        paths = [p.strip() for p in c.header.split("|")]
        if not paths[0].startswith(BATCH_PREFIX):
            molecule.append(c)
        elif c.target == ColumnTarget.BATCH_ID and DECIDING_BATCH_PATH in paths:
            deciding.append(c)
        else:
            other.append(c)
    return (
        ColumnMapping((_EXT_NAME, *molecule)),
        ColumnMapping((_EXT_NAME, *deciding)),
        ColumnMapping((_EXT_NAME, _PURCHASED, *other)),
    )


def _getter(
    obj: dict[str, Any], entity_id: int, prefix: str = ""
) -> Callable[[str], str | list[str] | None]:
    """``extract_row``'s cell reader over one vault object; ``prefix`` is stripped
    from each ``|`` alternative (``batch.`` for a batch)."""

    def get(header: str) -> str | list[str] | None:
        if header == _EXT_NAME.header:
            return f"EXT-{entity_id}"
        if header == _PURCHASED.header:
            return "purchased"
        path = "|".join(p.strip().removeprefix(prefix) for p in header.split("|"))
        val = _resolve_field(obj, path)
        if val is None:
            return None
        if isinstance(val, list):
            return [str(v) for v in val if v is not None]
        return val.strip() if isinstance(val, str) else str(val)

    return get


def _row(get: Callable[[str], str | list[str] | None], mapping: ColumnMapping) -> ExtractedRow:
    row = extract_row(get, mapping)
    assert row is not None  # the EXT name column always gives a name
    return row


def _compound_ids(row: ExtractedRow) -> list[dict[str, Any]]:
    """The row's mapped compound IDs, less its own name (CDD synonyms repeat it)."""
    return [e for e in row.external_ids if e["identifier"] != row.name]


# ---------------------------------------------------------------------------
# Molecule and batch mapping
# ---------------------------------------------------------------------------


def _map_single(
    obj: dict[str, Any],
    cols: tuple[ColumnMapping, ColumnMapping, ColumnMapping],
    id_mapping: EntityMapping,
    batch_id_mapping: EntityMapping | None,
    labels: Mapping[str, int],
    names: Mapping[str, int],
) -> tuple[MappedMolecule, list[MoleculeMapWarning]]:
    molecule_cols, deciding_cols, batch_cols = cols
    entity_id: int = _resolve_field(obj, id_mapping.id_field) or 0
    row = _row(_getter(obj, entity_id), molecule_cols)

    warnings: list[MoleculeMapWarning] = []
    if row.name == f"EXT-{entity_id}":
        warnings.append(MoleculeMapWarning(entity_id, "No name field; using external ID"))
    if not row.smiles:
        warnings.append(MoleculeMapWarning(entity_id, "No SMILES — registering as undisclosed"))

    # The vault id decides (with the name, promoted by the registration).
    storage = id_mapping.id_storage
    id_type = (
        storage.identifier_type
        if storage.storage_type == "identifier"
        else storage.custom_field_name
    )
    external_ids: list[dict[str, Any]] = (
        [{"identifier": str(entity_id), "identifier_type": id_type}] if id_type else []
    )
    not_stored = list(row.warnings)
    for e in _compound_ids(row):
        value = e["identifier"].lower()
        n = labels.get(value)
        if names.get(value, entity_id) != entity_id:
            not_stored.append(
                f"'{e['identifier']}' is the name of another compound in the vault; "
                "not stored as an ID"
            )
        elif n:
            not_stored.append(
                f"'{e['identifier']}' is on {n} compounds in the vault; not stored as an ID"
            )
        else:
            external_ids.append({**e, "decides": False})

    batches: list[MappedBatch] = []
    if batch_id_mapping is not None and batch_id_mapping.parent_path:
        raw = _resolve_field(obj, batch_id_mapping.parent_path) or []
        batches = [
            _map_batch(b, entity_id, batch_id_mapping.id_field, deciding_cols, batch_cols)
            for b in raw
        ]

    return (
        MappedMolecule(
            cdd_molecule_id=entity_id,
            name=row.name,
            smiles=row.smiles,
            molecule_type=row.molecule_type,
            external_ids=external_ids,
            batches=batches,
            cdd_modified_at=obj.get("modified_at"),
            warnings=not_stored,
        ),
        warnings,
    )


def _map_batch(
    b: dict[str, Any],
    entity_id: int,
    id_field: str,
    deciding_cols: ColumnMapping,
    batch_cols: ColumnMapping,
) -> MappedBatch:
    get = _getter(b, entity_id, BATCH_PREFIX)
    named = _row(get, deciding_cols)
    row = _row(get, batch_cols)
    cdd_batch_id = _resolve_field(b, id_field)
    batch_ids: list[dict[str, Any]] = [
        *({**x, "decides": True} for x in named.batch_ids),
        *({**x, "decides": False} for x in row.batch_ids),
    ]
    if cdd_batch_id is not None:  # also kept in custom_fields: plates resolve by it
        batch_ids.append(
            {
                "identifier": str(cdd_batch_id),
                "source": "CDD import",
                "identifier_type": "cdd_batch_id",
                "decides": True,
            }
        )
    return MappedBatch(
        cdd_batch_id=cdd_batch_id,
        batch_ids=batch_ids,
        amount_value=row.amount_value,
        amount_unit=row.amount_unit,
        purity=row.purity,
        batch_source=row.batch_source,
        # "Unknown Salt" is CDD's placeholder for none
        salt_code=row.salt_code if row.salt_code != "Unknown Salt" else None,
        salt_stoichiometry=row.salt_stoichiometry,
        appearance=row.appearance,
        warnings=[*named.warnings, *row.warnings],
    )
