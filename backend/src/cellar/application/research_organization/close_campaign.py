"""CloseCampaign — lock a DRAFT campaign and optionally publish a frozen Collection.

Pipeline:
  1. ``require_editor`` auth guard.
  2. Load campaign by (workspace_id, campaign_id); ``Failure(NotFoundError)`` if missing.
  3. Inline DRAFT check — ``Failure(ValidationError)`` if not DRAFT.
  4. Re-resolve every non-override cell across all (result, channel) pairs (same
     3-branch loop as ``RefreshFromSources``).
  5. Materialize ``source_protocols`` snapshot from distinct protocol_ids on channels.
  6. Repair ND placeholder units: non-override measurements with ``unit=="-"`` get the
     real ``ReadoutDefinition.unit`` from the loaded protocols when it is non-empty.
  7. Call ``campaign.close(closed_by=..., signature_id=..., source_protocols=...)``.
     ``ValidationError`` from the aggregate (no results / no channels) → ``Failure``.
  8. Save the campaign (so the FK from collections → campaign is satisfiable).
  9. If ``campaign.publishes_collection is True``:
       - Create and freeze a ``Collection``.
       - Save the collection.
       - ``add_molecules`` for SELECTED molecule_ids (when non-empty).
       - ``campaign.set_published_collection`` + register ``CampaignPublishedCollectionCreated``.
       - Save campaign again (published_collection_id changed).
  10. ``uow.commit()``; dispatch events; return ``Success(campaign)``.

NOTE: Signature is caller-supplied (stub mode) — the API layer will integrate a
SignatureService later. The use case takes ``signature_id`` and ``signature_meaning``
in the command; ``signature_meaning`` is reserved for the audit log when
``SignatureService`` lands and is not used here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.enums import (
    CampaignDecision,
    CampaignStatus,
)
from cellar.domain.research_organization.events import (
    CampaignPublishedCollectionCreated,
)
from cellar.domain.research_organization.repository import (
    CampaignRepository,
    CollectionRepository,
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
    signature_id: uuid.UUID
    signature_meaning: str | None = (
        None  # placeholder — for the audit log when SignatureService lands
    )
    #: Override the campaign's stored ``publishes_collection`` at close time.
    #: When None, keep whatever was set at campaign creation. Lets chemists
    #: choose at sign time instead of having to remember the create-time
    #: toggle.
    publishes_collection: bool | None = None


class CloseCampaign:
    """Lock a DRAFT campaign and optionally emit a frozen Collection of SELECTED molecules.

    Signature is caller-supplied (stub mode). The constructor accepts no
    ``signature_service`` dep — the API layer will inject one later.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        collection_repo: CollectionRepository,
        protocol_repo: ProtocolRepository,
        resolver: ChannelResolver,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._collection_repo = collection_repo
        self._protocol_repo = protocol_repo
        self._resolver = resolver
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: CloseCampaignCommand,
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

            # Allow the caller to override `publishes_collection` at close
            # time — chemists shouldn't have to remember a toggle they set
            # weeks ago at campaign creation.
            if input.publishes_collection is not None:
                campaign.publishes_collection = input.publishes_collection

            # Now close the aggregate in memory.
            campaign.close(
                closed_by=input.user_id,
                signature_id=input.signature_id,
                source_protocols=source_protocols,
            )

            # Step 8 — save the closed status so the FK from
            # collections.derived_from_campaign_id → campaign.id is satisfiable.
            await self._campaign_repo.save(campaign)

            # Step 9 — optionally publish a frozen Collection.
            if campaign.publishes_collection:
                coll = Collection.create(
                    workspace_id=campaign.workspace_id,
                    name=f"Hits — {campaign.name}",
                    description=(f'Frozen output of campaign "{campaign.name}"'),
                    project_id=campaign.project_id,
                    created_by=input.user_id,
                )
                # Save BEFORE freeze so membership can be written while the
                # persisted row is still mutable — add_molecules checks
                # the persisted is_frozen flag, not the in-memory flag.
                await self._collection_repo.save(coll)

                selected_mol_ids = [
                    r.molecule_id
                    for r in campaign.results
                    if r.decision == CampaignDecision.SELECTED
                ]
                if selected_mol_ids:
                    await self._collection_repo.add_molecules(
                        campaign.workspace_id, coll.id, selected_mol_ids
                    )

                # Now freeze (in-memory) and persist the frozen state.
                coll.freeze(derived_from_campaign_id=campaign.id)
                await self._collection_repo.save(coll)

                campaign.set_published_collection(coll.id)
                campaign.register_event(
                    CampaignPublishedCollectionCreated(
                        aggregate_id=campaign.id,
                        aggregate_type="Campaign",
                        workspace_id=campaign.workspace_id,
                        collection_id=coll.id,
                    )
                )
                # Save again — published_collection_id changed.
                await self._campaign_repo.save(campaign)

            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(campaign)
