"""MorganFingerprintLoader — loads persisted Morgan FP bytes and converts to ExplicitBitVect.

The domain stores ``mol.morgan_fp`` as packed MSB-first bytes (256 bytes for 2048 bits),
written by ``MorganAlgorithm.compute_bytes``.  Conversion back uses RDKit's
``CreateFromBitString`` (the inverse of the generator's ``ToBitString() → packed bytes``).
The bit-vector size must match the generator: 2048 (radius=2 ECFP4).

Molecules with ``fp_morgan IS NULL`` are silently skipped; the caller
(``ComputeUmapCluster``) collects them in ``skipped_molecule_ids``.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from rdkit import DataStructs
from rdkit.DataStructs import ExplicitBitVect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)

_MORGAN_FP_NBITS = 2048


def _bytes_to_bitvect(fp_bytes: bytes) -> ExplicitBitVect:
    """Decode MSB-packed bytes (the storage shape) back into an ExplicitBitVect.

    Inverse of ``MorganAlgorithm.compute_bytes``, which packs ``fp.ToBitString()``
    into bytes by chunking 8 bits MSB-first. Round-tripping uses RDKit's own
    ``CreateFromBitString``.
    """
    bit_string = "".join(f"{b:08b}" for b in fp_bytes)
    return DataStructs.CreateFromBitString(bit_string)


class MorganFingerprintLoader:
    """Loads Morgan fingerprints from the persistence layer.

    Uses a lean projection (id + fp_morgan) to avoid loading full molecule
    aggregates.  No workspace filter is applied because the molecule IDs
    are already workspace-scoped by the time they reach this loader (they
    originate from a workspace-authenticated collection or search result).

    A fresh session is created per ``load_morgan`` call from the
    ``async_sessionmaker`` — same resource lifecycle as the other lean
    projection readers in this codebase.
    """

    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load_morgan(self, ids: Iterable[UUID]) -> dict[UUID, ExplicitBitVect]:
        """Return a mapping of molecule_id -> ExplicitBitVect for all ids that have a FP.

        Molecules with ``fp_morgan IS NULL`` are omitted from the result so the
        caller can collect them as ``skipped_molecule_ids``.
        """
        id_list = list(ids)
        if not id_list:
            return {}

        stmt = select(MoleculeModel.id, MoleculeModel.fp_morgan).where(
            MoleculeModel.id.in_(id_list),
            MoleculeModel.fp_morgan.isnot(None),
        )

        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()

        result: dict[UUID, ExplicitBitVect] = {}
        for mol_id, fp_bytes in rows:
            if len(fp_bytes) * 8 != _MORGAN_FP_NBITS:
                continue
            result[mol_id] = _bytes_to_bitvect(fp_bytes)
        return result
