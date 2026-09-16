"""Org directory port — the application layer's view of the IdP's org list.

Satisfied structurally by ``cellar.infrastructure.duar.org_directory.OrgDirectory``
(its ``OrgSummary`` rows carry ``id``); tests pass a static stub.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol, runtime_checkable


class OrgRef(Protocol):
    @property
    def id(self) -> uuid.UUID: ...


@runtime_checkable
class OrgDirectoryPort(Protocol):
    async def list_orgs(self) -> Sequence[OrgRef]: ...
