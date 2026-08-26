"""Target entity — biological entity that a compound acts upon."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError

# Canonical home is domain.shared (cross-context VO — see target_ref module).
# Re-exported here so existing screening_assay imports keep working.
from cellar.domain.shared.target_ref import TargetRef

__all__ = ["EffectiveTarget", "Target", "TargetRef"]


@dataclass(frozen=True)
class EffectiveTarget:
    """A target on a protocol's *effective* list, with provenance.

    ``is_direct`` — attached directly at the protocol level; survives the
    auto-prune that removes inherited-only targets when their last run drops
    them. ``run_count`` — how many of the protocol's runs reference it (0 when
    the target is direct-only).
    """

    id: uuid.UUID
    name: str
    target_type: str
    is_direct: bool
    run_count: int


class Target(Entity):
    """A biological target — read-only mirror of prot-cellar's catalog.

    Reference entity (not AggregateRoot); rows are created/updated only by
    SyncTargetsFromProtCellar. Invariants: name non-empty.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        target_type: TargetType,
        organism: str | None = None,
        gene_name: str | None = None,
        uniprot_id: str | None = None,
        ncbi_gene_id: str | None = None,
        description: str | None = None,
        target_class: str | None = None,
        sequence: str | None = None,
        chembl_id: str | None = None,
        source_version: int | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if not name or not name.strip():
            raise ValidationError("Target name must not be empty")

        self.workspace_id = workspace_id
        self.name = name.strip()
        self.target_type = target_type
        self.organism = organism
        self.gene_name = gene_name
        self.uniprot_id = uniprot_id
        self.ncbi_gene_id = ncbi_gene_id
        self.description = description
        self.target_class = target_class
        self.sequence = sequence
        self.chembl_id = chembl_id
        self.source_version = source_version

    @classmethod
    def from_mirror(
        cls,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        name: str,
        target_type: TargetType,
        organism: str | None,
        chembl_id: str | None,
        source_version: int,
    ) -> Target:
        """Build the local mirror row for a prot-cellar target.

        ``id`` is prot-cellar's target id — identical on both sides so link
        tables (``protocol_targets`` / ``run_targets``) need no translation.
        """
        return cls(
            id=id,
            workspace_id=workspace_id,
            name=name,
            target_type=target_type,
            organism=organism,
            chembl_id=chembl_id,
            source_version=source_version,
        )
