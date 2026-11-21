"""Use-case side of a campaign managed by another app: the refusal as a railway Failure."""

from __future__ import annotations

from returns.result import Failure

from cellar.domain.research_organization.campaign_management import (
    CampaignManagedElsewhereError,
    CampaignManagement,
    ensure_writable_by,
)


def managed_elsewhere(
    management: CampaignManagement | None, acting_service: str | None
) -> Failure[CampaignManagedElsewhereError] | None:
    """A Failure when the campaign is managed by an app other than the caller, else None.

    Checked right after the campaign is found and before its status, in every use case that
    changes a campaign's lifecycle or structure: the managing app then meets every other rule
    exactly as on an unmanaged campaign, and everyone else is told where to go.
    """
    try:
        ensure_writable_by(management, acting_service)
    except CampaignManagedElsewhereError as exc:
        return Failure(exc)
    return None
