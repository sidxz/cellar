"""Integration test: DoseResponseCurveRepository.find_by_ids."""

from __future__ import annotations

import uuid

import pytest

from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from tests.fixtures.dose_response_curves import seed_curve


@pytest.mark.asyncio
class TestFindByIds:
    async def test_returns_curves_for_matching_ids(self, uow, workspace_id):
        async with uow:
            c1 = await seed_curve(uow, workspace_id=workspace_id)
            c2 = await seed_curve(uow, workspace_id=workspace_id)
            c3 = await seed_curve(uow, workspace_id=workspace_id)
        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            curves = await repo.find_by_ids([c1.id, c3.id], workspace_id=workspace_id)
        ids = {c.id for c in curves}
        assert ids == {c1.id, c3.id}

    async def test_filters_by_workspace(self, uow, workspace_id):
        other_ws = uuid.uuid4()
        async with uow:
            c1 = await seed_curve(uow, workspace_id=workspace_id)
            c2 = await seed_curve(uow, workspace_id=other_ws)
        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            curves = await repo.find_by_ids([c1.id, c2.id], workspace_id=workspace_id)
        assert {c.id for c in curves} == {c1.id}

    async def test_empty_input_returns_empty(self, uow, workspace_id):
        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            curves = await repo.find_by_ids([], workspace_id=workspace_id)
        assert curves == []

    async def test_missing_ids_silently_dropped(self, uow, workspace_id):
        async with uow:
            c1 = await seed_curve(uow, workspace_id=workspace_id)
        repo = SQLAlchemyDoseResponseCurveRepository(uow)
        async with uow:
            curves = await repo.find_by_ids([c1.id, uuid.uuid4()], workspace_id=workspace_id)
        assert [c.id for c in curves] == [c1.id]
