"""Build-identity endpoint (`GET /version`) — unauthenticated, no DB.

Composes the pure ``build_info()`` with the runtime ``environment`` (a settings
concern) into the response.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.version import build_info

router = APIRouter()


class VersionResponse(BaseModel):
    """Identity of the running backend build."""

    name: str
    version: str
    git_sha: str
    build_date: str
    environment: str


@router.get("/version", response_model=VersionResponse, tags=["meta"])
async def get_version() -> VersionResponse:
    info = build_info()
    return VersionResponse(
        name="cellar-backend",
        version=info.version,
        git_sha=info.git_sha,
        build_date=info.build_date,
        environment=os.environ.get("ENVIRONMENT", "development"),
    )
