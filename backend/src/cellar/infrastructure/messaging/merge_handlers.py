"""Merge side-effect handlers for cross-context FK reassignment.

Each handler re-points its context's molecule references from the source
(being tombstoned) to the target molecule within the same transaction.

All handlers accept UnitOfWork and extract the session internally, keeping
the application-layer MergeSideEffectHandler Protocol free of SA types.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from cellar.application.shared.unit_of_work import UnitOfWork


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
            sa.text("UPDATE batches SET molecule_id = :target WHERE molecule_id = :source"),
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
            sa.text("UPDATE readout_data SET molecule_id = :target WHERE molecule_id = :source"),
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
                "UPDATE dose_response_curves SET molecule_id = :target WHERE molecule_id = :source"
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
    """Re-point SynthesisRoute.target_molecule_id and
    ReactionStep.product_molecule_id from source to target."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        params = {"target": target_molecule_id, "source": source_molecule_id}
        await session.execute(
            sa.text(
                "UPDATE synthesis_routes SET target_molecule_id = :target "
                "WHERE target_molecule_id = :source"
            ),
            params,
        )
        await session.execute(
            sa.text(
                "UPDATE reaction_steps SET product_molecule_id = :target "
                "WHERE product_molecule_id = :source"
            ),
            params,
        )


class CompoundFlagMergeSideEffect:
    """Re-point compound_flags.molecule_id from source to target.

    Dedup: if both source and target have a flag for the same
    (workspace, protocol, flagged_by, flag_type), delete source's first.
    """

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        params = {"source": source_molecule_id, "target": target_molecule_id}

        # Delete duplicates that would violate unique constraint
        await session.execute(
            sa.text(
                "DELETE FROM compound_flags cf1 "
                "WHERE cf1.molecule_id = :source "
                "AND EXISTS ("
                "SELECT 1 FROM compound_flags cf2 "
                "WHERE cf2.molecule_id = :target "
                "AND cf2.workspace_id = cf1.workspace_id "
                "AND cf2.protocol_id = cf1.protocol_id "
                "AND cf2.flagged_by = cf1.flagged_by "
                "AND cf2.flag_type = cf1.flag_type"
                ")"
            ),
            params,
        )

        # Re-point remaining
        await session.execute(
            sa.text("UPDATE compound_flags SET molecule_id = :target WHERE molecule_id = :source"),
            params,
        )


class SynthesisRequestMergeSideEffect:
    """Re-point non-terminal synthesis_requests.molecule_id to target.

    Terminal statuses (fulfilled, rejected, cancelled, failed) are left
    pointing at source as historical records.
    """

    _TERMINAL = ("fulfilled", "rejected", "cancelled", "failed")

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        await session.execute(
            sa.text(
                "UPDATE synthesis_requests SET molecule_id = :target "
                "WHERE molecule_id = :source "
                "AND status NOT IN ('fulfilled', 'rejected', 'cancelled', 'failed')"
            ),
            {"target": target_molecule_id, "source": source_molecule_id},
        )


class SampleRequestMergeSideEffect:
    """Block merge if active sample requests exist, re-point completed ones.

    Active = submitted, approved, preparing (physical material in flight).
    Terminal = fulfilled, rejected, cancelled (safe to re-point for history).
    """

    _ACTIVE = ("submitted", "approved", "preparing")

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        params = {"source": source_molecule_id, "target": target_molecule_id}

        # Check for active requests — raise to abort merge
        result = await session.execute(
            sa.text(
                "SELECT COUNT(*) FROM sample_requests "
                "WHERE molecule_id = :source "
                "AND status IN ('submitted', 'approved', 'preparing')"
            ),
            {"source": source_molecule_id},
        )
        active_count = result.scalar_one()
        if active_count > 0:
            raise ValueError(
                f"Cannot merge: {active_count} active sample request(s) on source molecule"
            )

        # Re-point terminal requests for history
        await session.execute(
            sa.text(
                "UPDATE sample_requests SET molecule_id = :target WHERE molecule_id = :source"
            ),
            params,
        )


class MixtureComponentMergeSideEffect:
    """Re-point mixture_components FKs from source to target.

    Handles both mixture_molecule_id and component_molecule_id.
    Deletes rows that would create duplicate components in the same mixture.
    """

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = _session(uow)
        params = {"source": source_molecule_id, "target": target_molecule_id}

        # Delete component rows that would duplicate after re-point
        # (same mixture, same component, same role)
        await session.execute(
            sa.text(
                "DELETE FROM mixture_components mc1 "
                "WHERE mc1.component_molecule_id = :source "
                "AND EXISTS ("
                "SELECT 1 FROM mixture_components mc2 "
                "WHERE mc2.mixture_molecule_id = mc1.mixture_molecule_id "
                "AND mc2.component_molecule_id = :target"
                ")"
            ),
            params,
        )

        # Re-point component references
        await session.execute(
            sa.text(
                "UPDATE mixture_components "
                "SET component_molecule_id = :target "
                "WHERE component_molecule_id = :source"
            ),
            params,
        )

        # Re-point mixture references
        await session.execute(
            sa.text(
                "UPDATE mixture_components "
                "SET mixture_molecule_id = :target "
                "WHERE mixture_molecule_id = :source"
            ),
            params,
        )
