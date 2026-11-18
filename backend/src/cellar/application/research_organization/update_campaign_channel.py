"""UpdateCampaignChannel — mutate label, display order, selection rule, qc_filter,
or the column's test concentration.

Uses the UNSET sentinel to distinguish "don't touch this field" from
``None`` (which is a meaningful value for ``qc_filter`` — it clears it).

When a gating field (selection_rule, qc_filter, resolve_from_all_runs,
test_concentration) actually changes value,
every non-manual-override measurement for this channel across all results
is re-resolved via ``recompute_columns``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.column_resolution import ColumnCandidateQuery
from cellar.application.research_organization.recompute_columns import recompute_columns
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    SelectionRule,
)
from cellar.domain.research_organization.measurement_facts import Concentration
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


class _Unset:
    """Singleton sentinel meaning "caller did not supply this field"."""

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


@dataclass(frozen=True, kw_only=True)
class UpdateCampaignChannelCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    channel_id: uuid.UUID
    # UNSET means "don't touch"; None means "clear the value"
    label: str | object = UNSET
    selection_rule: SelectionRule | object = UNSET
    qc_filter: dict | object | None = UNSET
    display_order: int | object = UNSET
    #: Opt out of the campaign's run scope — gating, like selection_rule.
    resolve_from_all_runs: bool | object = UNSET
    #: The one concentration the column reads (spec §6.4); None clears it — gating.
    test_concentration: Concentration | object | None = UNSET


class UpdateCampaignChannel:
    """Update mutable fields on a CampaignChannel and optionally re-resolve measurements.

    Pipeline:
      1. ``require_editor`` auth guard.
      2. Load campaign; check status is DRAFT.
      3. Locate the channel by id.
      4. Detect which fields are changing (sentinel-aware).
      5. Mutate label / display_order in-place when supplied.
      6. If any gating field (selection_rule, qc_filter, resolve_from_all_runs,
         test_concentration) changed, re-resolve
         every non-manual-override measurement for this channel.
      7. Bump ``campaign.updated_at``.
      8. Save + commit; dispatch events; return ``Success(campaign)``.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        query: ColumnCandidateQuery,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._query = query
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: UpdateCampaignChannelCommand,
        auth: AuthContext | None = None,
    ) -> Result[Campaign, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(f"Cannot update channel: campaign is {campaign.status.value}")
                )

            channel = next((c for c in campaign.channels if c.id == input.channel_id), None)
            if channel is None:
                return Failure(NotFoundError("CampaignChannel", str(input.channel_id)))

            # Determine which gating fields actually changed value
            gating_changed = False

            if not isinstance(input.selection_rule, _Unset):
                if input.selection_rule != channel.selection_rule:
                    gating_changed = True
                channel.selection_rule = input.selection_rule  # type: ignore[assignment]

            if not isinstance(input.qc_filter, _Unset):
                if input.qc_filter != channel.qc_filter:
                    gating_changed = True
                channel.qc_filter = input.qc_filter  # type: ignore[assignment]

            if not isinstance(input.resolve_from_all_runs, _Unset):
                if input.resolve_from_all_runs != channel.resolve_from_all_runs:
                    gating_changed = True
                channel.resolve_from_all_runs = bool(input.resolve_from_all_runs)

            if not isinstance(input.test_concentration, _Unset):
                if input.test_concentration != channel.test_concentration:
                    gating_changed = True
                channel.test_concentration = input.test_concentration  # type: ignore[assignment]

            if not isinstance(input.label, _Unset):
                label = input.label
                if not isinstance(label, str) or not label.strip():
                    return Failure(ValidationError("CampaignChannel.label must not be empty"))
                channel.label = label.strip()

            if not isinstance(input.display_order, _Unset):
                try:
                    channel.reorder(input.display_order)  # type: ignore[arg-type]
                except ValidationError as exc:
                    return Failure(exc)

            # Re-resolve non-override measurements when gating fields changed
            if gating_changed:
                await recompute_columns(query=self._query, campaign=campaign, channels=[channel])

            campaign.updated_at = datetime.now(UTC)
            await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
