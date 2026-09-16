"""Unit tests for PlateVisibilityService — strict org scoping (spec 2026-08-25 §3)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.value_objects import Barcode
from tests.fakes.fake_auth import FakeAuth


class _FakeOrgDirectory:
    """Static OrgDirectoryPort — a fixed set of org ids."""

    def __init__(self, org_ids: set[uuid.UUID] | None = None) -> None:
        self._orgs = [SimpleNamespace(id=i) for i in (org_ids or set())]

    async def list_orgs(self):
        return self._orgs


def _make_plate(owner_org_id: uuid.UUID | None) -> RegisteredPlate:
    return RegisteredPlate.register(
        workspace_id=uuid.uuid4(),
        owner_org_id=owner_org_id,
        barcode=Barcode(value=f"PLT-{uuid.uuid4().hex[:8]}"),
        plate_label="Test Plate",
        format=PlateFormat.F96,
        plate_type=PlateType.MOTHER,
        registered_by=uuid.uuid4(),
    )


class TestExcludedOrgIds:
    async def test_auth_none_is_empty_set(self) -> None:
        service = PlateVisibilityService(_FakeOrgDirectory({uuid.uuid4()}))

        assert await service.excluded_org_ids(uuid.uuid4(), None) == set()

    async def test_admin_is_empty_set(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory({org_a, org_b}))
        auth = FakeAuth(role="admin", org_id=org_a)

        assert await service.excluded_org_ids(uuid.uuid4(), auth) == set()

    async def test_editor_excludes_every_other_org(self) -> None:
        org_a, org_b, org_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory({org_a, org_b, org_c}))
        auth = FakeAuth(role="editor", org_id=org_a)

        assert await service.excluded_org_ids(uuid.uuid4(), auth) == {org_b, org_c}

    async def test_editor_without_org_excludes_all(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory({org_a, org_b}))
        auth = FakeAuth(role="editor", org_id=None)

        assert await service.excluded_org_ids(uuid.uuid4(), auth) == {org_a, org_b}

    async def test_no_directory_fails_closed_for_editor(self) -> None:
        service = PlateVisibilityService()
        auth = FakeAuth(role="editor", org_id=uuid.uuid4())

        with pytest.raises(RuntimeError):
            await service.excluded_org_ids(uuid.uuid4(), auth)

    async def test_no_directory_is_fine_for_admin_and_system(self) -> None:
        service = PlateVisibilityService()

        assert await service.excluded_org_ids(uuid.uuid4(), None) == set()
        assert await service.excluded_org_ids(uuid.uuid4(), FakeAuth(role="admin")) == set()


class TestCanView:
    def test_null_owner_always_viewable(self) -> None:
        service = PlateVisibilityService(_FakeOrgDirectory())
        plate = _make_plate(owner_org_id=None)

        assert service.can_view(plate, FakeAuth(), {uuid.uuid4()}) is True

    def test_owner_in_excluded_not_viewable(self) -> None:
        org_b = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory())
        plate = _make_plate(owner_org_id=org_b)

        assert service.can_view(plate, FakeAuth(), {org_b}) is False

    def test_owner_not_in_excluded_is_viewable(self) -> None:
        org_a = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory())
        plate = _make_plate(owner_org_id=org_a)

        assert service.can_view(plate, FakeAuth(org_id=org_a), set()) is True

    def test_borrowed_plate_viewable_despite_exclusion(self) -> None:
        org_b = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory())
        plate = _make_plate(owner_org_id=org_b)

        assert service.can_view(plate, FakeAuth(), {org_b}, borrowed={plate.id}) is True
