"""KioskDevice admin use cases — create (token minted once), list, revoke (spec §4.5, §9)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_admin,
    require_authenticated,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.domain.inventory.repository import KioskDeviceRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError

KIOSK_TOKEN_BYTES = 32


@dataclass(frozen=True, kw_only=True)
class CreateKioskDeviceCommand(Command):
    workspace_id: uuid.UUID
    org_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class CreatedKioskDevice:
    """The one and only carrier of the plaintext token."""

    device: KioskDevice
    token: str


@dataclass(frozen=True, kw_only=True)
class ListKioskDevicesQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RevokeKioskDeviceCommand(Command):
    workspace_id: uuid.UUID
    device_id: uuid.UUID


def hash_kiosk_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CreateKioskDevice:
    def __init__(
        self, uow: UnitOfWork, repo: KioskDeviceRepository, dispatcher: EventDispatcherProtocol
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateKioskDeviceCommand, auth: AuthContext | None = None
    ) -> Result[CreatedKioskDevice, DomainError]:
        require_authenticated(auth)  # created_by attribution — before role guard
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None
        token = secrets.token_urlsafe(KIOSK_TOKEN_BYTES)
        async with self._uow:
            if await self._repo.find_by_name(input.workspace_id, input.name.strip()):
                return Failure(
                    ConflictError(f"A kiosk device named '{input.name.strip()}' already exists")
                )
            device = KioskDevice.create(
                workspace_id=input.workspace_id,
                org_id=input.org_id,
                name=input.name,
                token_hash=hash_kiosk_token(token),
                created_by=auth.user_id,
            )
            await self._repo.save(device)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(CreatedKioskDevice(device=device, token=token))


class ListKioskDevices:
    def __init__(self, uow: UnitOfWork, repo: KioskDeviceRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListKioskDevicesQuery, auth: AuthContext | None = None
    ) -> Result[list[KioskDevice], DomainError]:
        require_authenticated(auth)
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            return Success(await self._repo.find_by_workspace(input.workspace_id))


class RevokeKioskDevice:
    def __init__(
        self, uow: UnitOfWork, repo: KioskDeviceRepository, dispatcher: EventDispatcherProtocol
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RevokeKioskDeviceCommand, auth: AuthContext | None = None
    ) -> Result[KioskDevice, DomainError]:
        require_authenticated(auth)
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            device = await self._repo.find_by_id_in_workspace(input.workspace_id, input.device_id)
            if device is None:
                return Failure(NotFoundError("Kiosk device", str(input.device_id)))
            device.revoke()
            await self._repo.save(device)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(device)
