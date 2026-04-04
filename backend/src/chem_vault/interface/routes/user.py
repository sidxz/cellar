"""User preferences endpoints — cross-device settings sync."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.infrastructure.persistence.sqlalchemy.user_preferences import (
    UserPreferencesModel,
)
from chem_vault.interface.app import sentinel

router = APIRouter(prefix="/api/v1/user", tags=["user"])

AuthDep = Annotated[Any, Depends(sentinel.get_auth)]


async def _get_session(request: Any) -> AsyncSession:
    """Get a raw async session from the container (no UoW needed for simple CRUD)."""
    from chem_vault.interface.dependencies import get_container

    container = get_container(request)
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = container[async_sessionmaker]
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


@router.get("/preferences")
async def get_preferences(auth: AuthDep, session: SessionDep) -> dict:
    """Get user preferences for the current workspace."""
    result = await session.execute(
        select(UserPreferencesModel).where(
            UserPreferencesModel.workspace_id == auth.workspace_id,
            UserPreferencesModel.user_id == auth.user_id,
        )
    )
    row = result.scalar_one_or_none()
    return row.preferences if row else {}


@router.patch("/preferences")
async def update_preferences(
    body: dict,
    auth: AuthDep,
    session: SessionDep,
) -> dict:
    """Upsert user preferences for the current workspace (partial merge)."""
    # Fetch existing or create
    result = await session.execute(
        select(UserPreferencesModel).where(
            UserPreferencesModel.workspace_id == auth.workspace_id,
            UserPreferencesModel.user_id == auth.user_id,
        )
    )
    row = result.scalar_one_or_none()

    if row:
        merged = {**row.preferences, **body}
        row.preferences = merged
    else:
        row = UserPreferencesModel(
            workspace_id=auth.workspace_id,
            user_id=auth.user_id,
            preferences=body,
        )
        session.add(row)

    await session.commit()
    await session.refresh(row)
    return row.preferences
