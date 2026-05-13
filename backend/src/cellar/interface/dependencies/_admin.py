"""Admin (hard-delete, cascade) dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.admin.admin_hard_delete import AdminHardDelete
from cellar.application.admin.cascade_delete import CascadeDelete
from cellar.application.admin.cascade_preview import CascadePreview

from ._core import _get_use_case

__all__ = [
    "AdminHardDeleteDep",
    "CascadePreviewDep",
    "CascadeDeleteDep",
]

AdminHardDeleteDep = Annotated[AdminHardDelete, Depends(_get_use_case(AdminHardDelete))]
CascadePreviewDep = Annotated[CascadePreview, Depends(_get_use_case(CascadePreview))]
CascadeDeleteDep = Annotated[CascadeDelete, Depends(_get_use_case(CascadeDelete))]
