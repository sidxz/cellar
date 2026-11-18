"""The registration mapping stored on a CDD data source.

Same vocabulary as the bulk-registration "Match fields" mapping: ``header`` holds a
vault field path (``name``, ``synonyms``, ``molecule_fields.Alternate Names``, or
``batch.<path>`` for a batch field), ``target`` a phase-1 ``ColumnTarget``.
"""

from __future__ import annotations

from typing import Any

from cellar.application.chemical_registration.bulk_column_mapping import (
    ColumnMapping,
    ColumnTarget,
)
from cellar.domain.shared.errors import ValidationError

BATCH_PREFIX = "batch."

_BATCH_TARGETS = frozenset(
    {
        ColumnTarget.BATCH_ID,
        ColumnTarget.AMOUNT_VALUE,
        ColumnTarget.AMOUNT_UNIT,
        ColumnTarget.SALT_CODE,
        ColumnTarget.SALT_STOICHIOMETRY,
        ColumnTarget.PURITY,
        ColumnTarget.BATCH_SOURCE,
        ColumnTarget.APPEARANCE,
    }
)


def default_cdd_registration_mapping() -> list[dict[str, Any]]:
    """What a new CDD source starts with. Batch Synonym is deliberately absent."""

    def col(header: str, target: str, source: str | None = None) -> dict[str, Any]:
        return {"header": header, "target": target, "source": source, "separator": None}

    return [
        col("name|cdd_registry_number", "name"),
        col("smiles|cxsmiles", "smiles"),
        col("synonyms", "compound_id", "CDD synonym"),
        col(f"{BATCH_PREFIX}molecule_batch_identifier", "batch_id", "CDD batch ID"),
        col(f"{BATCH_PREFIX}salt_name", "salt_code"),
    ]


def validate_registration_mapping(columns: list[dict[str, Any]]) -> ValidationError | None:
    """Phase 1 rules plus the level rule: compound targets read molecule paths,
    batch targets read ``batch.`` paths."""
    try:
        mapping = ColumnMapping.from_dict({"columns": columns})
    except ValidationError as exc:
        return exc
    err = mapping.validate([c.header for c in mapping.columns], structure_implied=True)
    if err is not None:
        return err
    for c in mapping.columns:
        if c.target == ColumnTarget.IGNORE:
            continue
        levels = {p.strip().startswith(BATCH_PREFIX) for p in c.header.split("|")}
        if len(levels) > 1:
            return ValidationError(f"Field '{c.header}' mixes molecule and batch paths")
        is_batch_path = levels == {True}
        if c.target in _BATCH_TARGETS and not is_batch_path:
            return ValidationError(
                f"Field '{c.header}' is a compound field; it cannot go to {c.target.value}"
            )
        if c.target not in _BATCH_TARGETS and is_batch_path:
            return ValidationError(
                f"Field '{c.header}' is a batch field; it cannot go to {c.target.value}"
            )
    return None
