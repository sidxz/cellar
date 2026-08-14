"""Integration tests for SQLAlchemyKioskDeviceRepository."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.infrastructure.persistence.sqlalchemy.inventory.kiosk_device_repository import (
    SQLAlchemyKioskDeviceRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

ORG = uuid.uuid4()
USER = uuid.uuid4()


def _token() -> str:
    """A fresh 64-char token — token_hash is globally unique, not per-workspace."""
    return uuid.uuid4().hex + uuid.uuid4().hex


def _make(
    ws: uuid.UUID, *, name: str = "Bench scanner", token_hash: str | None = None
) -> KioskDevice:
    return KioskDevice.create(
        workspace_id=ws,
        org_id=ORG,
        name=name,
        token_hash=token_hash or _token(),
        created_by=USER,
    )


async def _save(session_factory, *devices: KioskDevice) -> None:
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyKioskDeviceRepository(uow)
        for device in devices:
            await repo.save(device)
        await uow.commit()


# ---------------------------------------------------------------------------
# (a) save -> find_by_id_in_workspace round-trips every field
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_round_trip_every_field(session_factory) -> None:
    ws = uuid.uuid4()
    token = _token()
    device = _make(ws, name="Bench scanner 1", token_hash=token)
    await _save(session_factory, device)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyKioskDeviceRepository(uow)
        loaded = await repo.find_by_id_in_workspace(ws, device.id)
        assert loaded is not None
        assert loaded.id == device.id
        assert loaded.workspace_id == ws
        assert loaded.org_id == ORG
        assert loaded.name == "Bench scanner 1"
        assert loaded.token_hash == token
        assert loaded.is_active is True
        assert loaded.last_seen_at is None
        assert loaded.created_by == USER
        assert loaded.version == 1


# ---------------------------------------------------------------------------
# (b) find_active_by_token_hash finds it; None after revoke()+save
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_find_active_by_token_hash_then_none_after_revoke(session_factory) -> None:
    ws = uuid.uuid4()
    token = _token()
    device = _make(ws, token_hash=token)
    await _save(session_factory, device)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyKioskDeviceRepository(uow)
        found = await repo.find_active_by_token_hash(token)
        assert found is not None
        assert found.id == device.id

        found.revoke()
        await repo.save(found)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyKioskDeviceRepository(uow)
        assert await repo.find_active_by_token_hash(token) is None


# ---------------------------------------------------------------------------
# (c) duplicate (workspace, name) insert raises IntegrityError
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_duplicate_workspace_name_raises_integrity_error(session_factory) -> None:
    ws = uuid.uuid4()
    first = _make(ws, name="Shared name")
    await _save(session_factory, first)

    second = _make(ws, name="Shared name")
    with pytest.raises(IntegrityError):
        await _save(session_factory, second)


# ---------------------------------------------------------------------------
# (d) touch_last_seen sets the timestamp WITHOUT bumping version
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_touch_last_seen_sets_timestamp_without_bumping_version(session_factory) -> None:
    ws = uuid.uuid4()
    device = _make(ws)
    await _save(session_factory, device)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyKioskDeviceRepository(uow)
        await repo.touch_last_seen(device.id)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyKioskDeviceRepository(uow)
        reloaded = await repo.find_by_id_in_workspace(ws, device.id)
        assert reloaded is not None
        assert reloaded.last_seen_at is not None
        assert reloaded.version == 1


# ---------------------------------------------------------------------------
# (e) find_by_name exact match
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_find_by_name_exact_match(session_factory) -> None:
    ws = uuid.uuid4()
    device = _make(ws, name="Exact Name")
    other = _make(ws, name="Exact Name 2")
    await _save(session_factory, device, other)

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyKioskDeviceRepository(uow)
        found = await repo.find_by_name(ws, "Exact Name")
        assert found is not None
        assert found.id == device.id
        assert await repo.find_by_name(ws, "Exact Name 3") is None
