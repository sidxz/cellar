"""Dashboard statistics endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.interface.dependencies import AuthDep, SessionFactoryDep
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
    SampleModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class DashboardStats(BaseModel):
    total_compounds: int
    total_batches: int
    total_samples: int
    active_protocols: int
    total_runs: int


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    auth: AuthDep,
    session_factory: SessionFactoryDep,
) -> DashboardStats:
    """Aggregate counts for the dashboard."""
    ws = auth.workspace_id

    async with session_factory() as session:
        compounds = await session.scalar(
            select(func.count()).select_from(MoleculeModel).where(
                MoleculeModel.workspace_id == ws
            )
        )
        batches = await session.scalar(
            select(func.count()).select_from(BatchModel).where(
                BatchModel.workspace_id == ws
            )
        )
        samples = await session.scalar(
            select(func.count()).select_from(SampleModel).where(
                SampleModel.workspace_id == ws
            )
        )
        protocols = await session.scalar(
            select(func.count()).select_from(ProtocolModel).where(
                ProtocolModel.workspace_id == ws,
                ProtocolModel.status == "active",
            )
        )
        runs = await session.scalar(
            select(func.count()).select_from(RunModel).where(
                RunModel.workspace_id == ws
            )
        )

    return DashboardStats(
        total_compounds=compounds or 0,
        total_batches=batches or 0,
        total_samples=samples or 0,
        active_protocols=protocols or 0,
        total_runs=runs or 0,
    )
