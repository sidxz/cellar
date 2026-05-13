"""Dashboard dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.dashboard.get_dashboard_stats import GetDashboardStats

from ._core import _get_use_case

__all__ = [
    "GetDashboardStatsDep",
]

GetDashboardStatsDep = Annotated[GetDashboardStats, Depends(_get_use_case(GetDashboardStats))]
