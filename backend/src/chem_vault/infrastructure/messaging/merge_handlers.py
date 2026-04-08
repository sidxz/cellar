"""Merge side-effect handlers for cross-context FK reassignment.

Each handler re-points its context's molecule references from the source
(being tombstoned) to the target molecule within the same transaction.

All handlers accept UnitOfWork and extract the session internally, keeping
the application-layer MergeSideEffectHandler Protocol free of SA types.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from chem_vault.application.shared.unit_of_work import UnitOfWork


def _session(uow: UnitOfWork) -> sa.ext.asyncio.AsyncSession:
    """Extract the async session from a UnitOfWork (infrastructure bridge).

    Uses duck typing: works with both AsyncUnitOfWork and test fakes that
    expose a `session` attribute.
    """
    return uow.session  # type: ignore[attr-defined]


class BatchMergeSideEffect:
    """Re-point Batch.molecule_id from source to target."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        await session.execute(
            sa.text(
                "UPDATE batches SET molecule_id = :target "
                "WHERE molecule_id = :source"
            ),
            {"target": target_molecule_id, "source": source_molecule_id},
        )


class ReadoutDataMergeSideEffect:
    """Re-point ReadoutData.molecule_id from source to target."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        await session.execute(
            sa.text(
                "UPDATE readout_data SET molecule_id = :target "
                "WHERE molecule_id = :source"
            ),
            {"target": target_molecule_id, "source": source_molecule_id},
        )


class DoseResponseCurveMergeSideEffect:
    """Re-point DoseResponseCurve.molecule_id from source to target."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        await session.execute(
            sa.text(
                "UPDATE dose_response_curves SET molecule_id = :target "
                "WHERE molecule_id = :source"
            ),
            {"target": target_molecule_id, "source": source_molecule_id},
        )


class MoleculeRelationshipMergeSideEffect:
    """Re-point MoleculeRelationship FKs, handling self-referential and duplicates.

    After substituting source -> target on both FK columns:
    1. Delete rows where both ends would point to target (self-referential).
    2. Delete rows that would duplicate an existing relationship on target.
    3. UPDATE the remaining rows.
    """

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        params = {"source": source_molecule_id, "target": target_molecule_id}

        # 1. Delete relationships that would become self-referential:
        #    source is on one side, target is already on the other.
        await session.execute(
            sa.text(
                "DELETE FROM molecule_relationships "
                "WHERE (source_molecule_id = :source AND target_molecule_id = :target) "
                "OR (source_molecule_id = :target AND target_molecule_id = :source)"
            ),
            params,
        )

        # 2. Delete source-side references that would duplicate an existing
        #    relationship on the target (same pair + type after re-point).
        await session.execute(
            sa.text(
                "DELETE FROM molecule_relationships r1 "
                "USING molecule_relationships r2 "
                "WHERE r1.source_molecule_id = :source "
                "AND r2.source_molecule_id = :target "
                "AND r1.target_molecule_id = r2.target_molecule_id "
                "AND r1.relationship_type = r2.relationship_type "
                "AND r1.workspace_id = r2.workspace_id"
            ),
            params,
        )

        # 3. Same for target-side references.
        await session.execute(
            sa.text(
                "DELETE FROM molecule_relationships r1 "
                "USING molecule_relationships r2 "
                "WHERE r1.target_molecule_id = :source "
                "AND r2.target_molecule_id = :target "
                "AND r1.source_molecule_id = r2.source_molecule_id "
                "AND r1.relationship_type = r2.relationship_type "
                "AND r1.workspace_id = r2.workspace_id"
            ),
            params,
        )

        # 4. Re-point remaining references.
        await session.execute(
            sa.text(
                "UPDATE molecule_relationships "
                "SET source_molecule_id = :target "
                "WHERE source_molecule_id = :source"
            ),
            params,
        )
        await session.execute(
            sa.text(
                "UPDATE molecule_relationships "
                "SET target_molecule_id = :target "
                "WHERE target_molecule_id = :source"
            ),
            params,
        )


class SynthesisRouteMergeSideEffect:
    """Re-point SynthesisRoute.target_molecule_id from source to target."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        await session.execute(
            sa.text(
                "UPDATE synthesis_routes SET target_molecule_id = :target "
                "WHERE target_molecule_id = :source"
            ),
            {"target": target_molecule_id, "source": source_molecule_id},
        )
