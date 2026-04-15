"""GetMergeImpact — query the data that would be affected by merging two molecules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success
from sqlalchemy import func, select

from chem_vault.application.auth import AuthContext
from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetMergeImpactQuery(Query):
    workspace_id: uuid.UUID
    target_molecule_id: uuid.UUID
    source_molecule_id: uuid.UUID


@dataclass(frozen=True)
class MoleculeSummary:
    id: uuid.UUID
    registration_number: str
    name: str
    structure_status: str


@dataclass(frozen=True)
class MergeImpactCategory:
    name: str
    label: str
    count: int
    items: list[dict] = field(default_factory=list)
    is_blocker: bool = False


@dataclass(frozen=True)
class MergeImpact:
    source: MoleculeSummary
    target: MoleculeSummary
    categories: list[MergeImpactCategory]
    blockers: list[str]


class GetMergeImpact:
    """Read-model query: count all data tied to the source molecule.

    Uses deferred SA model imports and raw queries for efficiency.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self,
        input: GetMergeImpactQuery,
        auth: AuthContext | None = None,
    ) -> Result[MergeImpact, DomainError]:
        # Deferred imports — infra models only used inside the read-model query.
        from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
            MoleculeModel,
            MoleculeRelationshipModel,
        )
        from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.synthesis_route_models import (
            SynthesisRouteModel,
        )
        from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_model import (
            CompoundFlagModel,
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
        from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models import (
            DoseResponseCurveModel,
            ReadoutDataModel,
        )

        ws = input.workspace_id
        src = input.source_molecule_id

        async with self._uow as uow:
            session = uow.session  # type: ignore[union-attr]

            # --- Load molecule summaries ---
            source_mol = (
                await session.execute(
                    select(MoleculeModel).where(
                        MoleculeModel.id == src,
                        MoleculeModel.workspace_id == ws,
                    )
                )
            ).scalar_one_or_none()

            target_mol = (
                await session.execute(
                    select(MoleculeModel).where(
                        MoleculeModel.id == input.target_molecule_id,
                        MoleculeModel.workspace_id == ws,
                    )
                )
            ).scalar_one_or_none()

            if source_mol is None:
                return Failure(NotFoundError("Molecule", str(src)))
            if target_mol is None:
                return Failure(
                    NotFoundError("Molecule", str(input.target_molecule_id))
                )

            source_summary = MoleculeSummary(
                id=source_mol.id,
                registration_number=source_mol.registration_number,
                name=source_mol.name,
                structure_status=source_mol.structure_status,
            )
            target_summary = MoleculeSummary(
                id=target_mol.id,
                registration_number=target_mol.registration_number,
                name=target_mol.name,
                structure_status=target_mol.structure_status,
            )

            # --- Count affected data ---
            categories: list[MergeImpactCategory] = []
            blockers: list[str] = []

            # Batches
            batch_count = (
                await session.execute(
                    select(func.count())
                    .select_from(BatchModel)
                    .where(BatchModel.molecule_id == src)
                )
            ).scalar_one()
            if batch_count:
                categories.append(
                    MergeImpactCategory(
                        name="batches", label="Batches", count=batch_count
                    )
                )

            # Readout data
            readout_count = (
                await session.execute(
                    select(func.count())
                    .select_from(ReadoutDataModel)
                    .where(ReadoutDataModel.molecule_id == src)
                )
            ).scalar_one()
            if readout_count:
                categories.append(
                    MergeImpactCategory(
                        name="readout_data",
                        label="Assay Results",
                        count=readout_count,
                    )
                )

            # Dose-response curves
            curve_count = (
                await session.execute(
                    select(func.count())
                    .select_from(DoseResponseCurveModel)
                    .where(DoseResponseCurveModel.molecule_id == src)
                )
            ).scalar_one()
            if curve_count:
                categories.append(
                    MergeImpactCategory(
                        name="dose_response_curves",
                        label="Dose-Response Curves",
                        count=curve_count,
                    )
                )

            # Collections
            collection_count = (
                await session.execute(
                    select(func.count())
                    .select_from(CollectionMoleculeModel)
                    .where(CollectionMoleculeModel.molecule_id == src)
                )
            ).scalar_one()
            if collection_count:
                categories.append(
                    MergeImpactCategory(
                        name="collections",
                        label="Collections",
                        count=collection_count,
                    )
                )

            # Compound flags
            flag_count = (
                await session.execute(
                    select(func.count())
                    .select_from(CompoundFlagModel)
                    .where(CompoundFlagModel.molecule_id == src)
                )
            ).scalar_one()
            if flag_count:
                categories.append(
                    MergeImpactCategory(
                        name="compound_flags",
                        label="Compound Flags",
                        count=flag_count,
                    )
                )

            # Sample requests
            active_sample_statuses = {"submitted", "approved", "preparing"}
            terminal_sample_statuses = {"fulfilled", "rejected", "cancelled"}

            active_sr_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SampleRequestModel)
                    .where(
                        SampleRequestModel.molecule_id == src,
                        SampleRequestModel.status.in_(active_sample_statuses),
                    )
                )
            ).scalar_one()
            terminal_sr_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SampleRequestModel)
                    .where(
                        SampleRequestModel.molecule_id == src,
                        SampleRequestModel.status.in_(terminal_sample_statuses),
                    )
                )
            ).scalar_one()
            total_sr = active_sr_count + terminal_sr_count
            if total_sr:
                categories.append(
                    MergeImpactCategory(
                        name="sample_requests",
                        label="Sample Requests",
                        count=total_sr,
                        items=[
                            {
                                "active_count": active_sr_count,
                                "terminal_count": terminal_sr_count,
                            }
                        ],
                        is_blocker=active_sr_count > 0,
                    )
                )
                if active_sr_count > 0:
                    blockers.append(
                        f"{active_sr_count} active sample request(s) must be "
                        f"fulfilled or cancelled before merge"
                    )

            # Synthesis requests
            active_synth_statuses = {
                "draft",
                "submitted",
                "approved",
                "assigned",
                "in_progress",
                "synthesis_complete",
            }
            synth_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SynthesisRequestModel)
                    .where(SynthesisRequestModel.molecule_id == src)
                )
            ).scalar_one()
            active_synth_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SynthesisRequestModel)
                    .where(
                        SynthesisRequestModel.molecule_id == src,
                        SynthesisRequestModel.status.in_(active_synth_statuses),
                    )
                )
            ).scalar_one()
            if synth_count:
                categories.append(
                    MergeImpactCategory(
                        name="synthesis_requests",
                        label="Synthesis Requests",
                        count=synth_count,
                        items=[
                            {
                                "active_count": active_synth_count,
                                "terminal_count": synth_count - active_synth_count,
                            }
                        ],
                    )
                )

            # Synthesis routes
            route_count = (
                await session.execute(
                    select(func.count())
                    .select_from(SynthesisRouteModel)
                    .where(SynthesisRouteModel.target_molecule_id == src)
                )
            ).scalar_one()
            if route_count:
                categories.append(
                    MergeImpactCategory(
                        name="synthesis_routes",
                        label="Synthesis Routes",
                        count=route_count,
                    )
                )

            # Relationships
            rel_count = (
                await session.execute(
                    select(func.count())
                    .select_from(MoleculeRelationshipModel)
                    .where(
                        (MoleculeRelationshipModel.source_molecule_id == src)
                        | (MoleculeRelationshipModel.target_molecule_id == src)
                    )
                )
            ).scalar_one()
            if rel_count:
                categories.append(
                    MergeImpactCategory(
                        name="relationships",
                        label="Relationships",
                        count=rel_count,
                    )
                )

            return Success(
                MergeImpact(
                    source=source_summary,
                    target=target_summary,
                    categories=categories,
                    blockers=blockers,
                )
            )
