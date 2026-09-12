"""Tests for the one-run-one-shape guards."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest

from cellar.application.screening.run_shape import refuse_if_welled, refuse_if_wellless
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.errors import ConflictError


def _make_run(*, with_plate: bool) -> Run:
    run = Run(
        workspace_id=uuid.uuid4(),
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 1, 15),
        operator=uuid.uuid4(),
    )
    if with_plate:
        plate = Plate(run_id=run.id, plate_number=1)
        run.plates = [plate]
        run.wells = [Well(plate_id=plate.id, row="A", column=1)]
    return run


class TestRefuseIfWelled:
    def test_run_without_wells_is_allowed(self):
        assert refuse_if_welled(_make_run(with_plate=False)) is None

    def test_run_with_wells_is_refused(self):
        run = _make_run(with_plate=True)

        error = refuse_if_welled(run)

        assert isinstance(error, ConflictError)
        assert "1 plate(s) with wells" in str(error)
        assert str(run.id) in str(error)


class TestRefuseIfWellless:
    @pytest.mark.asyncio
    async def test_no_wellless_rows_is_allowed(self):
        repo = AsyncMock()
        repo.has_wellless_rows = AsyncMock(return_value=False)
        ws, run_id = uuid.uuid4(), uuid.uuid4()

        assert await refuse_if_wellless(repo, ws, run_id) is None
        repo.has_wellless_rows.assert_awaited_once_with(ws, run_id)

    @pytest.mark.asyncio
    async def test_wellless_rows_are_refused(self):
        repo = AsyncMock()
        repo.has_wellless_rows = AsyncMock(return_value=True)
        run_id = uuid.uuid4()

        error = await refuse_if_wellless(repo, uuid.uuid4(), run_id)

        assert isinstance(error, ConflictError)
        assert "well-less summary results" in str(error)
        assert str(run_id) in str(error)
