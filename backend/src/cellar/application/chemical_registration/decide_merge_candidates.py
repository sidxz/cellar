"""DecideMergeCandidates — batch confirm/reject merge candidates (bulk registration).

Composes ``ConfirmDisclosure`` / ``RejectDisclosure`` per decision and
aggregates per-row outcomes, so a single failing row never fails the whole
batch. Extracted from the confirm-merges route, which previously held this
orchestration at the HTTP boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.chemical_registration.confirm_disclosure import (
    ConfirmDisclosure,
    ConfirmDisclosureCommand,
)
from cellar.application.chemical_registration.reject_disclosure import (
    RejectDisclosure,
    RejectDisclosureCommand,
)
from cellar.application.shared.command import Command
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class MergeDecision:
    disclosure_id: uuid.UUID
    action: str  # "confirm" | "reject"
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class DecideMergeCandidatesCommand(Command):
    workspace_id: uuid.UUID
    decided_by: uuid.UUID
    decisions: list[MergeDecision] = field(default_factory=list)


@dataclass(frozen=True)
class MergeDecisionOutcome:
    disclosure_id: uuid.UUID
    action: str
    success: bool
    error: str | None = None
    merged_into_molecule_id: uuid.UUID | None = None


@dataclass(frozen=True)
class DecideMergeCandidatesResult:
    outcomes: list[MergeDecisionOutcome]
    confirmed_count: int
    rejected_count: int
    error_count: int


def _error_message(error: DomainError) -> str:
    return getattr(error, "message", str(error))


class DecideMergeCandidates:
    """Apply a batch of merge-candidate decisions, one outcome per row."""

    def __init__(
        self,
        confirm_disclosure: ConfirmDisclosure,
        reject_disclosure: RejectDisclosure,
    ) -> None:
        self._confirm = confirm_disclosure
        self._reject = reject_disclosure

    async def __call__(
        self, input: DecideMergeCandidatesCommand, auth: AuthContext | None = None
    ) -> Result[DecideMergeCandidatesResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        outcomes: list[MergeDecisionOutcome] = []
        confirmed = rejected = errors = 0

        for decision in input.decisions:
            if decision.action == "confirm":
                result = await self._confirm(
                    ConfirmDisclosureCommand(
                        workspace_id=input.workspace_id,
                        disclosure_id=decision.disclosure_id,
                        confirmed_by=input.decided_by,
                    ),
                    auth=auth,
                )
                match result:
                    case Success(outcome):
                        outcomes.append(
                            MergeDecisionOutcome(
                                disclosure_id=decision.disclosure_id,
                                action=decision.action,
                                success=True,
                                merged_into_molecule_id=outcome.merged_into_molecule_id,
                            )
                        )
                        confirmed += 1
                    case Failure(error):
                        outcomes.append(
                            MergeDecisionOutcome(
                                disclosure_id=decision.disclosure_id,
                                action=decision.action,
                                success=False,
                                error=_error_message(error),
                            )
                        )
                        errors += 1

            elif decision.action == "reject":
                result = await self._reject(
                    RejectDisclosureCommand(
                        workspace_id=input.workspace_id,
                        disclosure_id=decision.disclosure_id,
                        reason=decision.reason,
                        rejected_by=input.decided_by,
                    ),
                    auth=auth,
                )
                match result:
                    case Success(_):
                        outcomes.append(
                            MergeDecisionOutcome(
                                disclosure_id=decision.disclosure_id,
                                action=decision.action,
                                success=True,
                            )
                        )
                        rejected += 1
                    case Failure(error):
                        outcomes.append(
                            MergeDecisionOutcome(
                                disclosure_id=decision.disclosure_id,
                                action=decision.action,
                                success=False,
                                error=_error_message(error),
                            )
                        )
                        errors += 1

            else:
                outcomes.append(
                    MergeDecisionOutcome(
                        disclosure_id=decision.disclosure_id,
                        action=decision.action,
                        success=False,
                        error=(
                            f"Unknown action '{decision.action}'. Must be 'confirm' or 'reject'."
                        ),
                    )
                )
                errors += 1

        return Success(
            DecideMergeCandidatesResult(
                outcomes=outcomes,
                confirmed_count=confirmed,
                rejected_count=rejected,
                error_count=errors,
            )
        )
