"""Kiosk-device admin routes — token minted once at create, never re-shown."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.kiosk_devices import (
    CreateKioskDeviceCommand,
    ListKioskDevicesQuery,
    RevokeKioskDeviceCommand,
)
from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.interface.dependencies import (
    AuthDep,
    CreateKioskDeviceDep,
    ListKioskDevicesDep,
    RevokeKioskDeviceDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/kiosk-devices", tags=["kiosk-devices"])


class CreateKioskDeviceBody(BaseModel):
    org_id: uuid.UUID
    name: str


class KioskDeviceResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime

    @classmethod
    def from_domain(cls, d: KioskDevice) -> KioskDeviceResponse:
        return cls(
            id=d.id,
            org_id=d.org_id,
            name=d.name,
            is_active=d.is_active,
            last_seen_at=d.last_seen_at,
            created_at=d.created_at,
        )


class KioskDeviceCreatedResponse(KioskDeviceResponse):
    token: str  # shown once; only the sha256 hash is stored


@router.post("", response_model=KioskDeviceCreatedResponse, status_code=201)
async def create_kiosk_device(
    body: CreateKioskDeviceBody, auth: AuthDep, uc: CreateKioskDeviceDep
) -> KioskDeviceCreatedResponse:
    # Note: org_id is not validated against the org directory — the FE picker
    # constrains input to real orgs; this endpoint trusts the caller (admin).
    command = CreateKioskDeviceCommand(
        workspace_id=auth.workspace_id, org_id=body.org_id, name=body.name
    )
    created = result_to_response(await uc(command, auth=auth))
    base = KioskDeviceResponse.from_domain(created.device)
    return KioskDeviceCreatedResponse(**base.model_dump(), token=created.token)


@router.get("", response_model=list[KioskDeviceResponse])
async def list_kiosk_devices(auth: AuthDep, uc: ListKioskDevicesDep) -> list[KioskDeviceResponse]:
    devices = result_to_response(
        await uc(ListKioskDevicesQuery(workspace_id=auth.workspace_id), auth=auth)
    )
    return [KioskDeviceResponse.from_domain(d) for d in devices]


@router.post("/{device_id}:revoke", response_model=KioskDeviceResponse)
async def revoke_kiosk_device(
    device_id: uuid.UUID, auth: AuthDep, uc: RevokeKioskDeviceDep
) -> KioskDeviceResponse:
    command = RevokeKioskDeviceCommand(workspace_id=auth.workspace_id, device_id=device_id)
    device = result_to_response(await uc(command, auth=auth))
    return KioskDeviceResponse.from_domain(device)
