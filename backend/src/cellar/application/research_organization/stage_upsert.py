"""Get-or-create for the ``stage_name`` import paths.

``add_results_from_runs`` and ``mirror_protocol_channels`` both let the
chemist name a stage while importing. Re-running an import with the same
stage name is the normal workflow (tweak a threshold, re-import), so a
matching name updates that stage's criteria instead of failing on
``Campaign``'s name-uniqueness rule.
"""

from __future__ import annotations

import uuid

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_stage import (
    UNSET,
    CampaignStage,
    StageCriterion,
    normalize_stage_name,
)
from cellar.domain.research_organization.enums import StageKind
from cellar.domain.shared.errors import ValidationError


def upsert_stage_by_name(
    campaign: Campaign,
    *,
    name: str,
    criteria: list[StageCriterion],
    parent_stage_id: uuid.UUID | None,
) -> tuple[CampaignStage, bool]:
    """Reuse the stage with this name (case-insensitive) and replace its criteria,
    else append a new criteria stage. Returns (stage, created). A manual stage of
    that name is a ValidationError — its membership is hand-picked, not rule-driven.

    Raises ``ValidationError`` (also from the domain guards: unknown/cyclic
    parent, a criterion on a foreign channel, a non-DRAFT campaign). Callers
    already translate that into ``Failure``.
    """
    normalized = normalize_stage_name(name)
    existing = next(
        (s for s in campaign.stages if s.name.lower() == normalized.lower()),
        None,
    )
    if existing is None:
        stage = CampaignStage(
            campaign_id=campaign.id,
            name=normalized,
            display_order=max((s.display_order for s in campaign.stages), default=-1) + 1,
            criteria=criteria,
            parent_stage_id=parent_stage_id,
        )
        campaign.add_stage(stage)
        return stage, True

    if existing.kind == StageKind.MANUAL:
        raise ValidationError(
            f"CampaignStage '{existing.name}' is a manual stage; its membership is "
            "hand-picked, not rule-driven. Rename the imported stage or convert "
            "this one to a criteria stage."
        )
    # An omitted parent leaves the existing parent alone — re-importing into a
    # stage must not silently detach it from its funnel.
    campaign.update_stage(
        existing.id,
        criteria=criteria,
        parent_stage_id=parent_stage_id if parent_stage_id is not None else UNSET,
    )
    return existing, False
