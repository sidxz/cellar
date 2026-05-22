"""Synchronize batch identifier mirrors with molecule synonyms.

Stateless collaborator. Two entry points:
  - fan_out_for_new_identifier: for one new MoleculeIdentifier, create
    a BatchIdentifier mirror on every existing batch of the molecule.
  - fan_out_for_new_batch: for one new Batch, create a BatchIdentifier
    mirror from every existing MoleculeIdentifier of its molecule.

Both skip-and-log on collision; the parent action always succeeds.

Mirrors are identified at the DB layer by a non-NULL FK
(BatchIdentifier.derived_from_molecule_identifier_id). Removal of the
parent MoleculeIdentifier cascade-deletes its mirrors — this helper
never deletes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

import structlog

from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.batch_identifier import BatchIdentifier

logger = structlog.get_logger(__name__)

SkipReason = Literal["already_mapped", "workspace_conflict", "malformed_batch_number"]


@dataclass(frozen=True)
class SkippedMirror:
    batch_number: str
    mirror_string: str
    reason: SkipReason


@dataclass(frozen=True)
class MirrorSummary:
    created: int = 0
    skipped: list[SkippedMirror] = field(default_factory=list)

    @classmethod
    def empty(cls) -> MirrorSummary:
        return cls()

    def __add__(self, other: MirrorSummary) -> MirrorSummary:
        return MirrorSummary(
            created=self.created + other.created,
            skipped=[*self.skipped, *other.skipped],
        )


class _BatchRepoProto(Protocol):
    async def save(self, batch: Batch) -> None: ...
    async def find_by_external_identifier(
        self, workspace_id: uuid.UUID, identifier: str
    ) -> Batch | None: ...


def _derive_suffix(batch_number: str) -> str | None:
    parts = batch_number.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return parts[1]


class SyncBatchIdentifierMirrors:
    """Stateless. Runs inside the caller's UoW."""

    def __init__(self, batch_repo: _BatchRepoProto) -> None:
        self._batch_repo = batch_repo

    async def fan_out_for_new_identifier(
        self,
        *,
        workspace_id: uuid.UUID,
        identifier: MoleculeIdentifier,
        batches: list[Batch],
        actor: uuid.UUID,
    ) -> MirrorSummary:
        summary = MirrorSummary.empty()
        for batch in batches:
            summary = summary + await self._mirror_one(
                workspace_id=workspace_id,
                identifier=identifier,
                batch=batch,
                actor=actor,
            )
        return summary

    async def fan_out_for_new_batch(
        self,
        *,
        workspace_id: uuid.UUID,
        batch: Batch,
        identifiers: list[MoleculeIdentifier],
        actor: uuid.UUID,
    ) -> MirrorSummary:
        """Pure mutator. Appends mirrors to batch.identifiers. Caller must save."""
        summary = MirrorSummary.empty()
        for identifier in identifiers:
            summary = summary + await self._mirror_one(
                workspace_id=workspace_id,
                identifier=identifier,
                batch=batch,
                actor=actor,
                save=False,
            )
        return summary

    async def _mirror_one(
        self,
        *,
        workspace_id: uuid.UUID,
        identifier: MoleculeIdentifier,
        batch: Batch,
        actor: uuid.UUID,
        save: bool = True,
    ) -> MirrorSummary:
        suffix = _derive_suffix(batch.batch_number.value)
        if suffix is None:
            return MirrorSummary(
                created=0,
                skipped=[
                    SkippedMirror(
                        batch_number=batch.batch_number.value,
                        mirror_string=f"{identifier.identifier}-?",
                        reason="malformed_batch_number",
                    )
                ],
            )
        mirror_string = f"{identifier.identifier}-{suffix}"

        # Skip if same string already on this batch (manual or prior auto-mirror).
        if any(bi.identifier == mirror_string for bi in batch.identifiers):
            return MirrorSummary(
                created=0,
                skipped=[
                    SkippedMirror(
                        batch_number=batch.batch_number.value,
                        mirror_string=mirror_string,
                        reason="already_mapped",
                    )
                ],
            )

        # Skip on workspace-unique conflict on another batch.
        owner = await self._batch_repo.find_by_external_identifier(workspace_id, mirror_string)
        if owner is not None and owner.id != batch.id:
            return MirrorSummary(
                created=0,
                skipped=[
                    SkippedMirror(
                        batch_number=batch.batch_number.value,
                        mirror_string=mirror_string,
                        reason="workspace_conflict",
                    )
                ],
            )

        batch.identifiers.append(
            BatchIdentifier.create(
                batch_id=batch.id,
                identifier=mirror_string,
                identifier_type="custom",
                source="compound-syn",
                registered_by=actor,
                derived_from_molecule_identifier_id=identifier.id,
            )
        )
        if save:
            await self._batch_repo.save(batch)
        return MirrorSummary(created=1, skipped=[])
