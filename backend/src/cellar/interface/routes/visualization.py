"""Visualization workbench: flat datasets for linked plots, filters and tables."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cellar.application.visualization.dataset import Dataset, DatasetColumn
from cellar.application.visualization.get_dataset import (
    ComparedProtocol,
    DatasetLevel,
    GetVisualizationDatasetQuery,
    ProtocolSource,
    RunSource,
)
from cellar.application.visualization.get_run_row_counts import GetRunRowCountsQuery
from cellar.application.visualization.match_substructure import (
    MatchSubstructureQuery,
    SubstructureMatchResult,
)
from cellar.interface.dependencies import (
    AuthDep,
    GetRunRowCountsDep,
    GetVisualizationDatasetDep,
    MatchSubstructureDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/visualization", tags=["visualization"])


class ComparedProtocolBody(BaseModel):
    protocol_id: uuid.UUID
    run_ids: list[uuid.UUID] | None = None


class ProtocolSourceBody(BaseModel):
    kind: Literal["protocol"]
    protocol_id: uuid.UUID
    run_ids: list[uuid.UUID] | None = None
    # Compounds level only: further protocols joined onto this one's compounds.
    compare: list[ComparedProtocolBody] = Field(default_factory=list, max_length=4)


class RunSourceBody(BaseModel):
    kind: Literal["run"]
    run_id: uuid.UUID


class DatasetRequest(BaseModel):
    source: Annotated[ProtocolSourceBody | RunSourceBody, Field(discriminator="kind")]
    level: DatasetLevel


class ColumnProvenanceResponse(BaseModel):
    protocol_id: uuid.UUID | None = None
    readout_definition_id: uuid.UUID | None = None
    layer: str | None = None
    condition_set: str | None = None
    aggregation: str | None = None
    stat: str | None = None
    # Aggregated value and p columns: the source runs of the column's condition set.
    run_ids: list[uuid.UUID] | None = None
    # A dose-response readout's columns: the layer its curves fit ("percent_inhibition",
    # ...); null for raw values and for other columns.
    fitted_layer: str | None = None


class DatasetColumnResponse(BaseModel):
    key: str
    label: str
    kind: Literal["number", "category", "text", "structure", "user"]
    unit: str | None = None
    group: str | None = None
    provenance: ColumnProvenanceResponse
    hidden: bool = False

    @classmethod
    def from_domain(cls, c: DatasetColumn) -> DatasetColumnResponse:
        return cls(
            key=c.key,
            label=c.label,
            kind=c.kind,
            unit=c.unit,
            group=c.group,
            provenance=ColumnProvenanceResponse(
                protocol_id=c.provenance.protocol_id,
                readout_definition_id=c.provenance.readout_definition_id,
                layer=c.provenance.layer,
                condition_set=c.provenance.condition_set,
                aggregation=c.provenance.aggregation,
                stat=c.provenance.stat,
                run_ids=list(c.provenance.run_ids) if c.provenance.run_ids is not None else None,
                fitted_layer=c.provenance.fitted_layer,
            ),
            hidden=c.hidden,
        )


class DatasetProtocolResponse(BaseModel):
    protocol_id: uuid.UUID
    name: str
    # "high" / "low": which control is the full effect (controls are coloured by effect).
    pos_control_signal: str = "high"


class DatasetResponse(BaseModel):
    revision: str
    level: DatasetLevel
    row_count: int
    row_ids: list[str]
    columns: list[DatasetColumnResponse]
    values: dict[str, list[Any]]
    # Wells only: each plate's Z′ as the run's QC stored it, keyed by the plate id
    # that values["plate_id"] carries.
    plate_z_prime: dict[str, float] = {}
    # Wells only: each plate's stored Z′ per value column (rd:<readout>:<layer>).
    plate_z_prime_by_column: dict[str, dict[str, float]] = {}
    # The protocols the columns come from; the first one owns the rows.
    protocols: list[DatasetProtocolResponse] = []

    @classmethod
    def from_domain(cls, d: Dataset) -> DatasetResponse:
        return cls(
            revision=d.revision,
            level=cast(DatasetLevel, d.level),
            row_count=len(d.row_ids),
            row_ids=d.row_ids,
            columns=[DatasetColumnResponse.from_domain(c) for c in d.columns],
            values=d.values,
            plate_z_prime=d.plate_z_prime,
            plate_z_prime_by_column=d.plate_z_prime_by_column,
            protocols=[
                DatasetProtocolResponse(
                    protocol_id=p.id, name=p.name, pos_control_signal=p.pos_control_signal
                )
                for p in d.protocols
            ],
        )


class RunRowCountsResponse(BaseModel):
    counts: dict[str, int]


def _run_ids(run_ids: list[uuid.UUID] | None) -> tuple[uuid.UUID, ...] | None:
    return tuple(run_ids) if run_ids is not None else None


@router.post("/dataset", response_model=DatasetResponse)
async def get_dataset(
    body: DatasetRequest, auth: AuthDep, uc: GetVisualizationDatasetDep
) -> DatasetResponse:
    """One flat dataset (row ids + one value array per column) for a protocol or a run."""
    src = body.source
    source: ProtocolSource | RunSource = (
        RunSource(run_id=src.run_id)
        if isinstance(src, RunSourceBody)
        else ProtocolSource(
            protocol_id=src.protocol_id,
            run_ids=_run_ids(src.run_ids),
            compare=tuple(
                ComparedProtocol(c.protocol_id, _run_ids(c.run_ids)) for c in src.compare
            ),
        )
    )
    query = GetVisualizationDatasetQuery(
        workspace_id=auth.workspace_id, source=source, level=body.level
    )
    return DatasetResponse.from_domain(result_to_response(await uc(query, auth=auth)))


@router.get("/protocols/{protocol_id}/run-row-counts", response_model=RunRowCountsResponse)
async def get_run_row_counts(
    protocol_id: uuid.UUID, auth: AuthDep, uc: GetRunRowCountsDep
) -> RunRowCountsResponse:
    """Rows each run of the protocol adds to a Wells dataset (for the run picker)."""
    query = GetRunRowCountsQuery(workspace_id=auth.workspace_id, protocol_id=protocol_id)
    counts = result_to_response(await uc(query, auth=auth))
    return RunRowCountsResponse(counts={str(k): v for k, v in counts.items()})


class SubstructureMatchRequest(BaseModel):
    query: str
    # How the editor exported the query; untagged queries are aromatized when they
    # parse as SMILES (a Kekulé SMARTS from the editor), else read as SMARTS.
    query_kind: Literal["smiles", "smarts"] | None = None
    molecule_ids: list[uuid.UUID]


class SubstructureMatchResponse(BaseModel):
    matched_ids: list[uuid.UUID]
    searched: int
    without_structure: int

    @classmethod
    def from_domain(cls, r: SubstructureMatchResult) -> SubstructureMatchResponse:
        return cls(
            matched_ids=r.matched_ids, searched=r.searched, without_structure=r.without_structure
        )


@router.post("/substructure-match", response_model=SubstructureMatchResponse)
async def match_substructure(
    body: SubstructureMatchRequest, auth: AuthDep, uc: MatchSubstructureDep
) -> SubstructureMatchResponse:
    """Which of the given molecules contain the substructure (Search's strict match)."""
    query = MatchSubstructureQuery(
        workspace_id=auth.workspace_id,
        molecule_ids=tuple(body.molecule_ids),
        query=body.query,
        query_kind=body.query_kind,
    )
    return SubstructureMatchResponse.from_domain(result_to_response(await uc(query, auth=auth)))
