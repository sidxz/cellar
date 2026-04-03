"""Generic SQLAlchemy repository with optimistic concurrency control."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ConcurrencyConflictError
from chem_vault.infrastructure.persistence.sqlalchemy.base import Base
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


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

    async def find_by_id(self, id: uuid.UUID) -> T | None:
        """Load an aggregate by primary key, or return ``None``."""
        model = await self._session.get(self.model_class, id)
        if model is None:
            return None
        domain_entity = self._to_domain(model)
        self._uow.track(domain_entity)
        return domain_entity

    async def save(self, aggregate: T) -> None:
        """Persist an aggregate (INSERT or UPDATE with version check)."""
        self._uow.track(aggregate)
        existing = await self._session.get(self.model_class, aggregate.id)

        if existing is None:
            # INSERT — new aggregate
            model = self._to_model(aggregate)
            self._session.add(model)
        else:
            # UPDATE — optimistic concurrency check against the version
            # the aggregate was loaded with, not the current DB version.
            loaded_version: int = aggregate.version
            self._update_model(existing, aggregate)

            stmt = (
                update(self.model_class)
                .where(
                    self.model_class.id == aggregate.id,  # type: ignore[attr-defined]
                    self.model_class.version == loaded_version,  # type: ignore[attr-defined]
                )
                .values(version=loaded_version + 1)
                .execution_options(synchronize_session=False)
            )
            result = await self._session.execute(stmt)

            if result.rowcount == 0:
                raise ConcurrencyConflictError(
                    entity_type=type(aggregate).__name__,
                    entity_id=str(aggregate.id),
                )
            aggregate.version = loaded_version + 1
