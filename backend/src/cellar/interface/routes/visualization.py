"""Visualization workbench: flat datasets for linked plots, filters and tables."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cellar.application.visualization.dataset import Dataset, DatasetColumn
from cellar.application.visualization.get_dataset import (
    DatasetLevel,
    GetVisualizationDatasetQuery,
    ProtocolSource,
    RunSource,
)
from cellar.application.visualization.get_run_row_counts import GetRunRowCountsQuery
from cellar.interface.dependencies import (
    AuthDep,
    GetRunRowCountsDep,
    GetVisualizationDatasetDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/visualization", tags=["visualization"])


class ProtocolSourceBody(BaseModel):
    kind: Literal["protocol"]
    protocol_id: uuid.UUID
    run_ids: list[uuid.UUID] | None = None


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
            ),
            hidden=c.hidden,
        )


class DatasetResponse(BaseModel):
    revision: str
    level: DatasetLevel
    row_count: int
    row_ids: list[str]
    columns: list[DatasetColumnResponse]
    values: dict[str, list[Any]]

    @classmethod
    def from_domain(cls, d: Dataset) -> DatasetResponse:
        return cls(
            revision=d.revision,
            level=cast(DatasetLevel, d.level),
            row_count=len(d.row_ids),
            row_ids=d.row_ids,
            columns=[DatasetColumnResponse.from_domain(c) for c in d.columns],
            values=d.values,
        )


class RunRowCountsResponse(BaseModel):
    counts: dict[str, int]


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
            run_ids=tuple(src.run_ids) if src.run_ids is not None else None,
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
