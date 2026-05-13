"""Target entity — biological entity that a compound acts upon."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError


class Target(Entity):
    """A biological target referenced by screening protocols.

    Reference entity (not AggregateRoot) — shared across many protocols,
    no complex behavior or domain events.

    Invariants:
        - name cannot be empty
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

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
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
    ) -> Target:
        return cls(
            workspace_id=workspace_id,
            name=name,
            target_type=target_type,
            organism=organism,
            gene_name=gene_name,
            uniprot_id=uniprot_id,
            ncbi_gene_id=ncbi_gene_id,
            description=description,
            target_class=target_class,
            sequence=sequence,
        )

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str | None = None,
        target_type: TargetType | None = None,
        organism: str | None = ...,  # type: ignore[assignment]
        gene_name: str | None = ...,  # type: ignore[assignment]
        uniprot_id: str | None = ...,  # type: ignore[assignment]
        ncbi_gene_id: str | None = ...,  # type: ignore[assignment]
        description: str | None = ...,  # type: ignore[assignment]
        target_class: str | None = ...,  # type: ignore[assignment]
        sequence: str | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields.

        Uses sentinel ``...`` for optional nullable fields so callers can
        explicitly pass ``None`` to clear them.
        """
        if name is not None:
            if not name.strip():
                raise ValidationError("Target name must not be empty")
            self.name = name.strip()
        if target_type is not None:
            self.target_type = target_type
        if organism is not ...:
            self.organism = organism
        if gene_name is not ...:
            self.gene_name = gene_name
        if uniprot_id is not ...:
            self.uniprot_id = uniprot_id
        if ncbi_gene_id is not ...:
            self.ncbi_gene_id = ncbi_gene_id
        if description is not ...:
            self.description = description
        if target_class is not ...:
            self.target_class = target_class
        if sequence is not ...:
            self.sequence = sequence
        self.updated_at = datetime.now(UTC)
