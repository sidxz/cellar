"""Cross-entity tag-browse read repository.

Given a tag, returns the entities of every taggable type that carry it, each with
a display label. A UNION ALL across the eight link tables, each branch joined to
its entity table for the label and workspace-scoped. Read-only; not an aggregate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import String, cast, literal, select, union_all

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
    RegisteredPlateModel,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignModel,
    CollectionModel,
    ProjectModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    BatchTagLinkModel,
    CampaignTagLinkModel,
    CollectionTagLinkModel,
    MoleculeTagLinkModel,
    ProjectTagLinkModel,
    ProtocolTagLinkModel,
    RegisteredPlateTagLinkModel,
    RunTagLinkModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@dataclass(frozen=True, kw_only=True)
class TaggedEntityRow:
    entity_type: str
    entity_id: uuid.UUID
    label: str


class SQLAlchemyTagBrowseRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self):  # AsyncSession
        return self._uow.session

    def _branch(
        self,
        entity_type,
        link_model,
        entity_id_attr,
        entity_model,
        label_col,
        tag_id,
        workspace_id,
        extra_where=None,
    ):
        link_fk = getattr(link_model, entity_id_attr)
        stmt = (
            select(
                literal(entity_type).label("entity_type"),
                entity_model.id.label("entity_id"),
                label_col.label("label"),
            )
            .join(link_model, link_fk == entity_model.id)
            .where(link_model.tag_id == tag_id, entity_model.workspace_id == workspace_id)
        )
        if extra_where is not None:
            stmt = stmt.where(extra_where)
        return stmt

    async def find_entities_for_tag(
        self,
        workspace_id: uuid.UUID,
        tag_id: uuid.UUID,
        *,
        types: list[str] | None = None,
        limit: int = 200,
    ) -> list[TaggedEntityRow]:
        b = self._branch
        run_branch = (
            select(
                literal("Run").label("entity_type"),
                RunModel.id.label("entity_id"),
                (ProtocolModel.name + literal(" · ") + cast(RunModel.run_date, String)).label(
                    "label"
                ),
            )
            .join(RunTagLinkModel, RunTagLinkModel.run_id == RunModel.id)
            .join(ProtocolModel, ProtocolModel.id == RunModel.protocol_id)
            .where(RunTagLinkModel.tag_id == tag_id, RunModel.workspace_id == workspace_id)
        )
        branches = {
            "Molecule": b(
                "Molecule",
                MoleculeTagLinkModel,
                "molecule_id",
                MoleculeModel,
                MoleculeModel.registration_number,
                tag_id,
                workspace_id,
                extra_where=MoleculeModel.merged_into_id.is_(None),
            ),
            "Protocol": b(
                "Protocol",
                ProtocolTagLinkModel,
                "protocol_id",
                ProtocolModel,
                ProtocolModel.name,
                tag_id,
                workspace_id,
            ),
            "Project": b(
                "Project",
                ProjectTagLinkModel,
                "project_id",
                ProjectModel,
                ProjectModel.name,
                tag_id,
                workspace_id,
            ),
            "Collection": b(
                "Collection",
                CollectionTagLinkModel,
                "collection_id",
                CollectionModel,
                CollectionModel.name,
                tag_id,
                workspace_id,
            ),
            "Run": run_branch,
            "Campaign": b(
                "Campaign",
                CampaignTagLinkModel,
                "campaign_id",
                CampaignModel,
                CampaignModel.name,
                tag_id,
                workspace_id,
            ),
            "Batch": b(
                "Batch",
                BatchTagLinkModel,
                "batch_id",
                BatchModel,
                BatchModel.batch_number,
                tag_id,
                workspace_id,
            ),
            "Plate": b(
                "Plate",
                RegisteredPlateTagLinkModel,
                "registered_plate_id",
                RegisteredPlateModel,
                RegisteredPlateModel.plate_label,
                tag_id,
                workspace_id,
            ),
        }
        selected = [s for name, s in branches.items() if not types or name in types]
        if not selected:
            return []
        unioned = union_all(*selected).subquery()
        stmt = (
            select(unioned.c.entity_type, unioned.c.entity_id, unioned.c.label)
            .order_by(unioned.c.entity_type, unioned.c.label)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            TaggedEntityRow(entity_type=r.entity_type, entity_id=r.entity_id, label=r.label)
            for r in result.all()
        ]
