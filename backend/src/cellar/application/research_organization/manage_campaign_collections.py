"""Campaign-collection association use cases — link / unlink a library.

The campaign twin of ``manage_run_collections``: the libraries a campaign
screened are an M2M association, not aggregate state, so the status check is a
column-only query, the audit event is constructed here, and an idempotent
re-add bumps no version and emits nothing. Coverage is computed live elsewhere
(``campaign_collection_coverage``); these use cases only manage links.

A closed or superseded campaign refuses link edits, mirroring the locked-run
rule — the libraries a campaign screened are part of what closing freezes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.events import (
    CampaignCollectionAdded,
    CampaignCollectionRemoved,
)
from cellar.domain.research_organization.repository import (
    CampaignCollectionLinkResult,
    CampaignRepository,
)
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class AddCampaignCollectionCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    collection_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class RemoveCampaignCollectionCommand(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    collection_id: uuid.UUID


async def _require_open_campaign(
    repo: CampaignRepository, workspace_id: uuid.UUID, campaign_id: uuid.UUID
) -> DomainError | None:
    """404 for an unknown/foreign campaign, 409 once it is closed."""
    status = await repo.find_status(workspace_id, campaign_id)
    if status is None:
        return NotFoundError("Campaign", str(campaign_id))
    if status is not CampaignStatus.DRAFT:
        return ConflictError(
            f"Cannot modify a {status.value} campaign — reopen it first",
        )
    return None


class AddCampaignCollection:
    """Link a library to a campaign (idempotent). Blocked once the campaign closes."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: CampaignRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AddCampaignCollectionCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            blocked = await _require_open_campaign(
                self._repo, input.workspace_id, input.campaign_id
            )
            if blocked is not None:
                return Failure(blocked)
            link = await self._repo.add_collection(
                input.workspace_id, input.campaign_id, input.collection_id
            )
            if link is CampaignCollectionLinkResult.COLLECTION_NOT_FOUND:
                return Failure(NotFoundError("Collection", str(input.collection_id)))
            if link is CampaignCollectionLinkResult.OWNER_NOT_FOUND:
                return Failure(NotFoundError("Campaign", str(input.campaign_id)))
            events = await self._uow.commit()

        if link is CampaignCollectionLinkResult.ADDED:
            events.append(
                CampaignCollectionAdded(
                    aggregate_id=input.campaign_id,
                    aggregate_type="Campaign",
                    workspace_id=input.workspace_id,
                    collection_id=input.collection_id,
                    user_id=auth.user_id if auth else None,
                )
            )
        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemoveCampaignCollection:
    """Unlink a library from a campaign. Blocked once the campaign closes."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: CampaignRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RemoveCampaignCollectionCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            blocked = await _require_open_campaign(
                self._repo, input.workspace_id, input.campaign_id
            )
            if blocked is not None:
                return Failure(blocked)
            removed = await self._repo.remove_collection(
                input.workspace_id, input.campaign_id, input.collection_id
            )
            events = await self._uow.commit()

        if removed:
            events.append(
                CampaignCollectionRemoved(
                    aggregate_id=input.campaign_id,
                    aggregate_type="Campaign",
                    workspace_id=input.workspace_id,
                    collection_id=input.collection_id,
                    user_id=auth.user_id if auth else None,
                )
            )
        await self._dispatcher.dispatch_all(events)
        return Success(None)
