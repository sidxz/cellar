"""CloseCampaign — lock a DRAFT campaign (soft close, no signature, no collection).

Pipeline:
  1. ``require_editor`` auth guard.
  2. Load campaign by (workspace_id, campaign_id); ``Failure(NotFoundError)`` if missing.
  3. Inline DRAFT check — ``Failure(ValidationError)`` if not DRAFT.
  4. Re-resolve every non-override cell across all (result, channel) pairs (same
     3-branch loop as ``RefreshFromSources``).
  5. Materialize ``source_protocols`` snapshot from distinct protocol_ids on channels.
  6. Repair ND placeholder units: non-override measurements with ``unit=="-"`` get the
     real ``ReadoutDefinition.unit`` from the loaded protocols when it is non-empty.
  7. Call ``campaign.close(closed_by=..., note=..., source_protocols=...)``.
     ``ValidationError`` from the aggregate (no results / no channels) → ``Failure``.
  8. Save the campaign; ``uow.commit()``; dispatch events; return ``Success(campaign)``.

No signature, no published Collection — see spec §4/§5. ``ReopenCampaign``
reverses a close back to DRAFT.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
    resolution_run_ids,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import (
    CampaignStatus,
)
from cellar.domain.research_organization.repository import (
    CampaignRepository,
)
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)


@dataclass(frozen=True, kw_only=True)
class CloseCampaignCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    user_id: uuid.UUID
    note: str | None = None


class CloseCampaign:
    """Lock a DRAFT campaign. No signature, no published Collection (spec §4/§5)."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        protocol_repo: ProtocolRepository,
        resolver: ChannelResolver,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._protocol_repo = protocol_repo
        self._resolver = resolver
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: CloseCampaignCommand,
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
                    ValidationError(f"Cannot close: campaign is {campaign.status.value}")
                )

            # Step 4 — re-resolve all non-override cells
            # (same 3-branch loop as RefreshFromSources).
            channels = list(campaign.channels)
            results = list(campaign.results)

            for result in results:
                for channel in channels:
                    measurement = result.find_measurement(channel.id)
                    if measurement is not None and measurement.is_manual_override:
                        continue
                    new_measurement = await self._resolver.resolve(
                        workspace_id=input.workspace_id,
                        channel=channel,
                        result_id=result.id,
                        molecule_id=result.molecule_id,
                        run_ids=resolution_run_ids(campaign, channel),
                    )
                    # Preserve the existing measurement id when replacing — this avoids
                    # the unique constraint on (result_id, channel_id) firing when the
                    # old row is DELETEd and a new row with the same (result_id, channel_id)
                    # is INSERTed within the same flush cycle.  Same pattern as in-place update.
                    if measurement is not None:
                        new_measurement.id = measurement.id
                        result.remove_measurement_for_channel(channel.id)
                    result.add_measurement(new_measurement)

            # Step 5 — materialize source_protocols snapshot.
            distinct_protocol_ids: list[uuid.UUID] = []
            seen_ids: set[uuid.UUID] = set()
            for ch in channels:
                if ch.protocol_id not in seen_ids:
                    seen_ids.add(ch.protocol_id)
                    distinct_protocol_ids.append(ch.protocol_id)

            protocols: list[Protocol] = []
            targets_by_protocol: dict[uuid.UUID, list] = {}
            if distinct_protocol_ids:
                protocols = await self._protocol_repo.find_by_ids(
                    input.workspace_id, distinct_protocol_ids
                )
                targets_by_protocol = (
                    await self._protocol_repo.find_effective_targets_for_protocols(
                        input.workspace_id, distinct_protocol_ids
                    )
                )

            source_protocols: list[dict[str, Any]] = []
            for p in protocols:
                source_protocols.append(
                    {
                        "id": str(p.id),
                        "name": p.name,
                        "version": p.protocol_version,
                        "targets": [
                            {"id": str(t.id), "name": t.name}
                            for t in targets_by_protocol.get(p.id, [])
                        ],
                    }
                )

            # Step 6 — repair ND placeholder units ("-") on non-override measurements.
            readout_unit_by_channel: dict[uuid.UUID, str] = {}
            readout_def_by_id = {rd.id: rd for p in protocols for rd in p.readout_definitions}
            for channel in channels:
                rd = readout_def_by_id.get(channel.readout_definition_id)
                if rd is not None and rd.unit:
                    readout_unit_by_channel[channel.id] = rd.unit
            campaign.repair_placeholder_units(readout_unit_by_channel)

            # Step 7a — validate close prerequisites
            # (domain method enforces ≥1 result + ≥1 channel).
            if not campaign.results:
                return Failure(ValidationError("Cannot close campaign with no results"))
            if not campaign.channels:
                return Failure(ValidationError("Cannot close campaign with no channels"))

            # Step 7b — pre-save the campaign as DRAFT to flush re-resolved measurements
            # to Postgres BEFORE the status changes to CLOSED.
            #
            # The DB trigger installed by migration 027 blocks INSERTs on
            # campaign_measurement when campaign.status='closed'.  The SQLAlchemy cascade
            # in _update_model() sets both the closed status and any new measurement rows
            # in the same ORM graph. To keep the single-UoW contract while honouring the
            # trigger, we:
            #   1. Save as DRAFT — Postgres receives the re-resolved measurement INSERTs
            #      while the parent row is still DRAFT (trigger silent).
            #   2. Flush immediately to materialise those INSERTs in the current transaction.
            #   3. Call campaign.close() — mutates status + registers CampaignClosed event.
            #   4. Save again — Postgres receives the status flip (DRAFT→CLOSED) only;
            #      no new measurement INSERTs happen so the trigger stays silent.
            await self._campaign_repo.save(campaign)
            await self._uow.session.flush()  # type: ignore[attr-defined]

            # Now close the aggregate in memory.
            campaign.close(
                closed_by=input.user_id,
                note=input.note,
                source_protocols=source_protocols,
            )

            # Step 8 — save the closed status.
            await self._campaign_repo.save(campaign)

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
