"""SAR analysis (scaffold tree + UMAP cluster) use-case dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.sar_analysis.cancel_scaffold_tree_job import CancelScaffoldTreeJob
from cellar.application.sar_analysis.cancel_umap_cluster_job import CancelUmapClusterJob
from cellar.application.sar_analysis.decompose_rgroups import DecomposeRGroups
from cellar.application.sar_analysis.get_scaffold_tree_job import GetScaffoldTreeJob
from cellar.application.sar_analysis.get_umap_cluster_job import GetUmapClusterJob
from cellar.application.sar_analysis.start_scaffold_tree_job import StartScaffoldTreeJob
from cellar.application.sar_analysis.start_umap_cluster_job import StartUmapClusterJob

from ._core import _get_use_case

__all__ = [
    "CancelScaffoldTreeJobDep",
    "CancelUmapClusterJobDep",
    "DecomposeRGroupsDep",
    "GetScaffoldTreeJobDep",
    "GetUmapClusterJobDep",
    "StartScaffoldTreeJobDep",
    "StartUmapClusterJobDep",
]

StartScaffoldTreeJobDep = Annotated[
    StartScaffoldTreeJob, Depends(_get_use_case(StartScaffoldTreeJob))
]
GetScaffoldTreeJobDep = Annotated[GetScaffoldTreeJob, Depends(_get_use_case(GetScaffoldTreeJob))]
CancelScaffoldTreeJobDep = Annotated[
    CancelScaffoldTreeJob, Depends(_get_use_case(CancelScaffoldTreeJob))
]
DecomposeRGroupsDep = Annotated[DecomposeRGroups, Depends(_get_use_case(DecomposeRGroups))]
_get_start_umap_cluster_job = _get_use_case(StartUmapClusterJob)
_get_get_umap_cluster_job = _get_use_case(GetUmapClusterJob)
_get_cancel_umap_cluster_job = _get_use_case(CancelUmapClusterJob)

StartUmapClusterJobDep = Annotated[StartUmapClusterJob, Depends(_get_start_umap_cluster_job)]
GetUmapClusterJobDep = Annotated[GetUmapClusterJob, Depends(_get_get_umap_cluster_job)]
CancelUmapClusterJobDep = Annotated[CancelUmapClusterJob, Depends(_get_cancel_umap_cluster_job)]
