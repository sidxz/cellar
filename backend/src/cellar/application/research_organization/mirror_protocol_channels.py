"""MirrorProtocolChannels — bulk-create campaign channels from a protocol.

Chemist's shortcut: instead of clicking ``+ Channel`` N times for every
readout in a protocol, mirror the whole protocol's readout structure in
one transaction. For each readout:

- DR with declared intercepts → one channel per intercept (primary stores
  ``intercept_key = None`` per Surface #7 convention; secondaries store
  ``{kind, level}``).
- DR with no declared intercepts → one channel for the implicit primary.
- Non-DR → one channel sourced from ``readout_data``, picking the
  readout's primary normalization layer if any (matches the
  channel-popover's auto-pick).

Idempotent: channels with the same ``(stage_id, protocol_id,
readout_definition_id, normalization_applied, intercept_key)`` are silently
skipped, so the chemist (or daikon, on every sync) can re-trigger without
duplicates.

The single-channel ``AddCampaignChannel`` use case stays the authoritative
path for one-at-a-time creation; this just iterates the same shape inside
one UoW for atomicity.

The columns go on a stage (spec §10):

- ``stage_id``: on that stage. Its criteria are never touched.
- ``stage_name`` (with ``parent_stage_id``): the stage is always created or reused
  (by case-insensitive name) and the columns go on it, even when no recommendation
  maps, so no stray campaign column is left. The protocol's
  ``recommended_hit_criteria`` replace the stage's criteria only when some map onto
  the columns this mirror touched (created or already present), via
  ``_match_recommended_threshold``. Numeric only: a recommendation using the
  string-based ``in`` operator is skipped.
- Neither: campaign columns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.research_organization.campaign_management import managed_elsewhere
from cellar.application.research_organization.column_resolution import ColumnCandidateQuery
from cellar.application.research_organization.recompute_columns import recompute_columns
from cellar.application.research_organization.stage_upsert import (
    get_or_create_stage,
    set_stage_criteria,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_stage import StageCriterion
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.screening_assay.enums import ReadoutDataType, primary_normalization
from cellar.domain.screening_assay.protocol import ReadoutDefinition
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import (
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey


@dataclass(frozen=True, kw_only=True)
class MirrorProtocolChannelsCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    protocol_id: uuid.UUID
    #: The stage the columns go on; its criteria are never touched.
    stage_id: uuid.UUID | None = None
    #: When no ``stage_id``: creates — or reuses, by case-insensitive name — this
    #: stage and puts the columns on it; the protocol's recommended criteria that
    #: map onto them replace its criteria.
    stage_name: str | None = None
    #: Parent for the stage ``stage_name`` creates, making it a child in the
    #: funnel. On reuse of an existing stage, ``None`` leaves the current
    #: parent alone.
    parent_stage_id: uuid.UUID | None = None
    # The realm app making the call (verified X-Service-Token); None for ChemCellar's own client.
    acting_service: str | None = None


@dataclass
class MirrorProtocolChannelsOutcome:
    campaign: Campaign
    channels_created: int
    channels_skipped: int
    stage_created: bool


def _intercept_label(spec) -> str:
    """Canonical chemist-facing label for one intercept spec.

    Mirrors the FE's ``interceptLabel(spec)`` helper so channel labels
    look the same whether the chemist mirrors a protocol or adds channels
    one-at-a-time via the popover. Uses spec.label if set, otherwise
    ``${KIND}${LEVEL}`` with integer levels rendered without a decimal.
    """
    if getattr(spec, "label", None):
        return spec.label
    level = spec.level
    lvl_str = str(int(level)) if level % 1 == 0 else f"{level:g}"
    return f"{spec.kind.value.upper()}{lvl_str}"


def _channel_label(
    rd: ReadoutDefinition,
    spec,
    is_multi_intercept: bool,
    primary_spec=None,
) -> str:
    """Build the channel label for one (readout, intercept) pair.

    Single-channel readouts (non-DR or single-intercept DR) use ``rd.name``.
    Multi-intercept DR readouts prefix the rd name with the intercept's
    canonical label — except for CDD-style readouts where ``rd.name``
    matches the *primary* intercept's label (in which case the prefix is
    redundant for every channel emitted from this readout: "EC50 EC50" /
    "EC50 EC90" → "EC50" / "EC90"). The dedup tracks what Surface #7 /
    commit #15 already does for ``add-from-runs``.
    """
    if not is_multi_intercept:
        return rd.name
    intercept_label = _intercept_label(spec)
    primary_label = _intercept_label(primary_spec) if primary_spec else None
    if primary_label is not None and rd.name == primary_label:
        return intercept_label
    return f"{rd.name} {intercept_label}"


# Stage criteria are numeric-only (StageCriterion forbids the string-based
# ``in`` operator); a recommended criterion using it is skipped when mapping
# onto a mirrored stage.
_NUMERIC_STAGE_OPERATORS = {"lt", "lte", "gt", "gte", "between", "not_between"}


def _match_recommended_threshold(
    recommended: list,
    readout_name: str,
    intercept_key: InterceptKey | None,
) -> HitCriterion | None:
    """Pick a recommended criterion for one (readout_name, intercept_key) pair.

    Prefers a criterion whose ``intercept_key`` matches exactly (treats the
    None case as the primary). Falls back to a same-readout-name criterion
    only when the channel targets the primary intercept — non-primary
    channels without an exact match get no auto-threshold to avoid
    surfacing the wrong number as a hit criterion.
    """
    if not recommended:
        return None
    name_matches = [c for c in recommended if c.readout_name == readout_name]
    if not name_matches:
        return None
    exact = next((c for c in name_matches if c.intercept_key == intercept_key), None)
    if exact is not None:
        return exact
    if intercept_key is None:
        return name_matches[0]
    return None


class MirrorProtocolChannels:
    """Iterates a protocol's readouts and creates campaign channels for each."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        protocol_repo: ProtocolRepository,
        query: ColumnCandidateQuery,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._protocol_repo = protocol_repo
        self._query = query
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: MirrorProtocolChannelsCommand,
        auth: AuthContext | None = None,
    ) -> Result[MirrorProtocolChannelsOutcome, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))

            if refused := managed_elsewhere(campaign.management, input.acting_service):
                return refused
            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(f"Cannot mirror protocol: campaign is {campaign.status.value}")
                )

            protocol = await self._protocol_repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            # The stage comes before its columns: a column's stage must exist.
            stage = None
            stage_created = False
            stage_touched = False  # the stage_name path created or rewrote it: persist
            if input.stage_id is not None:
                stage = campaign.find_stage(input.stage_id)
                if stage is None:
                    return Failure(NotFoundError("CampaignStage", str(input.stage_id)))
            elif input.stage_name:
                try:
                    stage, stage_created = get_or_create_stage(
                        campaign, name=input.stage_name, parent_stage_id=input.parent_stage_id
                    )
                except ValidationError as e:
                    return Failure(e)
                stage_touched = True
            stage_id = stage.id if stage else None

            existing_channels = {
                (
                    ch.stage_id,
                    ch.protocol_id,
                    ch.readout_definition_id,
                    ch.normalization_applied,
                    ch.intercept_key,
                ): ch
                for ch in campaign.channels
            }
            next_order = max((ch.display_order for ch in campaign.channels), default=-1) + 1

            channels_created = 0
            channels_skipped = 0
            # (readout_name, intercept_key, channel) for every readout this
            # mirror touched — created just now or already present — so a
            # requested stage_name can map recommended criteria onto either.
            channel_targets: list[tuple[str, InterceptKey | None, CampaignChannel]] = []
            # Channels created just now; their cells are resolved after the
            # stage step so a stage validation failure costs no resolver work.
            new_channels: list[CampaignChannel] = []

            for rd in protocol.readout_definitions:
                is_dr = rd.data_type == ReadoutDataType.DOSE_RESPONSE
                source_kind = (
                    ChannelSourceKind.DOSE_RESPONSE_CURVE
                    if is_dr
                    else ChannelSourceKind.READOUT_DATA
                )
                normalization = None if is_dr else primary_normalization(rd.normalizations)

                # Build the list of (intercept_key, spec, is_multi) tuples to
                # emit. Non-DR + single-intercept DR collapse to one tuple
                # with intercept_key=None. Multi-intercept DR emits N tuples;
                # the primary's spec is still used to compute the (possibly
                # deduped) label even though its intercept_key is null.
                if is_dr and rd.dose_response_config:
                    specs = list(rd.dose_response_config.intercepts or ())
                else:
                    specs = []

                if len(specs) >= 2:
                    items: list[tuple[InterceptKey | None, object]] = [(None, specs[0])]
                    for spec in specs[1:]:
                        ik = InterceptKey(kind=spec.kind.value, level=float(spec.level))
                        items.append((ik, spec))
                    is_multi = True
                else:
                    items = [(None, specs[0] if specs else None)]
                    is_multi = False

                primary_spec = specs[0] if specs else None
                for intercept_key, spec in items:
                    key = (stage_id, protocol.id, rd.id, normalization, intercept_key)
                    existing = existing_channels.get(key)
                    if existing is not None:
                        channels_skipped += 1
                        channel_targets.append((rd.name, intercept_key, existing))
                        continue

                    label = _channel_label(rd, spec, is_multi, primary_spec) if spec else rd.name

                    try:
                        channel = CampaignChannel(
                            campaign_id=campaign.id,
                            label=label,
                            protocol_id=protocol.id,
                            readout_definition_id=rd.id,
                            source_kind=source_kind,
                            selection_rule=SelectionRule.LATEST_RUN,
                            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
                            display_order=next_order,
                            normalization_applied=normalization,
                            intercept_key=intercept_key,
                            stage_id=stage_id,
                        )
                        campaign.add_channel(channel)
                    except ValidationError as e:
                        return Failure(e)
                    next_order += 1
                    existing_channels[key] = channel
                    channels_created += 1
                    channel_targets.append((rd.name, intercept_key, channel))
                    new_channels.append(channel)

            # stage_name only: the protocol's recommended criteria, mapped onto the
            # channels this mirror touched (created or already present), replace
            # the stage's criteria when some map. Numeric-only; a recommendation
            # with no match, or using the string-based ``in`` operator, contributes
            # nothing. A stage_id mirror never touches criteria.
            if stage_touched and stage is not None:
                recommended = protocol.recommended_hit_criteria or []
                stage_criteria: list[StageCriterion] = []
                for readout_name, intercept_key, channel in channel_targets:
                    matched = _match_recommended_threshold(
                        recommended, readout_name, intercept_key
                    )
                    if matched is None or matched.operator not in _NUMERIC_STAGE_OPERATORS:
                        continue
                    stage_criteria.append(
                        StageCriterion(
                            channel_id=channel.id,
                            operator=matched.operator,
                            value=matched.value,
                        )
                    )
                if stage_criteria:
                    try:
                        set_stage_criteria(campaign, stage, stage_criteria)
                    except ValidationError as e:
                        return Failure(e)

            # Resolve cells for the newly created channels — last, so the
            # cheap validation above can bail out first.
            await recompute_columns(query=self._query, campaign=campaign, channels=new_channels)

            if channels_created > 0 or stage_touched:
                await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            MirrorProtocolChannelsOutcome(
                campaign=campaign,
                channels_created=channels_created,
                channels_skipped=channels_skipped,
                stage_created=stage_created,
            )
        )
