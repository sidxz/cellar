"""Org directory port — the application layer's view of the IdP's org list.

Satisfied structurally by ``cellar.infrastructure.duar.org_directory.OrgDirectory``
(its ``OrgSummary`` rows carry ``id``); tests pass a static stub.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from cellar.domain.shared.errors import ValidationError


class OrgRef(Protocol):
    @property
    def id(self) -> uuid.UUID: ...

    @property
    def enabled(self) -> bool: ...


@runtime_checkable
class OrgDirectoryPort(Protocol):
    async def list_orgs(self) -> Sequence[OrgRef]: ...


async def unpickable_org(directory: OrgDirectoryPort, org_id: uuid.UUID) -> ValidationError | None:
    """The reason ``org_id`` cannot be picked (unknown to Duar, or disabled), else None."""
    for org in await directory.list_orgs():
        if org.id == org_id:
            return None if org.enabled else ValidationError(f"Organization {org_id} is disabled")
    return ValidationError(f"Unknown organization {org_id}")
