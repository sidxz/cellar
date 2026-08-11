"""Unit tests for PlateVisibilityService — private-org plate exclusion."""

from __future__ import annotations

import uuid

from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.value_objects import Barcode
from tests.fakes.fake_auth import FakeAuth


class _FakeOrgPlatePolicyRepo:
    """Fake OrgPlatePolicyRepository — returns a fixed set of private org ids."""

    def __init__(self, private_org_ids: set[uuid.UUID]) -> None:
        self._private_org_ids = private_org_ids

    async def find_by_org(self, workspace_id: uuid.UUID, org_id: uuid.UUID):
        raise NotImplementedError("not exercised by PlateVisibilityService")

    async def list_private_org_ids(self, workspace_id: uuid.UUID) -> set[uuid.UUID]:
        return self._private_org_ids

    async def save(self, aggregate) -> None:
        raise NotImplementedError("not exercised by PlateVisibilityService")


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
        org_b = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgPlatePolicyRepo({org_b}))

        excluded = await service.excluded_org_ids(uuid.uuid4(), None)

        assert excluded == set()

    async def test_caller_in_private_org_sees_own(self) -> None:
        org_b = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgPlatePolicyRepo({org_b}))
        auth = FakeAuth(org_id=org_b)

        excluded = await service.excluded_org_ids(uuid.uuid4(), auth)

        assert excluded == set()

    async def test_caller_in_other_org_gets_private_org_excluded(self) -> None:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgPlatePolicyRepo({org_b}))
        auth = FakeAuth(org_id=org_a)

        excluded = await service.excluded_org_ids(uuid.uuid4(), auth)

        assert excluded == {org_b}


class TestCanView:
    def test_null_owner_always_viewable(self) -> None:
        service = PlateVisibilityService(_FakeOrgPlatePolicyRepo(set()))
        plate = _make_plate(owner_org_id=None)

        assert service.can_view(plate, FakeAuth(), {uuid.uuid4()}) is True

    def test_owner_in_excluded_not_viewable(self) -> None:
        org_b = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgPlatePolicyRepo(set()))
        plate = _make_plate(owner_org_id=org_b)

        assert service.can_view(plate, FakeAuth(), {org_b}) is False

    def test_owner_not_in_excluded_is_viewable(self) -> None:
        org_a = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgPlatePolicyRepo(set()))
        plate = _make_plate(owner_org_id=org_a)

        assert service.can_view(plate, FakeAuth(org_id=org_a), set()) is True
