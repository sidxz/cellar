"""BulkAddToCollection — preview + commit a CSV upload of molecule references.

Pure find-and-add: never registers. Stashes unmatched rows under a
preview_id (in-memory, 30-min TTL) so the FE can hand them off to the
bulk-register wizard.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
)
from cellar.application.shared.command import Command
from cellar.application.shared.molecule_resolver import (
    MoleculeReference,
    MoleculeResolver,
    RefType,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.research_organization.bulk_add_types import (
    BulkAddResult,
    BulkAddRow,
    RowOutcome,
    RowStatus,
)
from cellar.domain.research_organization.repository import (
    CollectionImportTemplateRepository,
    CollectionRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError

_STASH_TTL_SECONDS = 1800
# TODO: revisit when collections grow past 100K members
_MEMBERSHIP_READ_CAP = 100_000


@dataclass(frozen=True, kw_only=True)
class BulkAddToCollectionCommand(Command):
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    rows: list[BulkAddRow]
    dry_run: bool
    # Optional template the chemist selected for this import. When provided
    # AND commit produces at least one resolved row, the template records the
    # collection in its `used_in_collections` list (idempotent).
    template_id: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class StashedUnregisteredRows:
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    rows: list[BulkAddRow]
    expires_at: float


class BulkAddToCollection:
    """Use case: preview + commit a bulk add to a collection.

    Pure find-and-add. Never registers. Unmatched rows are stashed under a
    `preview_id` (in-memory dict on the instance) so the FE can hand them
    off to the bulk-register wizard.

    Stash entries TTL at 30 minutes; lazy GC on each preview/fetch call.

    NOTE: must be wired as a SINGLETON in DI because the stash dict lives
    on the instance.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        resolver: MoleculeResolver,
        repo: CollectionRepository,
        molecule_repo: MoleculeRepository,
        template_repo: CollectionImportTemplateRepository,
    ) -> None:
        self._uow = uow
        self._resolver = resolver
        self._repo = repo
        self._molecule_repo = molecule_repo
        self._template_repo = template_repo
        self._stash: dict[uuid.UUID, StashedUnregisteredRows] = {}

    async def __call__(
        self,
        input: BulkAddToCollectionCommand,
        auth: AuthContext | None = None,
    ) -> Result[BulkAddResult, DomainError]:
        try:
            require_editor(auth)
            require_same_workspace(auth, input.workspace_id)
        except DomainError as exc:
            return Failure(exc)

        async with self._uow:
            collection = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.collection_id
            )
            if collection is None:
                return Failure(NotFoundError("Collection", str(input.collection_id)))

            member_ids = set(
                await self._repo.get_molecule_ids(
                    input.workspace_id,
                    input.collection_id,
                    offset=0,
                    limit=_MEMBERSHIP_READ_CAP,
                )
            )

            row_refs: list[tuple[BulkAddRow, MoleculeReference]] = []
            outcomes: list[RowOutcome] = []
            for row in input.rows:
                ref = _row_to_ref(row)
                if ref is None:
                    outcomes.append(
                        RowOutcome(
                            row_index=row.row_index,
                            status=RowStatus.ERROR,
                            message="no usable identifier",
                        )
                    )
                    continue
                row_refs.append((row, ref))

            flat_refs = [ref for _, ref in row_refs]
            resolved_list, unresolved_list = await self._resolver.resolve(
                input.workspace_id, flat_refs
            )
            resolved_by_key = {(r.ref.value, r.ref.ref_type): r for r in resolved_list}
            unresolved_by_key = {
                (u.ref.value, u.ref.ref_type): u for u in unresolved_list
            }

            for row, ref in row_refs:
                key = (ref.value, ref.ref_type)
                if key in resolved_by_key:
                    rmol = resolved_by_key[key]
                    status = (
                        RowStatus.ALREADY_PRESENT
                        if rmol.molecule_id in member_ids
                        else RowStatus.RESOLVED
                    )
                    outcomes.append(
                        RowOutcome(
                            row_index=row.row_index,
                            status=status,
                            molecule_id=rmol.molecule_id,
                        )
                    )
                else:
                    u = unresolved_by_key.get(key)
                    reason = u.reason if u else "not_found"
                    status = (
                        RowStatus.AMBIGUOUS
                        if reason == "ambiguous"
                        else RowStatus.UNREGISTERED
                    )
                    outcomes.append(
                        RowOutcome(
                            row_index=row.row_index,
                            status=status,
                            message=reason,
                        )
                    )

            # Bulk-look up names for every molecule_id present in resolved /
            # already_present outcomes. The resolver doesn't carry display
            # fields, so we fetch them here in one round-trip. Display priority
            # is registration_number (chemist's primary identifier), then name.
            resolved_ids = list(
                {
                    o.molecule_id
                    for o in outcomes
                    if o.molecule_id is not None
                    and o.status in (RowStatus.RESOLVED, RowStatus.ALREADY_PRESENT)
                }
            )
            name_by_id: dict[uuid.UUID, str] = {}
            if resolved_ids:
                molecules = await self._molecule_repo.find_by_ids(
                    input.workspace_id, resolved_ids
                )
                for m in molecules:
                    reg = getattr(m, "registration_number", None)
                    nm = getattr(m, "name", None)
                    display = str(reg) if reg else (nm or "")
                    if display:
                        name_by_id[m.id] = display

            # RowOutcome is frozen; rebuild with molecule_name stamped on the
            # resolved / already_present rows.
            outcomes = [
                RowOutcome(
                    row_index=o.row_index,
                    status=o.status,
                    molecule_id=o.molecule_id,
                    molecule_name=(
                        name_by_id.get(o.molecule_id) if o.molecule_id else None
                    ),
                    candidates=o.candidates,
                    message=o.message,
                )
                for o in outcomes
            ]

            if not input.dry_run:
                resolved_ids = [
                    o.molecule_id
                    for o in outcomes
                    if o.status == RowStatus.RESOLVED and o.molecule_id is not None
                ]
                if resolved_ids:
                    await self._repo.add_molecules(
                        input.workspace_id, input.collection_id, resolved_ids
                    )
                    # Record template usage on productive commits only — if
                    # nothing actually resolved, the chemist didn't use the
                    # template in any meaningful way.
                    if input.template_id is not None:
                        tpl = await self._template_repo.find_by_id_in_workspace(
                            input.workspace_id, input.template_id
                        )
                        if tpl is not None:
                            tpl.record_usage_in(input.collection_id)
                            await self._template_repo.save(tpl)
                    await self._uow.commit()

            preview_id: uuid.UUID | None = None
            unregistered_row_indices = {
                o.row_index for o in outcomes if o.status == RowStatus.UNREGISTERED
            }
            unregistered_rows = [
                row for row in input.rows if row.row_index in unregistered_row_indices
            ]
            if unregistered_rows:
                preview_id = uuid.uuid4()
                self._stash[preview_id] = StashedUnregisteredRows(
                    workspace_id=input.workspace_id,
                    collection_id=input.collection_id,
                    rows=unregistered_rows,
                    expires_at=time.time() + _STASH_TTL_SECONDS,
                )
                self._gc_stash()

            return Success(
                BulkAddResult.from_outcomes(outcomes, preview_id=preview_id)
            )

    def fetch_stash(
        self, preview_id: uuid.UUID | None
    ) -> StashedUnregisteredRows | None:
        if preview_id is None:
            return None
        self._gc_stash()
        return self._stash.get(preview_id)

    def _gc_stash(self) -> None:
        now = time.time()
        expired = [pid for pid, s in self._stash.items() if s.expires_at < now]
        for pid in expired:
            del self._stash[pid]


def _row_to_ref(row: BulkAddRow) -> MoleculeReference | None:
    """Pick the highest-priority identifier present on the row.

    Priority: registration_number -> inchi_key -> smiles -> external_id -> name.
    """
    if row.registration_number:
        return MoleculeReference(
            value=row.registration_number, ref_type=RefType.REGISTRATION_NUMBER
        )
    if row.inchi_key:
        return MoleculeReference(value=row.inchi_key, ref_type=RefType.INCHI_KEY)
    if row.smiles:
        return MoleculeReference(value=row.smiles, ref_type=RefType.SMILES)
    if row.external_id:
        return MoleculeReference(value=row.external_id, ref_type=RefType.EXTERNAL_ID)
    if row.name:
        return MoleculeReference(value=row.name, ref_type=RefType.NAME)
    return None
