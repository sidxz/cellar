"""SQLAlchemy repository for Target entities.

Target is a plain Entity (no version, no domain events). Inherits the
workspace-scoped read/save/delete surface from ``EntityRepository``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.screening_assay.target import Target
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    EntityRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
    TargetModel,
    protocol_targets,
    run_targets,
)


class SQLAlchemyTargetRepository(EntityRepository[Target, TargetModel]):
    """Persists Target entities to PostgreSQL."""

    model_class = TargetModel

    async def count_references(
        self, workspace_id: uuid.UUID, target_id: uuid.UUID
    ) -> tuple[int, int]:
        """``(protocol_count, run_count)`` of link rows referencing the target."""
        protocol_count = await self._session.scalar(
            select(func.count())
            .select_from(
                protocol_targets.join(
                    ProtocolModel, protocol_targets.c.protocol_id == ProtocolModel.id
                )
            )
            .where(
                protocol_targets.c.target_id == target_id,
                ProtocolModel.workspace_id == workspace_id,
            )
        )
        run_count = await self._session.scalar(
            select(func.count())
            .select_from(run_targets.join(RunModel, run_targets.c.run_id == RunModel.id))
            .where(
                run_targets.c.target_id == target_id,
                RunModel.workspace_id == workspace_id,
            )
        )
        return int(protocol_count or 0), int(run_count or 0)

    def _to_domain(self, model: TargetModel) -> Target:
        return Target(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            target_type=TargetType(model.target_type),
            organism=model.organism,
            gene_name=model.gene_name,
            uniprot_id=model.uniprot_id,
            ncbi_gene_id=model.ncbi_gene_id,
            description=model.description,
            target_class=model.target_class,
            sequence=model.sequence,
            chembl_id=model.chembl_id,
            source_version=model.source_version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Target) -> TargetModel:
        return TargetModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            target_type=entity.target_type.value,
            organism=entity.organism,
            gene_name=entity.gene_name,
            uniprot_id=entity.uniprot_id,
            ncbi_gene_id=entity.ncbi_gene_id,
            description=entity.description,
            target_class=entity.target_class,
            sequence=entity.sequence,
            chembl_id=entity.chembl_id,
            source_version=entity.source_version,
        )

    def _update_model(self, model: TargetModel, entity: Target) -> None:
        model.name = entity.name
        model.target_type = entity.target_type.value
        model.organism = entity.organism
        model.gene_name = entity.gene_name
        model.uniprot_id = entity.uniprot_id
        model.ncbi_gene_id = entity.ncbi_gene_id
        model.description = entity.description
        model.target_class = entity.target_class
        model.sequence = entity.sequence
        model.chembl_id = entity.chembl_id
        model.source_version = entity.source_version
