"""Cross-entity tag-browse read repository.

Given a tag, returns the entities of every taggable type that carry it, each with
a display label. A UNION ALL across the eight link tables, each branch joined to
its entity table for the label and workspace-scoped. Read-only; not an aggregate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, cast, distinct, func, literal, select, union_all

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
    assigned_at: datetime


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
        tag_ids,
        workspace_id,
        *,
        match_all,
        extra_where=None,
    ):
        link_fk = getattr(link_model, entity_id_attr)
        # GROUP BY the entity PK so an entity tagged with several of the selected
        # tags collapses to one row; max(assigned_at) is the most recent matching
        # assignment. `match_all` keeps only entities carrying every selected tag.
        stmt = (
            select(
                literal(entity_type).label("entity_type"),
                entity_model.id.label("entity_id"),
                label_col.label("label"),
                func.max(link_model.assigned_at).label("assigned_at"),
            )
            .join(link_model, link_fk == entity_model.id)
            .where(link_model.tag_id.in_(tag_ids), entity_model.workspace_id == workspace_id)
            .group_by(entity_model.id)
        )
        if extra_where is not None:
            stmt = stmt.where(extra_where)
        if match_all:
            stmt = stmt.having(func.count(distinct(link_model.tag_id)) == len(tag_ids))
        return stmt

    async def find_entities_for_tags(
        self,
        workspace_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        *,
        match_all: bool = False,
        types: list[str] | None = None,
        limit: int = 200,
    ) -> list[TaggedEntityRow]:
        if not tag_ids:
            return []
        ids = list(dict.fromkeys(tag_ids))  # dedup, preserve order
        b = self._branch
        run_branch = (
            select(
                literal("Run").label("entity_type"),
                RunModel.id.label("entity_id"),
                (ProtocolModel.name + literal(" · ") + cast(RunModel.run_date, String)).label(
                    "label"
                ),
                func.max(RunTagLinkModel.assigned_at).label("assigned_at"),
            )
            .join(RunTagLinkModel, RunTagLinkModel.run_id == RunModel.id)
            .join(ProtocolModel, ProtocolModel.id == RunModel.protocol_id)
            .where(RunTagLinkModel.tag_id.in_(ids), RunModel.workspace_id == workspace_id)
            .group_by(RunModel.id, ProtocolModel.id)
        )
        if match_all:
            run_branch = run_branch.having(
                func.count(distinct(RunTagLinkModel.tag_id)) == len(ids)
            )
        branches = {
            "Molecule": b(
                "Molecule",
                MoleculeTagLinkModel,
                "molecule_id",
                MoleculeModel,
                MoleculeModel.registration_number,
                ids,
                workspace_id,
                match_all=match_all,
                extra_where=MoleculeModel.merged_into_id.is_(None),
            ),
            "Protocol": b(
                "Protocol",
                ProtocolTagLinkModel,
                "protocol_id",
                ProtocolModel,
                ProtocolModel.name,
                ids,
                workspace_id,
                match_all=match_all,
            ),
            "Project": b(
                "Project",
                ProjectTagLinkModel,
                "project_id",
                ProjectModel,
                ProjectModel.name,
                ids,
                workspace_id,
                match_all=match_all,
            ),
            "Collection": b(
                "Collection",
                CollectionTagLinkModel,
                "collection_id",
                CollectionModel,
                CollectionModel.name,
                ids,
                workspace_id,
                match_all=match_all,
            ),
            "Run": run_branch,
            "Campaign": b(
                "Campaign",
                CampaignTagLinkModel,
                "campaign_id",
                CampaignModel,
                CampaignModel.name,
                ids,
                workspace_id,
                match_all=match_all,
            ),
            "Batch": b(
                "Batch",
                BatchTagLinkModel,
                "batch_id",
                BatchModel,
                BatchModel.batch_number,
                ids,
                workspace_id,
                match_all=match_all,
            ),
            "Plate": b(
                "Plate",
                RegisteredPlateTagLinkModel,
                "registered_plate_id",
                RegisteredPlateModel,
                RegisteredPlateModel.plate_label,
                ids,
                workspace_id,
                match_all=match_all,
            ),
        }
        selected = [s for name, s in branches.items() if not types or name in types]
        if not selected:
            return []
        unioned = union_all(*selected).subquery()
        stmt = (
            select(
                unioned.c.entity_type,
                unioned.c.entity_id,
                unioned.c.label,
                unioned.c.assigned_at,
            )
            .order_by(unioned.c.assigned_at.desc(), unioned.c.entity_type, unioned.c.label)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            TaggedEntityRow(
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                label=r.label,
                assigned_at=r.assigned_at,
            )
            for r in result.all()
        ]
