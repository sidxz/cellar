"""Generic SQLAlchemy repository with optimistic concurrency control."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.domain.shared.entity import AggregateRoot, Entity
from cellar.domain.shared.errors import AuthorizationError, ConcurrencyConflictError
from cellar.infrastructure.persistence.sqlalchemy.base import Base
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class SQLAlchemyRepository[T: AggregateRoot, ModelType: Base](ABC):
    """Abstract repository that maps between domain aggregates and SA models.

    Subclasses must set ``model_class`` and implement the three mapping methods.
    """

    model_class: type[ModelType]

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self) -> AsyncSession:
        return self._uow.session

    # ------------------------------------------------------------------
    # Abstract mapping contract — subclasses implement these
    # ------------------------------------------------------------------

    @abstractmethod
    def _to_domain(self, model: ModelType) -> T:
        """Map an SA model instance to a domain aggregate."""
        ...

    @abstractmethod
    def _to_model(self, aggregate: T) -> ModelType:
        """Map a domain aggregate to a *new* SA model instance (for INSERT)."""
        ...

    @abstractmethod
    def _update_model(self, model: ModelType, aggregate: T) -> None:
        """Update an *existing* SA model's attributes from the aggregate."""
        ...

    # ------------------------------------------------------------------
    # Repository protocol implementation
    # ------------------------------------------------------------------

    def _to_domain_tracked(self, model: ModelType) -> T:
        """Map an SA model to a domain aggregate and register it with the UoW."""
        domain_entity = self._to_domain(model)
        self._uow.track(domain_entity)
        return domain_entity

    async def _owns(self, model: type, id_: uuid.UUID, workspace_id: uuid.UUID) -> bool:
        """Defense-in-depth ownership check: row exists AND is in the workspace.

        ``model`` may be any workspace-scoped SA model, not just
        ``model_class`` — link-table methods use it to validate both sides
        of an association.
        """
        result = await self._session.execute(
            select(model.id).where(model.id == id_, model.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none() is not None

    async def _find_by_id_unscoped(self, id: uuid.UUID) -> T | None:
        """Load an aggregate by primary key with NO workspace check.

        Reserved for aggregates whose primary key IS the workspace_id (e.g.
        ``WorkspaceSettings``). Every other repository must use
        ``find_by_id_in_workspace`` to prevent cross-tenant reads.
        """
        model = await self._session.get(self.model_class, id)
        if model is None:
            return None
        return self._to_domain_tracked(model)

    async def find_by_id(self, id: uuid.UUID) -> T | None:
        """DEPRECATED — kept for legacy callers and Protocol compliance.

        New code MUST use ``find_by_id_in_workspace``. This method does not
        check workspace ownership and is a cross-tenant footgun. The only
        legitimate caller is ``WorkspaceSettingsRepository.find_by_workspace_id``,
        which delegates to ``_find_by_id_unscoped`` directly.
        """
        return await self._find_by_id_unscoped(id)

    async def find_by_id_in_workspace(self, workspace_id: uuid.UUID, id: uuid.UUID) -> T | None:
        """Load an aggregate by PK scoped to a workspace.

        Returns ``None`` if the entity does not exist **or** belongs to a
        different workspace.  Prefer this over ``find_by_id`` followed by a
        manual workspace check — it pushes the filter into the SQL query.
        """
        stmt = select(self.model_class).where(
            self.model_class.id == id,  # type: ignore[attr-defined]
            self.model_class.workspace_id == workspace_id,  # type: ignore[attr-defined]
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain_tracked(model)

    async def save(self, aggregate: T) -> None:
        """Persist an aggregate (INSERT or UPDATE with version check)."""
        self._uow.track(aggregate)
        existing = await self._session.get(self.model_class, aggregate.id)

        if existing is None:
            # INSERT — new aggregate
            model = self._to_model(aggregate)
            self._session.add(model)
        else:
            # Defence-in-depth: verify the existing row belongs to the
            # same workspace as the aggregate being saved.
            if (
                hasattr(existing, "workspace_id")
                and hasattr(aggregate, "workspace_id")
                and existing.workspace_id != aggregate.workspace_id
            ):
                raise AuthorizationError(
                    f"Cannot update {type(aggregate).__name__} from a different workspace"
                )

            # UPDATE — optimistic concurrency check against the version
            # the aggregate was loaded with, not the current DB version.
            loaded_version: int = aggregate.version
            self._update_model(existing, aggregate)

            where_clauses = [
                self.model_class.id == aggregate.id,  # type: ignore[attr-defined]
                self.model_class.version == loaded_version,  # type: ignore[attr-defined]
            ]
            if hasattr(aggregate, "workspace_id") and hasattr(self.model_class, "workspace_id"):
                where_clauses.append(
                    self.model_class.workspace_id == aggregate.workspace_id  # type: ignore[attr-defined]
                )

            stmt = (
                update(self.model_class)
                .where(*where_clauses)
                .values(version=loaded_version + 1)
                .execution_options(synchronize_session=False)
            )
            result = await self._session.execute(stmt)

            if result.rowcount == 0:
                raise ConcurrencyConflictError(
                    entity_type=type(aggregate).__name__,
                    entity_id=str(aggregate.id),
                )
            # Sync both the ORM model and the domain aggregate so that a
            # subsequent session.flush() does not regress the version column.
            existing.version = loaded_version + 1  # type: ignore[attr-defined]
            aggregate.version = loaded_version + 1


class EntityRepository[T: Entity, ModelType: Base](ABC):
    """Base repository for plain (non-aggregate) domain Entity types.

    Provides the same workspace-scoped read / save / delete surface as
    ``SQLAlchemyRepository`` but without optimistic concurrency or event
    plumbing — appropriate for entities that don't carry a ``version``
    column and don't emit domain events (e.g. ``Target``, ``CompoundFlag``,
    ``PlateTemplate``).

    Workspace-mismatch is enforced as defence-in-depth on every mutating
    path: ``save`` raises ``AuthorizationError`` if an existing row's
    ``workspace_id`` doesn't match the entity being saved; ``delete``
    pushes the workspace filter into the SQL WHERE clause so cross-tenant
    deletes are physically impossible.
    """

    model_class: type[ModelType]

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self) -> AsyncSession:
        return self._uow.session

    # ------------------------------------------------------------------
    # Abstract mapping contract — subclasses implement these
    # ------------------------------------------------------------------

    @abstractmethod
    def _to_domain(self, model: ModelType) -> T: ...

    @abstractmethod
    def _to_model(self, entity: T) -> ModelType: ...

    @abstractmethod
    def _update_model(self, model: ModelType, entity: T) -> None: ...

    # ------------------------------------------------------------------
    # Standard workspace-scoped queries
    # ------------------------------------------------------------------

    async def find_by_id_in_workspace(self, workspace_id: uuid.UUID, id: uuid.UUID) -> T | None:
        stmt = select(self.model_class).where(
            self.model_class.id == id,  # type: ignore[attr-defined]
            self.model_class.workspace_id == workspace_id,  # type: ignore[attr-defined]
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[T]:
        stmt = (
            select(self.model_class)
            .where(self.model_class.workspace_id == workspace_id)  # type: ignore[attr-defined]
            .order_by(self.model_class.id)  # type: ignore[attr-defined]
        )
        if cursor_id is not None:
            stmt = stmt.where(self.model_class.id > cursor_id)  # type: ignore[attr-defined]
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, entity: T) -> None:
        existing = await self._session.get(self.model_class, entity.id)
        if existing is None:
            self._session.add(self._to_model(entity))
            return
        # Defence-in-depth: refuse to mutate a row that belongs to a
        # different workspace. find_by_id_in_workspace already filters,
        # but a use case could load via a different path and still try
        # to save here.
        if (
            hasattr(existing, "workspace_id")
            and hasattr(entity, "workspace_id")
            and existing.workspace_id != entity.workspace_id  # type: ignore[attr-defined]
        ):
            raise AuthorizationError(
                f"Cannot update {type(entity).__name__} from a different workspace"
            )
        self._update_model(existing, entity)

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        """Delete with workspace filter in the SQL WHERE clause.

        Cross-tenant deletes are physically impossible — no row is loaded
        and re-checked; the DELETE statement itself ANDs the workspace_id.
        """
        stmt = sa_delete(self.model_class).where(
            self.model_class.id == id,  # type: ignore[attr-defined]
            self.model_class.workspace_id == workspace_id,  # type: ignore[attr-defined]
        )
        await self._session.execute(stmt)
