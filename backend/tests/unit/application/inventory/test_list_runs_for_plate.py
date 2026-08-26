"""Unit tests for ListRunsForPlate — GetPlate's guard + visibility sequence, then the reader."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from returns.result import Failure, Success

from cellar.application.inventory.list_runs_for_plate import (
    ListRunsForPlate,
    ListRunsForPlateQuery,
)
from cellar.application.inventory.plate_runs_reader import PlateRunRow
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.errors import NotFoundError
from cellar.domain.shared.value_objects import Barcode
from tests.fakes.fake_auth import FakeAuth
from tests.fakes.fake_registered_plate_repository import FakeRegisteredPlateRepository

WS = uuid.uuid4()
ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()


class _FakeUow:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeOrgDirectory:
    def __init__(self, *org_ids: uuid.UUID) -> None:
        self._orgs = [SimpleNamespace(id=i) for i in org_ids]

    async def list_orgs(self):
        return self._orgs


class _FakeLoanRepo:
    def __init__(self, borrowed: set[uuid.UUID]) -> None:
        self._borrowed = borrowed

    async def borrowed_plate_ids(self, workspace_id, org_id):
        return self._borrowed


class _StubReader:
    def __init__(self, rows: list[PlateRunRow]) -> None:
        self.rows = rows
        self.calls: list[uuid.UUID] = []

    async def runs_for_plate(self, workspace_id, plate_id):
        self.calls.append(plate_id)
        return self.rows


def _plate(owner_org_id: uuid.UUID | None) -> RegisteredPlate:
    return RegisteredPlate.register(
        workspace_id=WS,
        owner_org_id=owner_org_id,
        barcode=Barcode(value=f"PLT-{uuid.uuid4().hex[:8]}"),
        plate_label="Test Plate",
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=uuid.uuid4(),
    )


def _row() -> PlateRunRow:
    return PlateRunRow(
        run_id=uuid.uuid4(),
        run_date=date(2026, 6, 7),
        run_status="draft",
        protocol_id=uuid.uuid4(),
        protocol_name="Proto",
        plate_number=1,
        created_at=datetime.now(UTC),
    )


def _uc(plate: RegisteredPlate | None, reader: _StubReader, *, borrowed=None) -> ListRunsForPlate:
    return ListRunsForPlate(
        _FakeUow(),
        FakeRegisteredPlateRepository([plate] if plate else []),
        PlateVisibilityService(
            _FakeOrgDirectory(ORG_A, ORG_B),
            _FakeLoanRepo(borrowed) if borrowed is not None else None,
        ),
        reader,
    )


class TestListRunsForPlate:
    async def test_viewer_gets_reader_rows(self) -> None:
        plate = _plate(ORG_A)
        reader = _StubReader([_row()])

        result = await _uc(plate, reader)(
            ListRunsForPlateQuery(workspace_id=WS, plate_id=plate.id),
            auth=FakeAuth(role="viewer", workspace_id=WS, org_id=ORG_A),
        )

        assert isinstance(result, Success)
        assert result.unwrap() == reader.rows
        assert reader.calls == [plate.id]

    async def test_missing_plate_is_not_found(self) -> None:
        reader = _StubReader([_row()])

        result = await _uc(None, reader)(
            ListRunsForPlateQuery(workspace_id=WS, plate_id=uuid.uuid4()),
            auth=FakeAuth(role="viewer", workspace_id=WS, org_id=ORG_A),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert reader.calls == []

    async def test_hidden_foreign_org_plate_is_not_found(self) -> None:
        plate = _plate(ORG_B)
        reader = _StubReader([_row()])

        result = await _uc(plate, reader)(
            ListRunsForPlateQuery(workspace_id=WS, plate_id=plate.id),
            auth=FakeAuth(role="editor", workspace_id=WS, org_id=ORG_A),
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert reader.calls == []  # no existence leak via the reader either

    async def test_borrowed_plate_is_visible(self) -> None:
        plate = _plate(ORG_B)
        reader = _StubReader([_row()])

        result = await _uc(plate, reader, borrowed={plate.id})(
            ListRunsForPlateQuery(workspace_id=WS, plate_id=plate.id),
            auth=FakeAuth(role="editor", workspace_id=WS, org_id=ORG_A),
        )

        assert isinstance(result, Success)
        assert reader.calls == [plate.id]

    async def test_other_workspace_raises_not_found(self) -> None:
        plate = _plate(ORG_A)

        with pytest.raises(NotFoundError):
            await _uc(plate, _StubReader([]))(
                ListRunsForPlateQuery(workspace_id=WS, plate_id=plate.id),
                auth=FakeAuth(role="viewer", workspace_id=uuid.uuid4(), org_id=ORG_A),
            )
