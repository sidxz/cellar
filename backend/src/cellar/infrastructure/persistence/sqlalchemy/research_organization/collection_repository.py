"""SQLAlchemy repository for Collection aggregates + membership operations."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased

from cellar.domain.research_organization.collection import Collection, CollectionVisibility
from cellar.domain.shared.errors import CollectionFrozenError, NotFoundError
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionModel,
    CollectionMoleculeModel,
)


class SQLAlchemyCollectionRepository(SQLAlchemyRepository[Collection, CollectionModel]):
    model_class = CollectionModel

    def _to_domain(self, model: CollectionModel) -> Collection:
        return Collection(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            project_id=model.project_id,
            owned_by_org_id=model.owned_by_org_id,
            created_by=model.created_by,
            molecule_count=0,
            visibility=CollectionVisibility(model.visibility),
            is_frozen=model.is_frozen,
            derived_from_campaign_id=model.derived_from_campaign_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_domain_with_count(self, model: CollectionModel, molecule_count: int) -> Collection:
        """Map model to domain with an explicit molecule count."""
        entity = self._to_domain(model)
        entity.molecule_count = molecule_count
        return entity

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
            is_frozen=aggregate.is_frozen,
            derived_from_campaign_id=aggregate.derived_from_campaign_id,
            version=aggregate.version,
        )

    def _update_model(self, model: CollectionModel, aggregate: Collection) -> None:
        model.name = aggregate.name
        model.description = aggregate.description
        model.project_id = aggregate.project_id
        model.owned_by_org_id = aggregate.owned_by_org_id
        model.visibility = aggregate.visibility.value
        model.is_frozen = aggregate.is_frozen
        model.derived_from_campaign_id = aggregate.derived_from_campaign_id

    # ------------------------------------------------------------------
    # Workspace-scoped lookup (overrides base to include molecule_count)
    # ------------------------------------------------------------------

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Collection | None:
        stmt = select(CollectionModel).where(
            CollectionModel.id == id,
            CollectionModel.workspace_id == workspace_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        count = await self.count_molecules(workspace_id, id)
        domain_entity = self._to_domain_with_count(model, count)
        self._uow.track(domain_entity)
        return domain_entity

    # ------------------------------------------------------------------
    # Workspace queries
    # ------------------------------------------------------------------

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        project_ids: list[uuid.UUID] | None = None,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        limit: int | None = None,
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
        if project_ids:
            stmt = stmt.where(CollectionModel.project_id.in_(project_ids))
        # Newest-activity-first. Keyset on (updated_at, id) so pagination stays
        # stable under the DESC ordering: the next page is everything strictly
        # "older" than the last row of the previous page.
        if cursor is not None:
            cursor_updated_at, cursor_id = cursor
            stmt = stmt.where(
                sa.or_(
                    CollectionModel.updated_at < cursor_updated_at,
                    sa.and_(
                        CollectionModel.updated_at == cursor_updated_at,
                        CollectionModel.id < cursor_id,
                    ),
                )
            )
        stmt = stmt.order_by(
            CollectionModel.updated_at.desc(), CollectionModel.id.desc()
        )
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        collections = []
        for row in result.all():
            entity = self._to_domain_with_count(row[0], row[1])
            self._uow.track(entity)
            collections.append(entity)
        return collections

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        stmt = delete(CollectionModel).where(
            CollectionModel.workspace_id == workspace_id,
            CollectionModel.id == id,
        )
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Membership operations
    # ------------------------------------------------------------------

    async def add_molecules(
        self, workspace_id: uuid.UUID, collection_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> int:
        if not molecule_ids:
            return 0
        # Reject membership mutation on frozen Collections — closed campaigns
        # are immutable. Load the aggregate so the freeze flag is evaluated
        # against the persisted state.
        coll = await self.find_by_id_in_workspace(workspace_id, collection_id)
        if coll is None:
            raise NotFoundError("Collection", str(collection_id))
        if coll.is_frozen:
            raise CollectionFrozenError(
                f"Collection {collection_id} is frozen and cannot be modified"
            )
        values = [{"collection_id": collection_id, "molecule_id": mid} for mid in molecule_ids]
        stmt = pg_insert(CollectionMoleculeModel).values(values).on_conflict_do_nothing()
        result = await self._session.execute(stmt)
        if result.rowcount:
            await self._touch_updated_at(collection_id)
        return result.rowcount  # type: ignore[return-value]

    async def _touch_updated_at(self, collection_id: uuid.UUID) -> None:
        """Bump a collection's ``updated_at`` after a membership change.

        Membership lives in a join table, so inserts/deletes there don't trip
        the row's ``onupdate`` — but adding/removing molecules IS "working on"
        the collection, and the workspace list sorts by ``updated_at`` (newest
        activity first), so the collection should rise to the top.
        """
        await self._session.execute(
            update(CollectionModel)
            .where(CollectionModel.id == collection_id)
            .values(updated_at=func.now())
        )

    async def remove_molecules(
        self, workspace_id: uuid.UUID, collection_id: uuid.UUID, molecule_ids: list[uuid.UUID]
    ) -> int:
        if not molecule_ids:
            return 0
        # Reject membership mutation on frozen Collections — closed campaigns
        # are immutable.
        coll = await self.find_by_id_in_workspace(workspace_id, collection_id)
        if coll is None:
            raise NotFoundError("Collection", str(collection_id))
        if coll.is_frozen:
            raise CollectionFrozenError(
                f"Collection {collection_id} is frozen and cannot be modified"
            )
        # Defense-in-depth: only delete if collection belongs to workspace
        stmt = delete(CollectionMoleculeModel).where(
            CollectionMoleculeModel.collection_id == collection_id,
            CollectionMoleculeModel.molecule_id.in_(molecule_ids),
            CollectionMoleculeModel.collection_id.in_(
                select(CollectionModel.id).where(CollectionModel.workspace_id == workspace_id)
            ),
        )
        result = await self._session.execute(stmt)
        if result.rowcount:
            await self._touch_updated_at(collection_id)
        return result.rowcount  # type: ignore[return-value]

    async def get_molecule_ids(
        self,
        workspace_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[uuid.UUID]:
        stmt = (
            select(CollectionMoleculeModel.molecule_id)
            .join(CollectionModel, CollectionMoleculeModel.collection_id == CollectionModel.id)
            .where(
                CollectionMoleculeModel.collection_id == collection_id,
                CollectionModel.workspace_id == workspace_id,
            )
            .order_by(CollectionMoleculeModel.added_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def count_molecules(self, workspace_id: uuid.UUID, collection_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(CollectionMoleculeModel)
            .join(CollectionModel, CollectionMoleculeModel.collection_id == CollectionModel.id)
            .where(
                CollectionMoleculeModel.collection_id == collection_id,
                CollectionModel.workspace_id == workspace_id,
            )
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
            .join(
                CollectionMoleculeModel,
                CollectionMoleculeModel.collection_id == CollectionModel.id,
            )
            .where(
                CollectionModel.workspace_id == workspace_id,
                CollectionMoleculeModel.molecule_id == molecule_id,
            )
            .order_by(CollectionModel.name)
        )
        result = await self._session.execute(stmt)
        collections = []
        for row in result.all():
            entity = self._to_domain_with_count(row[0], row[1])
            self._uow.track(entity)
            collections.append(entity)
        return collections

    async def compose_molecule_ids(
        self,
        workspace_id: uuid.UUID,
        operation: str,
        collection_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Execute set operation across collection memberships.

        Only considers collections belonging to the specified workspace.
        """
        from sqlalchemy import func as sa_func

        # Restrict to collections in this workspace (defense-in-depth)
        valid_stmt = select(CollectionModel.id).where(
            CollectionModel.id.in_(collection_ids),
            CollectionModel.workspace_id == workspace_id,
        )
        valid_result = await self._session.execute(valid_stmt)
        ws_ids = list(valid_result.scalars())
        if not ws_ids:
            return []

        if operation == "union":
            stmt = (
                select(CollectionMoleculeModel.molecule_id)
                .where(CollectionMoleculeModel.collection_id.in_(ws_ids))
                .group_by(CollectionMoleculeModel.molecule_id)
            )
        elif operation == "intersect":
            stmt = (
                select(CollectionMoleculeModel.molecule_id)
                .where(CollectionMoleculeModel.collection_id.in_(ws_ids))
                .group_by(CollectionMoleculeModel.molecule_id)
                .having(
                    sa_func.count(sa_func.distinct(CollectionMoleculeModel.collection_id))
                    == len(ws_ids)
                )
            )
        elif operation == "difference":
            first_id = ws_ids[0]
            rest_ids = ws_ids[1:]
            first = select(CollectionMoleculeModel.molecule_id).where(
                CollectionMoleculeModel.collection_id == first_id
            )
            rest = select(CollectionMoleculeModel.molecule_id).where(
                CollectionMoleculeModel.collection_id.in_(rest_ids)
            )
            stmt = first.except_(rest)
        elif operation == "symmetric_difference":
            stmt = (
                select(CollectionMoleculeModel.molecule_id)
                .where(CollectionMoleculeModel.collection_id.in_(ws_ids))
                .group_by(CollectionMoleculeModel.molecule_id)
                .having(
                    sa_func.count(sa_func.distinct(CollectionMoleculeModel.collection_id)) == 1
                )
            )
        else:
            msg = f"Unknown boolean operation: {operation}"
            raise ValueError(msg)

        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def replace_molecule(
        self,
        workspace_id: uuid.UUID,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> int:
        """Replace source molecule with target in workspace collections.

        Frozen Collections are silently skipped — closed campaigns are
        historical artifacts and must not be retroactively rewired by
        molecule merge operations.

        Two-step process to avoid unique constraint violations:
        1. DELETE rows where both source and target exist in the same collection.
        2. UPDATE remaining source rows to point to target.

        Returns the number of rows updated in step 2.
        """
        # Identify candidate (workspace-scoped, non-frozen) collections that
        # contain the source molecule. We post-filter in Python so the freeze
        # check works regardless of whether the SQL column has shipped yet.
        candidates = await self.find_collections_containing(workspace_id, source_molecule_id)
        target_collection_ids = [c.id for c in candidates if not c.is_frozen]
        if not target_collection_ids:
            return 0

        # Step 1: Remove duplicate entries — collections that already have
        # the target molecule; the source entry would cause a PK conflict.
        cm2 = aliased(CollectionMoleculeModel)
        dedup_stmt = (
            delete(CollectionMoleculeModel)
            .where(
                CollectionMoleculeModel.molecule_id == source_molecule_id,
                CollectionMoleculeModel.collection_id.in_(target_collection_ids),
                sa.exists()
                .where(
                    cm2.collection_id == CollectionMoleculeModel.collection_id,
                    cm2.molecule_id == target_molecule_id,
                )
                .correlate(CollectionMoleculeModel),
            )
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(dedup_stmt)

        # Step 2: Re-point remaining source references to target.
        update_stmt = (
            sa.update(CollectionMoleculeModel)
            .where(
                CollectionMoleculeModel.molecule_id == source_molecule_id,
                CollectionMoleculeModel.collection_id.in_(target_collection_ids),
            )
            .values(molecule_id=target_molecule_id)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(update_stmt)
        return result.rowcount  # type: ignore[return-value]
