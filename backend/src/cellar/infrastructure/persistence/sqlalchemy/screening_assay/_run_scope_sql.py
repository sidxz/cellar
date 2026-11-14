"""RunScope → SQL, shared by every query that narrows runs for search columns."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import QueryableAttribute, aliased

from cellar.domain.screening_assay.enums import RunStatus
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.infrastructure.persistence.sqlalchemy._sql import any_id
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import RunModel

NOT_REJECTED: ColumnElement[bool] = RunModel.status != RunStatus.REJECTED.value


def run_scope_filters(
    run_scope: RunScope | None, workspace_id: uuid.UUID
) -> list[ColumnElement[bool]]:
    """WHERE clauses on ``RunModel`` (which must be in the FROM) for ``run_scope``.

    ``protocol_latest`` is correlated on ``RunModel.protocol_id``: each row's
    own protocol's newest non-rejected run, by run date, then creation, then id
    (deterministic — matching uses the same order).
    """
    if run_scope is None or run_scope.is_all():
        return []
    out: list[ColumnElement[bool]] = []
    if run_scope.protocol_latest:
        newest = aliased(RunModel)
        out.append(
            RunModel.id
            == select(newest.id)
            .where(
                newest.workspace_id == workspace_id,
                newest.protocol_id == RunModel.protocol_id,
                newest.status != RunStatus.REJECTED.value,
            )
            .order_by(newest.run_date.desc(), newest.created_at.desc(), newest.id.desc())
            .limit(1)
            .correlate(RunModel)
            .scalar_subquery()
        )
    if run_scope.explicit_run_ids:
        out.append(any_id(RunModel.id, run_scope.explicit_run_ids))
    if run_scope.since_date is not None:
        out.append(RunModel.run_date >= run_scope.since_date)
    if run_scope.from_date is not None and run_scope.to_date is not None:
        out.append(RunModel.run_date.between(run_scope.from_date, run_scope.to_date))
    elif run_scope.to_date is not None:
        out.append(RunModel.run_date <= run_scope.to_date)
    return out


def not_in_rejected_run(
    run_id_col: ColumnElement[Any] | QueryableAttribute[Any], workspace_id: uuid.UUID
) -> ColumnElement[bool]:
    """The row's run is not rejected — for queries that don't join ``RunModel``."""
    return ~run_id_col.in_(
        select(RunModel.id).where(
            RunModel.workspace_id == workspace_id,
            RunModel.status == RunStatus.REJECTED.value,
        )
    )
