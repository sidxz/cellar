"""SQLAlchemy repository for Collection aggregates + membership operations."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chem_vault.domain.research_organization.collection import Collection, CollectionVisibility
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    CollectionMoleculeModel,
)


class SQLAlchemyCollectionRepository(
    SQLAlchemyRepository[Collection, CollectionModel]
):
    model_class = CollectionModel

    def _to_domain(self, model: CollectionModel, *, molecule_count: int = 0) -> Collection:
        return Collection(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            project_id=model.project_id,
            owned_by_org_id=model.owned_by_org_id,
            created_by=model.created_by,
            molecule_count=molecule_count,
            visibility=CollectionVisibility(model.visibility),
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Collection) -> CollectionModel:
        return CollectionModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            name=aggregate.name,
            description=aggregate.description,
            project_id=aggregate.project_id,
            owned_by_org_id=aggregate.owned_by_org_id,
            created_by=aggregate.created_by,
            visibility=aggregate.visibility.value,
            version=aggregate.version,
        )

    def _update_model(self, model: CollectionModel, aggregate: Collection) -> None:
        model.name = aggregate.name
        model.description = aggregate.description
        model.project_id = aggregate.project_id
        model.owned_by_org_id = aggregate.owned_by_org_id
        model.visibility = aggregate.visibility.value

    # ------------------------------------------------------------------
    # Override find_by_id to populate molecule_count
    # ------------------------------------------------------------------

    async def find_by_id(self, id: uuid.UUID) -> Collection | None:
        model = await self._session.get(CollectionModel, id)
        if model is None:
            return None
        count = await self.count_molecules(id)
        domain_entity = self._to_domain(model, molecule_count=count)
        self._uow.track(domain_entity)
        return domain_entity

    # ------------------------------------------------------------------
    # Workspace queries
    # ------------------------------------------------------------------

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
    ) -> list[Collection]:
        # Subquery for molecule counts
        count_sq = (
            select(
                CollectionMoleculeModel.collection_id,
                func.count().label("mol_count"),
            )
            .group_by(CollectionMoleculeModel.collection_id)
            .subquery()
        )

        stmt = (
            select(CollectionModel, func.coalesce(count_sq.c.mol_count, 0).label("mol_count"))
            .outerjoin(count_sq, CollectionModel.id == count_sq.c.collection_id)
            .where(CollectionModel.workspace_id == workspace_id)
        )
        if project_id is not None:
            stmt = stmt.where(CollectionModel.project_id == project_id)
        stmt = stmt.order_by(CollectionModel.name)

        result = await self._session.execute(stmt)
        return [
            self._to_domain(row[0], molecule_count=row[1])
            for row in result.all()
        ]

    async def delete(self, id: uuid.UUID) -> None:
        stmt = delete(CollectionModel).where(CollectionModel.id == id)
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Membership operations
    # ------------------------------------------------------------------

    async def add_molecules(
        self, collection_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> int:
        if not molecule_ids:
            return 0
        values = [
            {"collection_id": collection_id, "molecule_id": mid}
            for mid in molecule_ids
        ]
        stmt = pg_insert(CollectionMoleculeModel).values(values).on_conflict_do_nothing()
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    async def remove_molecules(
        self, collection_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> int:
        if not molecule_ids:
            return 0
        stmt = delete(CollectionMoleculeModel).where(
            CollectionMoleculeModel.collection_id == collection_id,
            CollectionMoleculeModel.molecule_id.in_(molecule_ids),
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    async def get_molecule_ids(
        self,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]:
        stmt = (
            select(CollectionMoleculeModel.molecule_id)
            .where(CollectionMoleculeModel.collection_id == collection_id)
            .order_by(CollectionMoleculeModel.added_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def count_molecules(self, collection_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(CollectionMoleculeModel)
            .where(CollectionMoleculeModel.collection_id == collection_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def find_collections_containing(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> list[Collection]:
        """Return Collection objects in workspace that contain the given molecule."""
        # Subquery for molecule counts
        count_sq = (
            select(
                CollectionMoleculeModel.collection_id,
                func.count().label("mol_count"),
            )
            .group_by(CollectionMoleculeModel.collection_id)
            .subquery()
        )

        stmt = (
            select(CollectionModel, func.coalesce(count_sq.c.mol_count, 0).label("mol_count"))
            .outerjoin(count_sq, CollectionModel.id == count_sq.c.collection_id)
            .join(CollectionMoleculeModel, CollectionMoleculeModel.collection_id == CollectionModel.id)
            .where(
                CollectionModel.workspace_id == workspace_id,
                CollectionMoleculeModel.molecule_id == molecule_id,
            )
            .order_by(CollectionModel.name)
        )
        result = await self._session.execute(stmt)
        return [
            self._to_domain(row[0], molecule_count=row[1])
            for row in result.all()
        ]

    async def replace_molecule(
        self,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> int:
        """Replace source molecule with target in all collections.

        Two-step process to avoid unique constraint violations:
        1. DELETE rows where both source and target exist in the same collection.
        2. UPDATE remaining source rows to point to target.

        Returns the number of rows updated in step 2.
        """
        params = {"source": source_molecule_id, "target": target_molecule_id}

        # Step 1: Remove duplicate entries — collections that already have
        # the target molecule; the source entry would cause a PK conflict.
        await self._session.execute(
            sa.text(
                "DELETE FROM collection_molecules cm1 "
                "USING collection_molecules cm2 "
                "WHERE cm1.molecule_id = :source "
                "AND cm2.molecule_id = :target "
                "AND cm1.collection_id = cm2.collection_id"
            ),
            params,
        )

        # Step 2: Re-point remaining source references to target.
        result = await self._session.execute(
            sa.text(
                "UPDATE collection_molecules "
                "SET molecule_id = :target "
                "WHERE molecule_id = :source"
            ),
            params,
        )
        return result.rowcount  # type: ignore[return-value]
