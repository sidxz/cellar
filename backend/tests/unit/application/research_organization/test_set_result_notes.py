"""Unit tests for SetResultNotes use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.set_result_notes import (
    SetResultNotes,
    SetResultNotesCommand,
)
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import (
    CampaignResult,
    ResultNote,
    StaleNoteError,
)
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.shared.errors import AuthorizationError, NotFoundError
from tests.unit.application.research_organization._helpers import (
    AuditSpy,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _campaign_with_row(
    workspace_id: uuid.UUID, notes: str | None = None
) -> tuple[Campaign, CampaignResult]:
    campaign = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        created_by=uuid.uuid4(),
    )
    result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
    result.notes = notes
    campaign.add_result(result)
    return campaign, result


def _uc(
    campaign_repo: AsyncMock,
    *,
    audit: AuditSpy | None = None,
    uow: FakeUnitOfWork | None = None,
) -> SetResultNotes:
    return SetResultNotes(
        uow=uow or FakeUnitOfWork(),
        campaign_repo=campaign_repo,
        audit=audit or AuditSpy(),  # type: ignore[arg-type]
        dispatcher=AsyncMock(),
    )


def _cmd(
    auth, campaign_id: uuid.UUID, result_id: uuid.UUID, notes: str | None, expected: str | None
) -> SetResultNotesCommand:
    return SetResultNotesCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        notes=notes,
        expected_notes=expected,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSetResultNotes:
    @pytest.mark.asyncio
    async def test_success_returns_the_stamped_note(self) -> None:
        auth = fake_auth()
        campaign, result = _campaign_with_row(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)

        out = await _uc(repo)(_cmd(auth, campaign.id, result.id, "Watch hERG", None), auth=auth)

        assert isinstance(out, Success)
        assert result.notes_edited_at is not None
        assert out.unwrap() == ResultNote("Watch hERG", auth.user_id, result.notes_edited_at)
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_whitespace_only_notes_clear_the_note(self) -> None:
        auth = fake_auth()
        campaign, result = _campaign_with_row(auth.workspace_id, "old")

        out = await _uc(make_campaign_repo(find_in_ws=campaign))(
            _cmd(auth, campaign.id, result.id, "   \n ", "old"), auth=auth
        )

        assert isinstance(out, Success)
        assert out.unwrap().notes is None
        assert out.unwrap().edited_by == auth.user_id

    @pytest.mark.parametrize("status", [CampaignStatus.CLOSED, CampaignStatus.SUPERSEDED])
    @pytest.mark.asyncio
    async def test_closed_and_superseded_campaigns_accept_notes(
        self, status: CampaignStatus
    ) -> None:
        auth = fake_auth()
        campaign, result = _campaign_with_row(auth.workspace_id)
        campaign.status = status  # type: ignore[misc]
        repo = make_campaign_repo(find_in_ws=campaign)

        out = await _uc(repo)(_cmd(auth, campaign.id, result.id, "Seen again", None), auth=auth)

        assert isinstance(out, Success)
        assert result.notes == "Seen again"
        assert result.notes_edited_by == auth.user_id
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_records_one_audit_operation_in_the_uow(self) -> None:
        auth = fake_auth()
        campaign, result = _campaign_with_row(auth.workspace_id, "old")
        audit, uow = AuditSpy(), FakeUnitOfWork()

        await _uc(make_campaign_repo(find_in_ws=campaign), audit=audit, uow=uow)(
            _cmd(auth, campaign.id, result.id, "new", "old"), auth=auth
        )

        assert audit.call_count == 1
        rec = audit.last_record
        assert rec is not None
        assert rec["workspace_id"] == auth.workspace_id
        assert rec["operation_type"] == OperationType.NOTE_EDIT
        assert rec["entity_type"] == "CampaignResult"
        assert rec["entity_id"] == result.id
        assert rec["user_id"] == auth.user_id
        assert rec["session"] is uow.session
        [entry] = rec["entries"]
        assert (entry.field_name, entry.old_value, entry.new_value, entry.action) == (
            "notes",
            "old",
            "new",
            AuditAction.UPDATE,
        )
        assert (entry.entity_type, entry.entity_id) == ("CampaignResult", result.id)

    @pytest.mark.parametrize(
        ("before", "after", "action"),
        [(None, "a", AuditAction.CREATE), ("a", None, AuditAction.DELETE)],
    )
    @pytest.mark.asyncio
    async def test_audit_action_create_and_delete(
        self, before: str | None, after: str | None, action: AuditAction
    ) -> None:
        auth = fake_auth()
        campaign, result = _campaign_with_row(auth.workspace_id, before)
        audit = AuditSpy()

        await _uc(make_campaign_repo(find_in_ws=campaign), audit=audit)(
            _cmd(auth, campaign.id, result.id, after, before), auth=auth
        )

        assert audit.last_record is not None
        assert audit.last_record["entries"][0].action == action

    @pytest.mark.asyncio
    async def test_same_text_saves_nothing(self) -> None:
        auth = fake_auth()
        campaign, result = _campaign_with_row(auth.workspace_id, "keep")
        repo, audit = make_campaign_repo(find_in_ws=campaign), AuditSpy()

        out = await _uc(repo, audit=audit)(
            _cmd(auth, campaign.id, result.id, " keep ", "keep"), auth=auth
        )

        assert out == Success(ResultNote("keep", None, None))
        repo.save.assert_not_awaited()
        assert audit.call_count == 0

    @pytest.mark.asyncio
    async def test_stale_expected_returns_stale_note_failure(self) -> None:
        auth = fake_auth()
        campaign, result = _campaign_with_row(auth.workspace_id, "theirs")
        repo, audit = make_campaign_repo(find_in_ws=campaign), AuditSpy()

        out = await _uc(repo, audit=audit)(
            _cmd(auth, campaign.id, result.id, "mine", "what I opened"), auth=auth
        )

        assert isinstance(out, Failure)
        err = out.failure()
        assert isinstance(err, StaleNoteError)
        assert err.current == ResultNote("theirs", None, None)
        repo.save.assert_not_awaited()
        assert audit.call_count == 0

    @pytest.mark.asyncio
    async def test_audit_failure_leaves_the_note_unsaved(self) -> None:
        auth = fake_auth()
        campaign, result = _campaign_with_row(auth.workspace_id, "old")
        audit, uow = AuditSpy(), FakeUnitOfWork()
        audit.fail_with = RuntimeError("audit down")
        uow.commit = AsyncMock(wraps=uow.commit)  # type: ignore[method-assign]
        repo = make_campaign_repo(find_in_ws=campaign)

        with pytest.raises(RuntimeError):
            await _uc(repo, audit=audit, uow=uow)(
                _cmd(auth, campaign.id, result.id, "new", "old"), auth=auth
            )

        assert audit.call_count == 1
        uow.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_result_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, _ = _campaign_with_row(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)

        out = await _uc(repo)(_cmd(auth, campaign.id, uuid.uuid4(), "anything", None), auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        repo = make_campaign_repo(find_in_ws=None)

        out = await _uc(repo)(_cmd(auth, uuid.uuid4(), uuid.uuid4(), "anything", None), auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        repo = make_campaign_repo(find_in_ws=None)

        with pytest.raises(AuthorizationError):
            await _uc(repo)(_cmd(auth, uuid.uuid4(), uuid.uuid4(), "nope", None), auth=auth)
        repo.save.assert_not_awaited()
