"""Dashboard bindings."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from chem_vault.application.dashboard.get_dashboard_stats import GetDashboardStats
from chem_vault.infrastructure.persistence.sqlalchemy.dashboard_reader import (
    SQLAlchemyDashboardReader,
)


def register_dashboard(container: Container) -> None:
    container.define(
        GetDashboardStats,
        lambda c: GetDashboardStats(SQLAlchemyDashboardReader(c[async_sessionmaker])),
    )
