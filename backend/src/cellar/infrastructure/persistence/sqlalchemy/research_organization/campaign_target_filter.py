"""Campaign-by-target filter subquery.

Returns a Select of campaign ids whose measurements reference runs that carry
the given targets (``match_all=False`` = any; ``match_all=True`` = all).
A campaign "has" target T if any of its measurements references a run
(``source_run_id`` or a member of ``contributing_run_ids``) that has T in
``run_targets``. The run is joined to ``RunModel`` and scoped on
``workspace_id`` so the filter path enforces owner-side tenant isolation,
mirroring the ``project_targets`` chips projection (defense-in-depth).

Note: ``match_all=True`` with a single target id is equivalent to
``match_all=False`` — the ``HAVING count == 1`` matches any campaign that
touches that one target.
"""

from __future__ import annotations

import uuid

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.sql import Select

from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignMeasurementModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    RunModel,
    run_targets,
)


def campaign_target_filter_subquery(
    target_ids: list[uuid.UUID], *, match_all: bool, workspace_id: uuid.UUID
) -> Select:
    unique_ids = list(dict.fromkeys(target_ids))  # dedup, preserve order
    run_match = or_(
        run_targets.c.run_id == CampaignMeasurementModel.source_run_id,
        run_targets.c.run_id == func.any(CampaignMeasurementModel.contributing_run_ids),
    )
    stmt = (
        select(CampaignResultModel.campaign_id)
        .select_from(CampaignResultModel)
        .join(
            CampaignMeasurementModel,
            CampaignMeasurementModel.result_id == CampaignResultModel.id,
        )
        .join(run_targets, run_match)
        .join(RunModel, run_targets.c.run_id == RunModel.id)
        .where(
            run_targets.c.target_id.in_(unique_ids),
            RunModel.workspace_id == workspace_id,
        )
    )
    if match_all:
        stmt = stmt.group_by(CampaignResultModel.campaign_id).having(
            func.count(distinct(run_targets.c.target_id)) == len(unique_ids)
        )
    else:
        stmt = stmt.distinct()
    return stmt
