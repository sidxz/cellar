"""KioskDevice aggregate unit tests (spec §4.5)."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.events import KioskDeviceCreated, KioskDeviceRevoked
from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
ORG = uuid.uuid4()
USER = uuid.uuid4()
HASH = "a" * 64


def _make() -> KioskDevice:
    return KioskDevice.create(
        workspace_id=WS, org_id=ORG, name="Bench scanner", token_hash=HASH, created_by=USER
    )


class TestCreate:
    def test_create_sets_fields_and_emits(self) -> None:
        device = _make()
        assert device.is_active is True
        assert device.last_seen_at is None
        assert device.token_hash == HASH
        events = device.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, KioskDeviceCreated)
        assert (event.org_id, event.name, event.created_by) == (ORG, "Bench scanner", USER)

    def test_create_strips_and_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            KioskDevice.create(
                workspace_id=WS, org_id=ORG, name="   ", token_hash=HASH, created_by=USER
            )

    def test_create_rejects_overlong_name(self) -> None:
        with pytest.raises(ValidationError):
            KioskDevice.create(
                workspace_id=WS, org_id=ORG, name="x" * 101, token_hash=HASH, created_by=USER
            )

    def test_create_rejects_non_sha256_hash(self) -> None:
        with pytest.raises(ValidationError):
            KioskDevice.create(
                workspace_id=WS, org_id=ORG, name="Ok", token_hash="short", created_by=USER
            )


class TestRevoke:
    def test_revoke_deactivates_and_emits_once(self) -> None:
        device = _make()
        device.clear_events()
        device.revoke()
        assert device.is_active is False
        events = device.collect_events()
        assert len(events) == 1 and isinstance(events[0], KioskDeviceRevoked)

    def test_revoke_is_idempotent(self) -> None:
        device = _make()
        device.revoke()
        device.clear_events()
        device.revoke()  # second call: no-op, no duplicate audit event
        assert device.collect_events() == []
