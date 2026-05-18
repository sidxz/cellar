"""SAR analysis (scaffold tree) use-case dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.sar_analysis.cancel_scaffold_tree_job import CancelScaffoldTreeJob
from cellar.application.sar_analysis.get_scaffold_tree_job import GetScaffoldTreeJob
from cellar.application.sar_analysis.start_scaffold_tree_job import StartScaffoldTreeJob

from ._core import _get_use_case

__all__ = [
    "StartScaffoldTreeJobDep",
    "GetScaffoldTreeJobDep",
    "CancelScaffoldTreeJobDep",
]

StartScaffoldTreeJobDep = Annotated[StartScaffoldTreeJob, Depends(_get_use_case(StartScaffoldTreeJob))]
GetScaffoldTreeJobDep = Annotated[GetScaffoldTreeJob, Depends(_get_use_case(GetScaffoldTreeJob))]
CancelScaffoldTreeJobDep = Annotated[CancelScaffoldTreeJob, Depends(_get_use_case(CancelScaffoldTreeJob))]
