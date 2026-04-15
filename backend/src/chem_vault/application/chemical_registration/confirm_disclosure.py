"""ConfirmDisclosure — confirm a disclosure that is awaiting merge confirmation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.chemical_registration.disclosure_service import DisclosureOutcome
from chem_vault.application.chemical_registration.merge_service import MergeCommand, MergeService
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.enums import DisclosureStatus, MergeReason
from chem_vault.domain.chemical_registration.repository import (
    DisclosureRequestRepository,
)
from chem_vault.domain.shared.errors import DomainError, NotFoundError, ValidationError


@dataclass(frozen=True, kw_only=True)
class ConfirmDisclosureCommand(Command):
    workspace_id: uuid.UUID
    disclosure_id: uuid.UUID
    confirmed_by: uuid.UUID


class ConfirmDisclosure:
    """Confirm a disclosure in PENDING_CONFIRMATION status, executing the merge.

    Uses merge_in_transaction() so the merge + DR update happen atomically.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        disclosure_repo: DisclosureRequestRepository,
        merge_service: MergeService,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._disclosure_repo = disclosure_repo
        self._merge_service = merge_service
        self._dispatcher = dispatcher

    async def __call__(
        self,
        input: ConfirmDisclosureCommand,
        auth: AuthContext | None = None,
    ) -> Result[DisclosureOutcome, DomainError]:
        require_editor(auth)

        async with self._uow:
            dr = await self._disclosure_repo.find_by_id_in_workspace(
                input.workspace_id, input.disclosure_id
            )
            if dr is None:
                return Failure(
                    NotFoundError("DisclosureRequest", str(input.disclosure_id))
                )

            if dr.status != DisclosureStatus.PENDING_CONFIRMATION:
                return Failure(
                    ValidationError(
                        f"Disclosure is in '{dr.status.value}' status, "
                        f"not 'pending_confirmation'"
                    )
                )

            if dr.matched_molecule_id is None:
                return Failure(
                    ValidationError(
                        "Disclosure has no matched molecule — cannot confirm"
                    )
                )

            target_molecule_id = dr.matched_molecule_id
            canonical_smiles = dr.canonical_smiles or dr.disclosed_smiles
            inchi_key = dr.inchi_key

            # Execute merge in the same transaction.
            # DR is already persisted, so merge_events FK is satisfiable.
            merge_result = await self._merge_service.merge_in_transaction(
                MergeCommand(
                    workspace_id=input.workspace_id,
                    source_molecule_id=dr.molecule_id,
                    target_molecule_id=target_molecule_id,
                    reason=MergeReason.DISCLOSURE_RESOLVED,
                    merged_by=input.confirmed_by,
                    disclosure_request_id=dr.id,
                    notes=dr.notes,
                ),
            )

            if isinstance(merge_result, Success):
                dr.resolve_as_merged(
                    canonical_smiles=canonical_smiles,
                    inchi_key=inchi_key,
                    resolved_to_molecule_id=target_molecule_id,
                )
            else:
                dr.mark_conflict(
                    reason=f"Merge failed: {merge_result.failure().message}"
                )

            await self._disclosure_repo.save(dr)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

            if isinstance(merge_result, Failure):
                return Failure(merge_result.failure())

            return Success(
                DisclosureOutcome(
                    disclosure_request=dr,
                    was_merged=True,
                    merged_into_molecule_id=target_molecule_id,
                )
            )
