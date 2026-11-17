"""Compound and Batch text of a labelling table resolved to a compound and its batch.

A layout file's Compound cell names a compound by its registration number, then by any
registered identifier. A compound named without a batch takes its only batch, or is
marked as needing a choice when it has several; that rule is also applied to the
compound a position label names (``ResolvePositionLabels``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cellar.application.inventory.resolve_batch_ref import resolve_batch_ref
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.inventory.batch import Batch
from cellar.domain.inventory.repository import BatchRepository


@dataclass(frozen=True)
class LayoutCompound:
    molecule_id: uuid.UUID
    molecule_name: str
    registration_number: str
    batch_id: uuid.UUID | None
    batch_number: str | None
    needs_batch_choice: bool


class LayoutCompoundResolver:
    """Compound and Batch text -> LayoutCompound, one lookup per distinct text and molecule."""

    def __init__(
        self, ws: uuid.UUID, molecule_repo: MoleculeRepository, batch_repo: BatchRepository
    ) -> None:
        self._ws = ws
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._molecules: dict[str, Molecule | None] = {}
        self._molecules_by_id: dict[uuid.UUID, Molecule | None] = {}
        self._batches: dict[str, Batch | None] = {}
        self._batches_of: dict[uuid.UUID, list[Batch]] = {}

    async def __call__(
        self, compound_text: str, batch_text: str, problems: list[str]
    ) -> LayoutCompound | None:
        molecule = await self._molecule(compound_text) if compound_text else None
        batch = await self._batch(batch_text) if batch_text else None
        missing = False
        if compound_text and molecule is None:
            problems.append(f"Compound '{compound_text}' was not found")
            missing = True
        if batch_text and batch is None:
            problems.append(f"Batch '{batch_text}' was not found")
            missing = True
        if missing:
            return None

        if batch is not None:
            if molecule is None:
                molecule = await self._molecule_by_id(batch.molecule_id)
                if molecule is None:
                    problems.append(f"Batch '{batch_text}' was not found")
                    return None
            elif batch.molecule_id != molecule.id:
                problems.append(
                    f"Batch '{batch_text}' does not belong to compound '{compound_text}'"
                )
                return None
            return _compound(molecule, batch, needs_batch_choice=False)

        return await self.for_molecule(molecule) if molecule is not None else None

    async def for_molecule(self, molecule: Molecule) -> LayoutCompound:
        """A compound named without a batch: its only batch, or a choice among several."""
        batches = await self._batches_of_molecule(molecule.id)
        if len(batches) == 1:
            return _compound(molecule, batches[0], needs_batch_choice=False)
        return _compound(molecule, None, needs_batch_choice=len(batches) > 1)

    async def _molecule(self, text: str) -> Molecule | None:
        if text not in self._molecules:
            found = await self._molecule_repo.find_by_registration_number(self._ws, text)
            if found is None:
                found = await self._molecule_repo.find_by_identifier(self._ws, text)
            self._molecules[text] = found
        return self._molecules[text]

    async def _molecule_by_id(self, molecule_id: uuid.UUID) -> Molecule | None:
        if molecule_id not in self._molecules_by_id:
            self._molecules_by_id[molecule_id] = await self._molecule_repo.find_by_id_in_workspace(
                self._ws, molecule_id
            )
        return self._molecules_by_id[molecule_id]

    async def _batch(self, text: str) -> Batch | None:
        if text not in self._batches:
            self._batches[text] = await resolve_batch_ref(self._batch_repo, self._ws, text)
        return self._batches[text]

    async def _batches_of_molecule(self, molecule_id: uuid.UUID) -> list[Batch]:
        if molecule_id not in self._batches_of:
            self._batches_of[molecule_id] = await self._batch_repo.find_by_molecule(
                self._ws, molecule_id
            )
        return self._batches_of[molecule_id]


def _compound(
    molecule: Molecule, batch: Batch | None, *, needs_batch_choice: bool
) -> LayoutCompound:
    return LayoutCompound(
        molecule_id=molecule.id,
        molecule_name=molecule.name,
        registration_number=molecule.registration_number.value,
        batch_id=batch.id if batch is not None else None,
        batch_number=batch.batch_number.value if batch is not None else None,
        needs_batch_choice=needs_batch_choice,
    )
