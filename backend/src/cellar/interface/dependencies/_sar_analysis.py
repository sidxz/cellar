"""SAR analysis (scaffold tree + UMAP cluster + R-group decomposition) use-case dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.sar_analysis.activity_heatmap import FetchActivityHeatmap
from cellar.application.sar_analysis.cancel_activity_projection import CancelActivityProjection
from cellar.application.sar_analysis.cancel_decomposition_run import CancelDecompositionRun
from cellar.application.sar_analysis.cancel_scaffold_tree_job import CancelScaffoldTreeJob
from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.application.sar_analysis.decomposition_rows import FetchDecompositionRows
from cellar.application.sar_analysis.get_activity_projection import GetActivityProjection
from cellar.application.sar_analysis.get_decomposition_run import GetDecompositionRun
from cellar.application.sar_analysis.get_scaffold_tree_job import GetScaffoldTreeJob
from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob
from cellar.application.sar_analysis.save_decomposition_collection import (
    SaveDecompositionCollection,
)
from cellar.application.sar_analysis.start_activity_projection import StartActivityProjection
from cellar.application.sar_analysis.start_decomposition_run import StartDecompositionRun
from cellar.application.sar_analysis.start_scaffold_tree_job import StartScaffoldTreeJob
from cellar.application.sar_analysis.start_umap_cluster_job import StartUmapClusterJob

from ._core import _get_use_case

__all__ = [
    "CancelActivityProjectionDep",
    "CancelDecompositionRunDep",
    "CancelScaffoldTreeJobDep",
    "CancelUmapClusterJobDep",
    "FetchActivityHeatmapDep",
    "FetchDecompositionRowsDep",
    "GetActivityProjectionDep",
    "GetDecompositionRunDep",
    "GetScaffoldTreeJobDep",
    "GetUmapClusterJobDep",
    "SaveDecompositionCollectionDep",
    "StartActivityProjectionDep",
    "StartDecompositionRunDep",
    "StartScaffoldTreeJobDep",
    "StartUmapClusterJobDep",
]

StartActivityProjectionDep = Annotated[
    StartActivityProjection, Depends(_get_use_case(StartActivityProjection))
]
GetActivityProjectionDep = Annotated[
    GetActivityProjection, Depends(_get_use_case(GetActivityProjection))
]
CancelActivityProjectionDep = Annotated[
    CancelActivityProjection, Depends(_get_use_case(CancelActivityProjection))
]
FetchActivityHeatmapDep = Annotated[
    FetchActivityHeatmap, Depends(_get_use_case(FetchActivityHeatmap))
]
StartScaffoldTreeJobDep = Annotated[
    StartScaffoldTreeJob, Depends(_get_use_case(StartScaffoldTreeJob))
]
GetScaffoldTreeJobDep = Annotated[GetScaffoldTreeJob, Depends(_get_use_case(GetScaffoldTreeJob))]
CancelScaffoldTreeJobDep = Annotated[
    CancelScaffoldTreeJob, Depends(_get_use_case(CancelScaffoldTreeJob))
]
StartDecompositionRunDep = Annotated[
    StartDecompositionRun, Depends(_get_use_case(StartDecompositionRun))
]
GetDecompositionRunDep = Annotated[
    GetDecompositionRun, Depends(_get_use_case(GetDecompositionRun))
]
CancelDecompositionRunDep = Annotated[
    CancelDecompositionRun, Depends(_get_use_case(CancelDecompositionRun))
]
FetchDecompositionRowsDep = Annotated[
    FetchDecompositionRows, Depends(_get_use_case(FetchDecompositionRows))
]
SaveDecompositionCollectionDep = Annotated[
    SaveDecompositionCollection, Depends(_get_use_case(SaveDecompositionCollection))
]
_get_start_umap_cluster_job = _get_use_case(StartUmapClusterJob)
_get_get_umap_cluster_job = _get_use_case(GetUmapClusterJob)
_get_cancel_umap_cluster_job = _get_use_case(CancelUmapClusterJob)

StartUmapClusterJobDep = Annotated[StartUmapClusterJob, Depends(_get_start_umap_cluster_job)]
GetUmapClusterJobDep = Annotated[GetUmapClusterJob, Depends(_get_get_umap_cluster_job)]
CancelUmapClusterJobDep = Annotated[CancelUmapClusterJob, Depends(_get_cancel_umap_cluster_job)]
