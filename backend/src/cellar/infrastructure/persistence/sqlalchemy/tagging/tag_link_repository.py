"""Lightweight (non-aggregate) repositories for tag↔entity links.

One generic base, four type-bound subclasses, and a factory. Mirrors
SQLAlchemyProjectMemberRepository: direct SQL, on_conflict_do_nothing,
workspace defense via a subquery to the entity table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, distinct, func, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cellar.domain.workspace_config.tagging.tag import Tag, TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    ProjectModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    CollectionTagLinkModel,
    MoleculeTagLinkModel,
    ProjectTagLinkModel,
    ProtocolTagLinkModel,
    TagModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    tag_model_to_domain,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyTagLinkRepository:
    """Base for a single link table. Subclasses set the three class attributes."""

    link_model: type
    entity_model: type
    entity_id_attr: str

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self):  # noqa: ANN202 - AsyncSession
        return self._uow.session

    @property
    def _entity_col(self):  # noqa: ANN202 - InstrumentedAttribute
        return getattr(self.link_model, self.entity_id_attr)

    async def entity_exists_in_workspace(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> bool:
        stmt = select(self.entity_model.id).where(
            self.entity_model.id == entity_id,
            self.entity_model.workspace_id == workspace_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def add(
        self,
        workspace_id: uuid.UUID,
        entity_id: uuid.UUID,
        tag_id: uuid.UUID,
        assigned_by: uuid.UUID,
    ) -> None:
        if not await self.entity_exists_in_workspace(workspace_id, entity_id):
            return
        stmt = (
            pg_insert(self.link_model)
            .values(
                **{self.entity_id_attr: entity_id},
                tag_id=tag_id,
                assigned_by=assigned_by,
            )
            .on_conflict_do_nothing()
        )
        await self._session.execute(stmt)

    async def remove(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID, tag_id: uuid.UUID
    ) -> None:
        if not await self.entity_exists_in_workspace(workspace_id, entity_id):
            return
        stmt = delete(self.link_model).where(
            self._entity_col == entity_id, self.link_model.tag_id == tag_id
        )
        await self._session.execute(stmt)

    async def set_for_entity(
        self,
        workspace_id: uuid.UUID,
        entity_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        assigned_by: uuid.UUID,
    ) -> None:
        if not await self.entity_exists_in_workspace(workspace_id, entity_id):
            return
        del_stmt = delete(self.link_model).where(self._entity_col == entity_id)
        if tag_ids:
            del_stmt = del_stmt.where(self.link_model.tag_id.not_in(tag_ids))
        await self._session.execute(del_stmt)
        for tag_id in tag_ids:
            stmt = (
                pg_insert(self.link_model)
                .values(
                    **{self.entity_id_attr: entity_id},
                    tag_id=tag_id,
                    assigned_by=assigned_by,
                )
                .on_conflict_do_nothing()
            )
            await self._session.execute(stmt)

    async def find_tags_for_entity(
        self, workspace_id: uuid.UUID, entity_id: uuid.UUID
    ) -> list[Tag]:
        stmt = (
            select(TagModel)
            .join(self.link_model, TagModel.id == self.link_model.tag_id)
            .where(self._entity_col == entity_id, TagModel.workspace_id == workspace_id)
            .order_by(TagModel.normalized_key, TagModel.normalized_value)
        )
        result = await self._session.execute(stmt)
        return [tag_model_to_domain(m) for m in result.scalars()]

    async def find_entity_ids_for_tags(
        self,
        workspace_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        *,
        match_all: bool,
    ) -> list[uuid.UUID]:
        if not tag_ids:
            return []
        unique_ids = list(set(tag_ids))
        col = self._entity_col
        stmt = (
            select(col)
            .join(self.entity_model, self.entity_model.id == col)
            .where(
                self.link_model.tag_id.in_(unique_ids),
                self.entity_model.workspace_id == workspace_id,
            )
        )
        if match_all:
            stmt = stmt.group_by(col).having(
                func.count(distinct(self.link_model.tag_id)) == len(unique_ids)
            )
        else:
            stmt = stmt.distinct()
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def repoint(
        self, from_tag_id: uuid.UUID, to_tag_id: uuid.UUID
    ) -> None:
        """Move every link from ``from_tag_id`` to ``to_tag_id`` (merge).

        Copies the source links onto the target tag (skipping rows where the
        entity already carries the target — composite-PK conflict), then deletes
        the source links.
        """
        col = self._entity_col
        src = select(
            col,
            literal(to_tag_id),
            self.link_model.assigned_by,
            self.link_model.assigned_at,
        ).where(self.link_model.tag_id == from_tag_id)
        ins = (
            pg_insert(self.link_model)
            .from_select(
                [self.entity_id_attr, "tag_id", "assigned_by", "assigned_at"], src
            )
            .on_conflict_do_nothing()
        )
        await self._session.execute(ins)
        await self._session.execute(
            delete(self.link_model).where(self.link_model.tag_id == from_tag_id)
        )


class MoleculeTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = MoleculeTagLinkModel
    entity_model = MoleculeModel
    entity_id_attr = "molecule_id"


class ProtocolTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = ProtocolTagLinkModel
    entity_model = ProtocolModel
    entity_id_attr = "protocol_id"


class ProjectTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = ProjectTagLinkModel
    entity_model = ProjectModel
    entity_id_attr = "project_id"


class CollectionTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = CollectionTagLinkModel
    entity_model = CollectionModel
    entity_id_attr = "collection_id"


_REGISTRY: dict[TaggableEntityType, type[SQLAlchemyTagLinkRepository]] = {
    TaggableEntityType.MOLECULE: MoleculeTagLinkRepository,
    TaggableEntityType.PROTOCOL: ProtocolTagLinkRepository,
    TaggableEntityType.PROJECT: ProjectTagLinkRepository,
    TaggableEntityType.COLLECTION: CollectionTagLinkRepository,
}


def get_tag_link_repository(
    entity_type: TaggableEntityType, uow: AsyncUnitOfWork
) -> SQLAlchemyTagLinkRepository:
    """Factory: the link repository bound to ``entity_type``'s table."""
    return _REGISTRY[entity_type](uow)


class SQLAlchemyTagLinkRepositoryProvider:
    """Resolves the right link repository for an entity type, bound to a uow."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    def for_type(self, entity_type: TaggableEntityType) -> SQLAlchemyTagLinkRepository:
        return get_tag_link_repository(entity_type, self._uow)
