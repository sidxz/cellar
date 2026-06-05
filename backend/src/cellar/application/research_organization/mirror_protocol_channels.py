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

Idempotent: channels with the same ``(protocol_id, readout_definition_id,
normalization_applied, intercept_key)`` are silently skipped, so the
chemist can re-trigger after editing the protocol's intercepts without
duplicates.

The single-channel ``AddCampaignChannel`` use case stays the authoritative
path for one-at-a-time creation; this just iterates the same shape inside
one UoW for atomicity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.research_organization.repository import CampaignRepository
from cellar.domain.screening_assay.enums import ReadoutDataType
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


@dataclass
class MirrorProtocolChannelsOutcome:
    campaign: Campaign
    channels_created: int
    channels_skipped: int


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


def _primary_normalization(rd: ReadoutDefinition) -> str | None:
    """Pick the readout's primary normalization layer (non-'none') if any.

    Matches the channel-popover's create-mode auto-pick: chemists usually
    want the computed (% inhibition / z-score / ...) layer rather than the
    raw signal. Returns None when the readout declares no normalizations.
    """
    for norm in rd.normalizations or []:
        v = norm.value if hasattr(norm, "value") else norm
        if v != "none":
            return v
    return None


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
        input: MirrorProtocolChannelsCommand,
        auth: AuthContext | None = None,
    ) -> Result[MirrorProtocolChannelsOutcome, DomainError]:
        require_editor(auth)

        async with self._uow:
            campaign = await self._campaign_repo.find_by_id_in_workspace(
                input.workspace_id, input.campaign_id
            )
            if campaign is None:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))
            if campaign.status != CampaignStatus.DRAFT:
                return Failure(
                    ValidationError(f"Cannot mirror protocol: campaign is {campaign.status.value}")
                )

            protocol = await self._protocol_repo.find_by_id_in_workspace(
                input.workspace_id, input.protocol_id
            )
            if protocol is None:
                return Failure(NotFoundError("Protocol", str(input.protocol_id)))

            existing_keys = {
                (
                    ch.protocol_id,
                    ch.readout_definition_id,
                    ch.normalization_applied,
                    ch.intercept_key,
                )
                for ch in campaign.channels
            }
            next_order = max((ch.display_order for ch in campaign.channels), default=-1) + 1

            recommended = list(protocol.recommended_hit_criteria or [])
            channels_created = 0
            channels_skipped = 0

            for rd in protocol.readout_definitions:
                is_dr = rd.data_type == ReadoutDataType.DOSE_RESPONSE
                source_kind = (
                    ChannelSourceKind.DOSE_RESPONSE_CURVE
                    if is_dr
                    else ChannelSourceKind.READOUT_DATA
                )
                normalization = None if is_dr else _primary_normalization(rd)

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
                    key = (protocol.id, rd.id, normalization, intercept_key)
                    if key in existing_keys:
                        channels_skipped += 1
                        continue

                    label = _channel_label(rd, spec, is_multi, primary_spec) if spec else rd.name
                    threshold = _match_recommended_threshold(recommended, rd.name, intercept_key)

                    try:
                        channel = CampaignChannel(
                            campaign_id=campaign.id,
                            label=label,
                            protocol_id=protocol.id,
                            readout_definition_id=rd.id,
                            source_kind=source_kind,
                            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
                            display_order=next_order,
                            hit_threshold=threshold,
                            normalization_applied=normalization,
                            intercept_key=intercept_key,
                        )
                        campaign.add_channel(channel)
                    except ValidationError as e:
                        return Failure(e)
                    next_order += 1
                    existing_keys.add(key)
                    channels_created += 1

                    for result in campaign.results:
                        measurement = await self._resolver.resolve(
                            workspace_id=input.workspace_id,
                            channel=channel,
                            result_id=result.id,
                            molecule_id=result.molecule_id,
                        )
                        result.add_measurement(measurement)

            if channels_created > 0:
                await self._campaign_repo.save(campaign)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(
            MirrorProtocolChannelsOutcome(
                campaign=campaign,
                channels_created=channels_created,
                channels_skipped=channels_skipped,
            )
        )
