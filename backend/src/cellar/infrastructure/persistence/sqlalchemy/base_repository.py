"""Generic SQLAlchemy repository with optimistic concurrency control."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.domain.shared.entity import AggregateRoot
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
