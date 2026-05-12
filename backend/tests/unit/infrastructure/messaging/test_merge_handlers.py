"""Unit tests for merge side-effect handlers.

Each handler is tested with a mocked AsyncSession to verify the correct
SQL statements are executed with the right parameters.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, call

import pytest

from cellar.infrastructure.messaging.merge_handlers import (
    BatchMergeSideEffect,
    DoseResponseCurveMergeSideEffect,
    MoleculeRelationshipMergeSideEffect,
    ReadoutDataMergeSideEffect,
)


class FakeUoW:
    """Minimal UoW stub that exposes a mock session."""

    def __init__(self, session: AsyncMock) -> None:
        self.session = session


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def uow(session: AsyncMock) -> FakeUoW:
    return FakeUoW(session)


@pytest.fixture
def source_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def target_id() -> uuid.UUID:
    return uuid.uuid4()


class TestBatchMergeSideEffect:
    @pytest.mark.asyncio
    async def test_updates_molecule_id(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        handler = BatchMergeSideEffect()
        await handler.on_merge(uow, source_id, target_id)

        session.execute.assert_awaited_once()
        args = session.execute.call_args
        sql_text = str(args[0][0].text)
        params = args[0][1]

        assert "UPDATE batches" in sql_text
        assert "molecule_id = :target" in sql_text
        assert "WHERE molecule_id = :source" in sql_text
        assert params == {"target": target_id, "source": source_id}


class TestReadoutDataMergeSideEffect:
    @pytest.mark.asyncio
    async def test_updates_molecule_id(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        handler = ReadoutDataMergeSideEffect()
        await handler.on_merge(uow, source_id, target_id)

        session.execute.assert_awaited_once()
        args = session.execute.call_args
        sql_text = str(args[0][0].text)
        params = args[0][1]

        assert "UPDATE readout_data" in sql_text
        assert "molecule_id = :target" in sql_text
        assert params == {"target": target_id, "source": source_id}


class TestDoseResponseCurveMergeSideEffect:
    @pytest.mark.asyncio
    async def test_updates_molecule_id(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        handler = DoseResponseCurveMergeSideEffect()
        await handler.on_merge(uow, source_id, target_id)

        session.execute.assert_awaited_once()
        args = session.execute.call_args
        sql_text = str(args[0][0].text)
        params = args[0][1]

        assert "UPDATE dose_response_curves" in sql_text
        assert "molecule_id = :target" in sql_text
        assert params == {"target": target_id, "source": source_id}


class TestMoleculeRelationshipMergeSideEffect:
    @pytest.mark.asyncio
    async def test_executes_five_statements(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        """Should execute: 1 self-ref delete, 2 duplicate deletes, 2 updates."""
        handler = MoleculeRelationshipMergeSideEffect()
        await handler.on_merge(uow, source_id, target_id)

        assert session.execute.await_count == 5

    @pytest.mark.asyncio
    async def test_deletes_self_referential_first(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        handler = MoleculeRelationshipMergeSideEffect()
        await handler.on_merge(uow, source_id, target_id)

        first_call = session.execute.call_args_list[0]
        sql_text = str(first_call[0][0].text)

        assert "DELETE FROM molecule_relationships" in sql_text
        assert "source_molecule_id = :source AND target_molecule_id = :target" in sql_text

    @pytest.mark.asyncio
    async def test_updates_remaining_references_last(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        handler = MoleculeRelationshipMergeSideEffect()
        await handler.on_merge(uow, source_id, target_id)

        calls = session.execute.call_args_list

        # 4th call: UPDATE source_molecule_id
        sql_4 = str(calls[3][0][0].text)
        assert "UPDATE molecule_relationships" in sql_4
        assert "SET source_molecule_id = :target" in sql_4

        # 5th call: UPDATE target_molecule_id
        sql_5 = str(calls[4][0][0].text)
        assert "UPDATE molecule_relationships" in sql_5
        assert "SET target_molecule_id = :target" in sql_5

    @pytest.mark.asyncio
    async def test_all_statements_use_correct_params(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        handler = MoleculeRelationshipMergeSideEffect()
        await handler.on_merge(uow, source_id, target_id)

        expected_params = {"source": source_id, "target": target_id}
        for c in session.execute.call_args_list:
            assert c[0][1] == expected_params

    @pytest.mark.asyncio
    async def test_dedup_queries_scope_by_workspace_id(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        """Dedup DELETE USING joins must include workspace_id for tenant isolation."""
        handler = MoleculeRelationshipMergeSideEffect()
        await handler.on_merge(uow, source_id, target_id)

        calls = session.execute.call_args_list
        # Steps 2 and 3 are the dedup deletes (indices 1, 2)
        for idx in (1, 2):
            sql_text = str(calls[idx][0][0].text)
            assert "workspace_id" in sql_text


class TestRegistryIntegration:
    """Verify handlers satisfy the MergeSideEffectHandler protocol."""

    @pytest.mark.asyncio
    async def test_all_handlers_callable(
        self, session: AsyncMock, uow: FakeUoW, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        from cellar.application.chemical_registration.merge_side_effect_registry import (
            MergeSideEffectRegistry,
        )

        registry = MergeSideEffectRegistry()
        registry.register(BatchMergeSideEffect())
        registry.register(ReadoutDataMergeSideEffect())
        registry.register(DoseResponseCurveMergeSideEffect())
        registry.register(MoleculeRelationshipMergeSideEffect())

        await registry.execute_all(uow, source_id, target_id)

        # 1 (batch) + 1 (readout) + 1 (drc) + 5 (relationships) = 8
        assert session.execute.await_count == 8
