"""OrgPlatePolicy aggregate — per-org plate loan policy within a workspace.

Identity: composite ``(workspace_id, org_id)`` — unlike ``WorkspaceSettings``,
``id`` is a regular generated surrogate key, not the scoping key itself, since
a workspace has many orgs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.inventory.enums import LoanConfirmationMode
from cellar.domain.inventory.events import OrgPlatePolicySet
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

DEFAULT_DUE_DAYS = 14


class OrgPlatePolicy(AggregateRoot):
    """Per-org policy for plate loan approval/confirmation."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        org_id: uuid.UUID,
        require_approval: bool = True,
        confirmation: LoanConfirmationMode = LoanConfirmationMode.ADMIN_CONFIRM,
        default_due_days: int | None = DEFAULT_DUE_DAYS,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.org_id = org_id
        self.require_approval = require_approval
        self.confirmation = confirmation
        self.default_due_days = default_due_days

    @classmethod
    def create_default(cls, *, workspace_id: uuid.UUID, org_id: uuid.UUID) -> OrgPlatePolicy:
        """Factory for an org with no policy row yet — all default values."""
        return cls(workspace_id=workspace_id, org_id=org_id)

    def update(self, **fields: object) -> None:
        """Set fields present in ``fields``, validate, and emit ``OrgPlatePolicySet``.

        Accepted keys: require_approval, confirmation, default_due_days.
        """
        if "default_due_days" in fields:
            days = fields["default_due_days"]
            if days is not None and (
                not isinstance(days, int) or isinstance(days, bool) or days < 1
            ):
                raise ValidationError(f"default_due_days must be None or >= 1 (got: {days!r})")

        for key in ("require_approval", "confirmation", "default_due_days"):
            if key in fields:
                setattr(self, key, fields[key])

        self.updated_at = datetime.now(UTC)
        self.register_event(
            OrgPlatePolicySet(
                aggregate_id=self.id,
                aggregate_type="OrgPlatePolicy",
                workspace_id=self.workspace_id,
                org_id=self.org_id,
            )
        )
