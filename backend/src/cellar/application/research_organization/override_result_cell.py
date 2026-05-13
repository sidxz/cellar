"""OverrideResultCell — manually override a single (result, channel) measurement.

Replaces an existing auto-resolved CampaignMeasurement with a manual value,
preserving the original source FKs and protocol snapshot fields for audit
purposes. The override flag is set to True on the new measurement so subsequent
re-resolves skip it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    HitCall,
    ValueQualifier,
)
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class OverrideResultCellCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    result_id: uuid.UUID
    channel_id: uuid.UUID
    value: float | None
    value_qualifier: ValueQualifier
    unit: str
    hit_call: HitCall | None = None
    reason: str | None = None  # B8 audit defensibility — captured at override time


class OverrideResultCell:
    """Replace one measurement cell with a manually-entered value.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign (workspace-scoped); NotFoundError if missing.
      3. Inline DRAFT check — Failure(ValidationError) if not DRAFT.
      4. Find result by id on ``campaign.results``; NotFoundError if missing.
      5. Find existing measurement via ``result.find_measurement(channel_id)``;
         NotFoundError("CampaignMeasurement", ...) if missing.
      6. Snapshot audit fields from the existing measurement.
      7. Build a new ``CampaignMeasurement`` with ``is_manual_override=True``,
         carrying forward source FKs, protocol snapshot, and the existing id.
      8. Replace via ``remove_measurement_for_channel`` + ``add_measurement``.
      9. Bump ``campaign.updated_at``. Save + commit; dispatch; return ``Success``.

    ``CampaignMeasurement.__post_init__`` validates qualifier/value combinations
    and rejects empty unit; these propagate as ``Failure(ValidationError)``.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: OverrideResultCellCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        require_editor(auth)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(f"Cannot override cell: campaign is {campaign.status.value}")
                )

            result = next((r for r in campaign.results if r.id == input.result_id), None)
            if result is None:
                return Failure(NotFoundError("CampaignResult", str(input.result_id)))

            existing = result.find_measurement(input.channel_id)
            if existing is None:
                return Failure(NotFoundError("CampaignMeasurement", str(input.channel_id)))

            # Build the override measurement, preserving audit trail from existing.
            # Snapshot fields from migration 029 are also carried forward unchanged.
            try:
                new_m = CampaignMeasurement(
                    id=existing.id,
                    result_id=result.id,
                    channel_id=input.channel_id,
                    value=input.value,
                    value_qualifier=input.value_qualifier,
                    unit=input.unit,
                    hit_call=input.hit_call,
                    is_manual_override=True,
                    protocol_name_snapshot=existing.protocol_name_snapshot,
                    protocol_version_snapshot=existing.protocol_version_snapshot,
                    source_run_id=existing.source_run_id,
                    source_curve_id=existing.source_curve_id,
                    source_readout_id=existing.source_readout_id,
                    run_date_snapshot=existing.run_date_snapshot,
                    override_reason=input.reason,
                    test_concentration_value=existing.test_concentration_value,
                    test_concentration_unit=existing.test_concentration_unit,
                    replicate_count=existing.replicate_count,
                    qc_pass=existing.qc_pass,
                    contributing_run_ids=existing.contributing_run_ids,
                )
            except ValidationError as e:
                return Failure(e)

            result.remove_measurement_for_channel(input.channel_id)
            result.add_measurement(new_m)

            campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
