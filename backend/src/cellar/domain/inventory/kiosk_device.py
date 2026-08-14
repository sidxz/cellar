"""KioskDevice aggregate — org-bound scan-station credential (spec §4.5).

The plaintext token exists only at creation time (application layer);
the domain stores its sha256 hexdigest. A device acts only on plates
whose owner org matches its org — enforced by the kiosk use cases.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.inventory.events import KioskDeviceCreated, KioskDeviceRevoked
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

MAX_NAME_LENGTH = 100
_SHA256_HEX_LENGTH = 64


class KioskDevice(AggregateRoot):
    """Admin-issued device credential for kiosk scan/confirm endpoints."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        org_id: uuid.UUID,
        name: str,
        token_hash: str,
        is_active: bool = True,
        last_seen_at: datetime | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.org_id = org_id
        self.name = name
        self.token_hash = token_hash
        self.is_active = is_active
        self.last_seen_at = last_seen_at
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        org_id: uuid.UUID,
        name: str,
        token_hash: str,
        created_by: uuid.UUID,
    ) -> KioskDevice:
        name = name.strip()
        if not name:
            raise ValidationError("Device name is required")
        if len(name) > MAX_NAME_LENGTH:
            raise ValidationError(f"Device name exceeds {MAX_NAME_LENGTH} characters")
        if len(token_hash) != _SHA256_HEX_LENGTH:
            raise ValidationError("token_hash must be a sha256 hexdigest")
        device = cls(
            workspace_id=workspace_id,
            org_id=org_id,
            name=name,
            token_hash=token_hash,
            created_by=created_by,
        )
        device.register_event(
            KioskDeviceCreated(
                aggregate_id=device.id,
                aggregate_type="KioskDevice",
                workspace_id=workspace_id,
                org_id=org_id,
                name=name,
                created_by=created_by,
            )
        )
        return device

    def revoke(self) -> None:
        """Deactivate the credential. Idempotent — a second revoke is a no-op."""
        if not self.is_active:
            return
        self.is_active = False
        self.updated_at = datetime.now(UTC)
        self.register_event(
            KioskDeviceRevoked(
                aggregate_id=self.id,
                aggregate_type="KioskDevice",
                workspace_id=self.workspace_id,
                org_id=self.org_id,
                name=self.name,
            )
        )
