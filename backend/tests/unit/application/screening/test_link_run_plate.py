"""Unit tests for LinkRunPlate / UnlinkRunPlate (S15 spec §5.2)."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace, TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.screening.link_run_plate import (
    LinkRunPlate,
    LinkRunPlateCommand,
    UnlinkRunPlate,
    UnlinkRunPlateCommand,
)
from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.screening_assay.run import Plate, Run
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.errors import AuthorizationError, ConflictError, NotFoundError
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.value_objects import Barcode
from tests.fakes.fake_auth import FakeAuth
from tests.fakes.fake_registered_plate_repository import FakeRegisteredPlateRepository

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


class FakeRunRepository:
    def __init__(self, runs: list[Run]) -> None:
        self._runs = {r.id: r for r in runs}
        self.saved: list[Run] = []

    async def find_by_id_in_workspace(self, workspace_id: uuid.UUID, id: uuid.UUID) -> Run | None:
        run = self._runs.get(id)
        return run if run is not None and run.workspace_id == workspace_id else None

    async def save(self, run: Run) -> None:
        self.saved.append(run)


class _FakeOrgDirectory:
    async def list_orgs(self):
        return [SimpleNamespace(id=ORG_A), SimpleNamespace(id=ORG_B)]


def _reg_plate(
    workspace_id: uuid.UUID, *, barcode: str, label: str, owner_org_id: uuid.UUID = ORG_A
) -> RegisteredPlate:
    return RegisteredPlate.register(
        workspace_id=workspace_id,
        owner_org_id=owner_org_id,
        barcode=Barcode(value=barcode),
        plate_label=label,
        format=PlateFormat.F96,
        plate_type=PlateType.ASSAY,
        registered_by=uuid.uuid4(),
    )


def _run_with_plate(workspace_id: uuid.UUID, *, locked: bool = False) -> tuple[Run, Plate]:
    run = Run(
        workspace_id=workspace_id,
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 8, 26),
        operator=uuid.uuid4(),
    )
    plate = Plate(run_id=run.id, plate_number=1)
    run.add_plate(plate)
    run.is_locked = locked
    return run, plate


def _build(
    auth: FakeAuth, run: Run, plates: list[RegisteredPlate]
) -> tuple[LinkRunPlate, UnlinkRunPlate, FakeRunRepository, AsyncMock]:
    uow = FakeUoW()
    run_repo = FakeRunRepository([run])
    plate_repo = FakeRegisteredPlateRepository(plates)
    visibility = PlateVisibilityService(_FakeOrgDirectory())
    dispatcher = AsyncMock()
    return (
        LinkRunPlate(uow, run_repo, plate_repo, visibility, dispatcher),
        UnlinkRunPlate(uow, run_repo, dispatcher),
        run_repo,
        dispatcher,
    )


def _link_cmd(auth: FakeAuth, run: Run, plate: Plate, barcode: str) -> LinkRunPlateCommand:
    return LinkRunPlateCommand(
        workspace_id=auth.workspace_id, run_id=run.id, plate_id=plate.id, barcode=barcode
    )


class TestLinkRunPlate:
    @pytest.mark.parametrize("reference", ["000123", "123", "SAC3-014-3070"])
    async def test_links_by_barcode_zero_padded_or_label(self, reference: str) -> None:
        auth = FakeAuth(role="editor", org_id=ORG_A)
        run, plate = _run_with_plate(auth.workspace_id)
        rp = _reg_plate(auth.workspace_id, barcode="000123", label="SAC3-014-3070")
        link, _, run_repo, dispatcher = _build(auth, run, [rp])

        result = await link(_link_cmd(auth, run, plate, reference), auth=auth)

        assert isinstance(result, Success), result
        out = result.unwrap()
        assert out.plate_id == plate.id
        assert out.registered_plate_id == rp.id
        assert out.barcode == "000123"
        assert out.plate_label == "SAC3-014-3070"
        assert plate.registered_plate_id == rp.id
        assert run_repo.saved == [run]
        dispatcher.dispatch_all.assert_awaited_once()

    async def test_unknown_reference_is_not_found(self) -> None:
        auth = FakeAuth(role="editor", org_id=ORG_A)
        run, plate = _run_with_plate(auth.workspace_id)
        link, _, run_repo, _ = _build(auth, run, [])

        result = await link(_link_cmd(auth, run, plate, "nope"), auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert run_repo.saved == []

    async def test_hidden_foreign_org_plate_is_not_found(self) -> None:
        auth = FakeAuth(role="editor", org_id=ORG_A)
        run, plate = _run_with_plate(auth.workspace_id)
        rp = _reg_plate(auth.workspace_id, barcode="000123", label="X", owner_org_id=ORG_B)
        link, _, _, _ = _build(auth, run, [rp])

        result = await link(_link_cmd(auth, run, plate, "000123"), auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert plate.registered_plate_id is None

    async def test_locked_run_conflicts(self) -> None:
        auth = FakeAuth(role="editor", org_id=ORG_A)
        run, plate = _run_with_plate(auth.workspace_id, locked=True)
        rp = _reg_plate(auth.workspace_id, barcode="000123", label="X")
        link, _, _, _ = _build(auth, run, [rp])

        with pytest.raises(ConflictError, match="locked"):
            await link(_link_cmd(auth, run, plate, "000123"), auth=auth)

    async def test_plate_not_on_run_is_not_found(self) -> None:
        auth = FakeAuth(role="editor", org_id=ORG_A)
        run, _ = _run_with_plate(auth.workspace_id)
        rp = _reg_plate(auth.workspace_id, barcode="000123", label="X")
        link, _, run_repo, _ = _build(auth, run, [rp])
        stray = Plate(run_id=uuid.uuid4(), plate_number=1)

        result = await link(_link_cmd(auth, run, stray, "000123"), auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert run_repo.saved == []

    async def test_unknown_run_is_not_found(self) -> None:
        auth = FakeAuth(role="editor", org_id=ORG_A)
        run, plate = _run_with_plate(auth.workspace_id)
        link, _, _, _ = _build(auth, run, [])
        cmd = LinkRunPlateCommand(
            workspace_id=auth.workspace_id, run_id=uuid.uuid4(), plate_id=plate.id, barcode="x"
        )

        result = await link(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    async def test_viewer_is_forbidden(self) -> None:
        auth = FakeAuth(role="viewer", org_id=ORG_A)
        run, plate = _run_with_plate(auth.workspace_id)
        link, unlink, _, _ = _build(auth, run, [])

        with pytest.raises(AuthorizationError):
            await link(_link_cmd(auth, run, plate, "000123"), auth=auth)
        with pytest.raises(AuthorizationError):
            await unlink(
                UnlinkRunPlateCommand(
                    workspace_id=auth.workspace_id, run_id=run.id, plate_id=plate.id
                ),
                auth=auth,
            )


class TestUnlinkRunPlate:
    async def test_unlink_clears_link(self) -> None:
        auth = FakeAuth(role="editor", org_id=ORG_A)
        run, plate = _run_with_plate(auth.workspace_id)
        plate.registered_plate_id = uuid.uuid4()
        _, unlink, run_repo, dispatcher = _build(auth, run, [])

        result = await unlink(
            UnlinkRunPlateCommand(
                workspace_id=auth.workspace_id, run_id=run.id, plate_id=plate.id
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        out = result.unwrap()
        assert out.plate_id == plate.id
        assert out.registered_plate_id is None
        assert out.barcode is None
        assert out.plate_label is None
        assert plate.registered_plate_id is None
        assert run_repo.saved == [run]
        dispatcher.dispatch_all.assert_awaited_once()

    async def test_unlink_locked_run_conflicts(self) -> None:
        auth = FakeAuth(role="editor", org_id=ORG_A)
        run, plate = _run_with_plate(auth.workspace_id, locked=True)
        _, unlink, _, _ = _build(auth, run, [])

        with pytest.raises(ConflictError, match="locked"):
            await unlink(
                UnlinkRunPlateCommand(
                    workspace_id=auth.workspace_id, run_id=run.id, plate_id=plate.id
                ),
                auth=auth,
            )
