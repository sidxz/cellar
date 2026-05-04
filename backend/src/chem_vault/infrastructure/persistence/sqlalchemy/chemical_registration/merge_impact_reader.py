"""SQLAlchemy implementation of MergeImpactReader."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chem_vault.application.chemical_registration.merge_impact_reader import (
    MergeImpactCounts,
    MoleculeSummaryRow,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
    MoleculeRelationshipModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.synthesis_route_models import (
    SynthesisRouteModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.sample_request_models import (
    SampleRequestModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.inventory.synthesis_request_models import (
    SynthesisRequestModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CollectionMoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_model import (
    CompoundFlagModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    ReadoutDataModel,
)


class SQLAlchemyMergeImpactReader:
    """Infrastructure-layer read model for merge impact queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_molecule_summary(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID
    ) -> MoleculeSummaryRow | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(MoleculeModel).where(
                        MoleculeModel.id == molecule_id,
                        MoleculeModel.workspace_id == workspace_id,
                    )
                )
            ).scalar_one_or_none()

            if row is None:
                return None

            return MoleculeSummaryRow(
                id=row.id,
                registration_number=row.registration_number,
                name=row.name,
                structure_status=row.structure_status,
            )

    async def get_impact_counts(
        self, workspace_id: uuid.UUID, source_molecule_id: uuid.UUID
    ) -> MergeImpactCounts:
        src = source_molecule_id

        async with self._session_factory() as session:
            ws = workspace_id

            # Batches
            batch_count = (
                await session.execute(
                    select(func.count())
                    .select_from(BatchModel)
                    .where(BatchModel.molecule_id == src, BatchModel.workspace_id == ws)
                )
            ).scalar_one()

            # Readout data
            readout_count = (
                await session.execute(
                    select(func.count())
                    .select_from(ReadoutDataModel)
                    .where(ReadoutDataModel.molecule_id == src, ReadoutDataModel.workspace_id == ws)
                )
            ).scalar_one()

            # Dose-response curves
            curve_count = (
                await session.execute(
                    select(func.count())
                    .select_from(DoseResponseCurveModel)
                    .where(DoseResponseCurveModel.molecule_id == src, DoseResponseCurveModel.workspace_id == ws)
                )
            ).scalar_one()

            # Collections
            collection_count = (
                await session.execute(
                    select(func.count())
                    .select_from(CollectionMoleculeModel)
                    .where(CollectionMoleculeModel.molecule_id == src)
                )
            ).scalar_one()

            # Compound flags
            flag_count = (
                await session.execute(
                    select(func.count())
                    .select_from(CompoundFlagModel)
                    .where(CompoundFlagModel.molecule_id == src, CompoundFlagModel.workspace_id == ws)
                )
            ).scalar_one()

            # Sample requests
            active_sample_statuses = {"submitted", "approved", "preparing"}
            terminal_sample_statuses = {"fulfilled", "rejected", "cancelled"}

            active_sample_request_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SampleRequestModel)
                    .where(
                        SampleRequestModel.molecule_id == src,
                        SampleRequestModel.workspace_id == ws,
                        SampleRequestModel.status.in_(active_sample_statuses),
                    )
                )
            ).scalar_one()

            terminal_sample_request_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SampleRequestModel)
                    .where(
                        SampleRequestModel.molecule_id == src,
                        SampleRequestModel.workspace_id == ws,
                        SampleRequestModel.status.in_(terminal_sample_statuses),
                    )
                )
            ).scalar_one()

            # Synthesis requests
            active_synth_statuses = {
                "draft",
                "submitted",
                "approved",
                "assigned",
                "in_progress",
                "synthesis_complete",
            }

            synthesis_request_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SynthesisRequestModel)
                    .where(SynthesisRequestModel.molecule_id == src, SynthesisRequestModel.workspace_id == ws)
                )
            ).scalar_one()

            active_synthesis_request_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SynthesisRequestModel)
                    .where(
                        SynthesisRequestModel.molecule_id == src,
                        SynthesisRequestModel.workspace_id == ws,
                        SynthesisRequestModel.status.in_(active_synth_statuses),
                    )
                )
            ).scalar_one()

            # Synthesis routes
            route_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SynthesisRouteModel)
                    .where(SynthesisRouteModel.target_molecule_id == src, SynthesisRouteModel.workspace_id == ws)
                )
            ).scalar_one()

            # Relationships
            relationship_count = (
                await session.execute(
                    select(func.count())
                    .select_from(MoleculeRelationshipModel)
                    .where(
                        MoleculeRelationshipModel.workspace_id == ws,
                        (MoleculeRelationshipModel.source_molecule_id == src)
                        | (MoleculeRelationshipModel.target_molecule_id == src),
                    )
                )
            ).scalar_one()

        return MergeImpactCounts(
            batch_count=batch_count,
            readout_count=readout_count,
            curve_count=curve_count,
            collection_count=collection_count,
            flag_count=flag_count,
            active_sample_request_count=active_sample_request_count,
            terminal_sample_request_count=terminal_sample_request_count,
            synthesis_request_count=synthesis_request_count,
            active_synthesis_request_count=active_synthesis_request_count,
            route_count=route_count,
            relationship_count=relationship_count,
        )
