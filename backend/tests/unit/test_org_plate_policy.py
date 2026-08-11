"""Unit tests for OrgPlatePolicy aggregate."""

import uuid

import pytest

from cellar.domain.inventory.enums import LoanConfirmationMode
from cellar.domain.inventory.events import OrgPlatePolicySet
from cellar.domain.inventory.org_plate_policy import OrgPlatePolicy
from cellar.domain.shared.errors import ValidationError


class TestCreateDefault:
    def test_defaults(self) -> None:
        ws_id = uuid.uuid4()
        org_id = uuid.uuid4()
        policy = OrgPlatePolicy.create_default(workspace_id=ws_id, org_id=org_id)
        assert policy.workspace_id == ws_id
        assert policy.org_id == org_id
        assert policy.require_approval is True
        assert policy.confirmation == LoanConfirmationMode.ADMIN_CONFIRM
        assert policy.default_due_days == 14
        assert policy.plates_private is False
        assert policy.version == 1


class TestUpdate:
    def test_update_flips_plates_private_and_emits_event(self) -> None:
        policy = OrgPlatePolicy.create_default(workspace_id=uuid.uuid4(), org_id=uuid.uuid4())
        policy.update(plates_private=True)
        assert policy.plates_private is True

        events = policy.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], OrgPlatePolicySet)
        assert events[0].org_id == policy.org_id

    def test_update_other_fields(self) -> None:
        policy = OrgPlatePolicy.create_default(workspace_id=uuid.uuid4(), org_id=uuid.uuid4())
        policy.update(
            require_approval=False,
            confirmation=LoanConfirmationMode.KIOSK_SCAN,
            default_due_days=30,
        )
        assert policy.require_approval is False
        assert policy.confirmation == LoanConfirmationMode.KIOSK_SCAN
        assert policy.default_due_days == 30
        assert policy.plates_private is False  # unchanged

    def test_default_due_days_none_allowed(self) -> None:
        policy = OrgPlatePolicy.create_default(workspace_id=uuid.uuid4(), org_id=uuid.uuid4())
        policy.update(default_due_days=None)
        assert policy.default_due_days is None


class TestValidation:
    def test_default_due_days_zero_rejected(self) -> None:
        policy = OrgPlatePolicy.create_default(workspace_id=uuid.uuid4(), org_id=uuid.uuid4())
        with pytest.raises(ValidationError, match="default_due_days"):
            policy.update(default_due_days=0)

    def test_default_due_days_negative_rejected(self) -> None:
        policy = OrgPlatePolicy.create_default(workspace_id=uuid.uuid4(), org_id=uuid.uuid4())
        with pytest.raises(ValidationError, match="default_due_days"):
            policy.update(default_due_days=-1)
