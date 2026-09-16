"""Duar org directory (read-only) — distinct from provenance /organizations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.interface.dependencies import AuthDep, OrgDirectoryDep

router = APIRouter(prefix="/api/v1/orgs", tags=["org-directory"])


class OrgDirectoryEntryResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


@router.get("", response_model=list[OrgDirectoryEntryResponse])
async def list_orgs(auth: AuthDep, directory: OrgDirectoryDep) -> list[OrgDirectoryEntryResponse]:
    orgs = await directory.list_orgs()
    return [OrgDirectoryEntryResponse(id=o.id, slug=o.slug, name=o.name) for o in orgs]
