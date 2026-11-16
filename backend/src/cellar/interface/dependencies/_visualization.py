"""Visualization workbench deps."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.visualization.get_dataset import GetVisualizationDataset
from cellar.application.visualization.get_run_row_counts import GetRunRowCounts

from ._core import _get_use_case

__all__ = [
    "GetRunRowCountsDep",
    "GetVisualizationDatasetDep",
]

GetVisualizationDatasetDep = Annotated[
    GetVisualizationDataset, Depends(_get_use_case(GetVisualizationDataset))
]
GetRunRowCountsDep = Annotated[GetRunRowCounts, Depends(_get_use_case(GetRunRowCounts))]
