"""Duar org directory (read-only) — distinct from provenance /organizations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.interface.dependencies import AuthDep, OrgDirectoryAllDep

router = APIRouter(prefix="/api/v1/orgs", tags=["org-directory"])


class OrgDirectoryEntryResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    enabled: bool


@router.get("", response_model=list[OrgDirectoryEntryResponse])
async def list_orgs(
    auth: AuthDep, directory: OrgDirectoryAllDep, include_disabled: bool = False
) -> list[OrgDirectoryEntryResponse]:
    """Enabled orgs (for pickers); ``include_disabled`` adds disabled ones (for names)."""
    orgs = await directory.list_orgs()
    return [
        OrgDirectoryEntryResponse(id=o.id, slug=o.slug, name=o.name, enabled=o.enabled)
        for o in orgs
        if include_disabled or o.enabled
    ]
