"""GetMergeImpact — query the data that would be affected by merging two molecules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext
from chem_vault.application.chemical_registration.merge_impact_reader import (
    MergeImpactReader,
)
from chem_vault.application.shared.query import Query
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

    Delegates raw SA queries to MergeImpactReader (infrastructure).
    """

    def __init__(self, reader: MergeImpactReader) -> None:
        self._reader = reader

    async def __call__(
        self,
        input: GetMergeImpactQuery,
        auth: AuthContext | None = None,
    ) -> Result[MergeImpact, DomainError]:
        from chem_vault.application.auth import require_same_workspace

        require_same_workspace(auth, input.workspace_id)

        ws = input.workspace_id
        src = input.source_molecule_id

        # --- Load molecule summaries (business logic: existence check) ---
        source_row = await self._reader.get_molecule_summary(ws, src)
        target_row = await self._reader.get_molecule_summary(
            ws, input.target_molecule_id
        )

        if source_row is None:
            return Failure(NotFoundError("Molecule", str(src)))
        if target_row is None:
            return Failure(
                NotFoundError("Molecule", str(input.target_molecule_id))
            )

        source_summary = MoleculeSummary(
            id=source_row.id,
            registration_number=source_row.registration_number,
            name=source_row.name,
            structure_status=source_row.structure_status,
        )
        target_summary = MoleculeSummary(
            id=target_row.id,
            registration_number=target_row.registration_number,
            name=target_row.name,
            structure_status=target_row.structure_status,
        )

        # --- Count affected data ---
        counts = await self._reader.get_impact_counts(ws, src)

        categories: list[MergeImpactCategory] = []
        blockers: list[str] = []

        # Batches
        if counts.batch_count:
            categories.append(
                MergeImpactCategory(
                    name="batches", label="Batches", count=counts.batch_count
                )
            )

        # Readout data
        if counts.readout_count:
            categories.append(
                MergeImpactCategory(
                    name="readout_data",
                    label="Assay Results",
                    count=counts.readout_count,
                )
            )

        # Dose-response curves
        if counts.curve_count:
            categories.append(
                MergeImpactCategory(
                    name="dose_response_curves",
                    label="Dose-Response Curves",
                    count=counts.curve_count,
                )
            )

        # Collections
        if counts.collection_count:
            categories.append(
                MergeImpactCategory(
                    name="collections",
                    label="Collections",
                    count=counts.collection_count,
                )
            )

        # Compound flags
        if counts.flag_count:
            categories.append(
                MergeImpactCategory(
                    name="compound_flags",
                    label="Compound Flags",
                    count=counts.flag_count,
                )
            )

        # Sample requests
        total_sr = (
            counts.active_sample_request_count
            + counts.terminal_sample_request_count
        )
        if total_sr:
            categories.append(
                MergeImpactCategory(
                    name="sample_requests",
                    label="Sample Requests",
                    count=total_sr,
                    items=[
                        {
                            "active_count": counts.active_sample_request_count,
                            "terminal_count": counts.terminal_sample_request_count,
                        }
                    ],
                    is_blocker=counts.active_sample_request_count > 0,
                )
            )
            if counts.active_sample_request_count > 0:
                blockers.append(
                    f"{counts.active_sample_request_count} active sample request(s) must be "
                    f"fulfilled or cancelled before merge"
                )

        # Synthesis requests
        if counts.synthesis_request_count:
            categories.append(
                MergeImpactCategory(
                    name="synthesis_requests",
                    label="Synthesis Requests",
                    count=counts.synthesis_request_count,
                    items=[
                        {
                            "active_count": counts.active_synthesis_request_count,
                            "terminal_count": counts.synthesis_request_count
                            - counts.active_synthesis_request_count,
                        }
                    ],
                )
            )

        # Synthesis routes
        if counts.route_count:
            categories.append(
                MergeImpactCategory(
                    name="synthesis_routes",
                    label="Synthesis Routes",
                    count=counts.route_count,
                )
            )

        # Relationships
        if counts.relationship_count:
            categories.append(
                MergeImpactCategory(
                    name="relationships",
                    label="Relationships",
                    count=counts.relationship_count,
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
