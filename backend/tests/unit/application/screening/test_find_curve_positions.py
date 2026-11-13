"""Unit tests for FindCurvePositions."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from cellar.application.screening.curve_position_reader import CurvePositions
from cellar.application.screening.find_curve_positions import (
    FindCurvePositions,
    FindCurvePositionsQuery,
)
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth


class Harness:
    def __init__(self) -> None:
        self.viewer = FakeAuth(role="viewer")
        self.ws = self.viewer.workspace_id
        self.protocol_id = uuid.uuid4()
        self.found = CurvePositions(
            protocol_id=self.protocol_id, dose_unit="uM", runs=(), positions=()
        )
        self.reader = AsyncMock()
        self.reader.find = AsyncMock(return_value=self.found)
        self.uc = FindCurvePositions(reader=self.reader)

    def query(self, *, run_ids=(), molecule_ids=()) -> FindCurvePositionsQuery:  # type: ignore[no-untyped-def]
        return FindCurvePositionsQuery(
            workspace_id=self.ws,
            protocol_id=self.protocol_id,
            run_ids=tuple(run_ids),
            molecule_ids=tuple(molecule_ids),
        )


async def test_passes_the_filters_to_the_reader():
    h = Harness()
    runs, molecules = (uuid.uuid4(), uuid.uuid4()), (uuid.uuid4(),)
    out = (await h.uc(h.query(run_ids=runs, molecule_ids=molecules), auth=h.viewer)).unwrap()
    assert out is h.found
    h.reader.find.assert_awaited_once_with(
        h.ws, h.protocol_id, run_ids=runs, molecule_ids=molecules
    )


async def test_more_than_8_runs_is_validation_error():
    h = Harness()
    failure = (
        await h.uc(h.query(run_ids=[uuid.uuid4() for _ in range(9)]), auth=h.viewer)
    ).failure()
    assert isinstance(failure, ValidationError)
    assert "At most 8 runs can be shown at once" in str(failure)
    h.reader.find.assert_not_awaited()


async def test_exactly_8_runs_is_accepted():
    h = Harness()
    result = await h.uc(h.query(run_ids=[uuid.uuid4() for _ in range(8)]), auth=h.viewer)
    assert result.unwrap() is h.found


async def test_more_than_50_compounds_is_validation_error():
    h = Harness()
    many = [uuid.uuid4() for _ in range(51)]
    failure = (await h.uc(h.query(molecule_ids=many), auth=h.viewer)).failure()
    assert isinstance(failure, ValidationError)
    assert "At most 50 compounds can be shown at once" in str(failure)
    h.reader.find.assert_not_awaited()


async def test_protocol_not_found():
    h = Harness()
    h.reader.find.return_value = None
    failure = (await h.uc(h.query(), auth=h.viewer)).failure()
    assert isinstance(failure, NotFoundError) and str(h.protocol_id) in str(failure)


async def test_other_workspace_raises_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h.uc(h.query(), auth=FakeAuth(role="viewer"))
    h.reader.find.assert_not_awaited()


async def test_no_role_raises_authorization_error():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h.uc(h.query(), auth=FakeAuth(role="guest", workspace_id=h.ws))
    h.reader.find.assert_not_awaited()
