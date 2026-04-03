"""Integration tests for database infrastructure (S03).

Requires Docker — uses testcontainers to spin up PostgreSQL+RDKit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy import String, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ConcurrencyConflictError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)
from chem_vault.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

# ---------------------------------------------------------------------------
# Test-only domain aggregate, SA model, and repository
# ---------------------------------------------------------------------------

WORKSPACE_ID = uuid.uuid4()


@dataclass(frozen=True, kw_only=True)
class _DummyCreated(DomainEvent):
    name: str


class _DummyAggregate(AggregateRoot):
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str = "",
        workspace_id: uuid.UUID = WORKSPACE_ID,
        version: int = 1,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, version=version, created_at=created_at, updated_at=updated_at)
        self.name = name
        self.workspace_id = workspace_id


class _DummyModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    __tablename__ = "_test_dummy"
    name: Mapped[str] = mapped_column(String(100))


class _DummyRepository(SQLAlchemyRepository[_DummyAggregate, _DummyModel]):
    model_class = _DummyModel

    def _to_domain(self, model: _DummyModel) -> _DummyAggregate:
        return _DummyAggregate(
            id=model.id,
            name=model.name,
            workspace_id=model.workspace_id,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, aggregate: _DummyAggregate) -> _DummyModel:
        return _DummyModel(
            id=aggregate.id,
            name=aggregate.name,
            workspace_id=aggregate.workspace_id,
            version=aggregate.version,
            created_at=aggregate.created_at,
            updated_at=aggregate.updated_at,
        )

    def _update_model(self, model: _DummyModel, aggregate: _DummyAggregate) -> None:
        model.name = aggregate.name
        model.workspace_id = aggregate.workspace_id
        model.updated_at = aggregate.updated_at


# ---------------------------------------------------------------------------
# Module-scoped fixture: create/drop the test table
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
async def _create_test_table(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[_DummyModel.__table__])
    yield  # type: ignore[misc]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=[_DummyModel.__table__])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRDKitExtension:
    async def test_rdkit_extension_available(self, db_session: AsyncSession) -> None:
        """RDKit cartridge is enabled and functional."""
        result = await db_session.execute(text("SELECT mol_to_smiles('CCO'::mol)"))
        smiles = result.scalar_one()
        assert smiles == "CCO"

    async def test_rdkit_extension_idempotent(self, db_session: AsyncSession) -> None:
        """Creating the RDKit extension again does not error (IF NOT EXISTS)."""
        await db_session.execute(text("CREATE EXTENSION IF NOT EXISTS rdkit"))
        # Verify still functional
        result = await db_session.execute(text("SELECT mol_to_smiles('C'::mol)"))
        assert result.scalar_one() == "C"


class TestCRUDWithMixins:
    async def test_insert_read_update_delete(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Full CRUD lifecycle with EntityModelMixin + VersionMixin."""
        row_id = uuid.uuid4()

        # INSERT
        async with session_factory() as session:
            model = _DummyModel(
                id=row_id,
                name="aspirin",
                workspace_id=WORKSPACE_ID,
                version=1,
            )
            session.add(model)
            await session.commit()

        # READ
        async with session_factory() as session:
            result = await session.get(_DummyModel, row_id)
            assert result is not None
            assert result.name == "aspirin"
            assert result.version == 1
            assert result.workspace_id == WORKSPACE_ID
            assert result.created_at is not None
            assert result.updated_at is not None

        # UPDATE
        async with session_factory() as session:
            result = await session.get(_DummyModel, row_id)
            assert result is not None
            result.name = "ibuprofen"
            result.version = 2
            await session.commit()

        # Verify update
        async with session_factory() as session:
            result = await session.get(_DummyModel, row_id)
            assert result is not None
            assert result.name == "ibuprofen"
            assert result.version == 2

        # DELETE
        async with session_factory() as session:
            result = await session.get(_DummyModel, row_id)
            assert result is not None
            await session.delete(result)
            await session.commit()

        # Verify delete
        async with session_factory() as session:
            result = await session.get(_DummyModel, row_id)
            assert result is None


class TestOptimisticConcurrency:
    async def test_concurrency_conflict_detected(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Second save with stale version raises ConcurrencyConflictError."""
        agg_id = uuid.uuid4()
        agg = _DummyAggregate(id=agg_id, name="original")

        # Insert via repo
        async with AsyncUnitOfWork(session_factory) as uow_insert:
            repo = _DummyRepository(uow_insert)
            await repo.save(agg)
            await uow_insert.commit()

        # Both UoWs load the SAME version BEFORE either commits
        uow_a = AsyncUnitOfWork(session_factory)
        uow_b = AsyncUnitOfWork(session_factory)
        await uow_a.__aenter__()
        await uow_b.__aenter__()

        repo_a = _DummyRepository(uow_a)
        repo_b = _DummyRepository(uow_b)

        loaded_a = await repo_a.find_by_id(agg_id)
        loaded_b = await repo_b.find_by_id(agg_id)
        assert loaded_a is not None
        assert loaded_b is not None
        assert loaded_a.version == loaded_b.version == 1

        # A saves and commits — version 1 → 2
        loaded_a.name = "update_a"
        await repo_a.save(loaded_a)
        await uow_a.commit()
        await uow_a.__aexit__(None, None, None)

        # B tries to save with stale version 1 — DB has version 2
        loaded_b.name = "update_b"
        with pytest.raises(ConcurrencyConflictError):
            await repo_b.save(loaded_b)
        await uow_b.__aexit__(None, None, None)


class TestUnitOfWork:
    async def test_commit_collects_events(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """UoW commit returns domain events and clears them from aggregates."""
        agg = _DummyAggregate(name="event-test")
        event = _DummyCreated(
            aggregate_id=agg.id,
            aggregate_type="DummyAggregate",
            name="event-test",
        )
        agg.register_event(event)

        async with AsyncUnitOfWork(session_factory) as uow:
            repo = _DummyRepository(uow)
            await repo.save(agg)
            events = await uow.commit()

        assert len(events) == 1
        assert isinstance(events[0], _DummyCreated)
        assert events[0].name == "event-test"
        # Events cleared after commit
        assert agg.collect_events() == []

    async def test_rollback_no_leak(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """On error, session rolls back and aggregate events are preserved."""
        agg = _DummyAggregate(name="rollback-test")
        event = _DummyCreated(
            aggregate_id=agg.id,
            aggregate_type="DummyAggregate",
            name="rollback-test",
        )
        agg.register_event(event)

        with pytest.raises(RuntimeError, match="intentional"):
            async with AsyncUnitOfWork(session_factory) as uow:
                repo = _DummyRepository(uow)
                await repo.save(agg)
                raise RuntimeError("intentional")

        # Events NOT cleared — aggregate still has them for potential retry
        assert len(agg.collect_events()) == 1

        # Row was not persisted
        async with session_factory() as session:
            result = await session.get(_DummyModel, agg.id)
            assert result is None
