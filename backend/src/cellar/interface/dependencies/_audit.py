"""Audit query dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.audit.query_audit import GetAuditOperation, ListAuditOperations

from ._core import _get_use_case

__all__ = [
    "GetAuditOperationDep",
    "ListAuditOperationsDep",
]

ListAuditOperationsDep = Annotated[
    ListAuditOperations, Depends(_get_use_case(ListAuditOperations))
]
GetAuditOperationDep = Annotated[GetAuditOperation, Depends(_get_use_case(GetAuditOperation))]
