"""RegisteredPlate API routes — CRUD, well mapping, status transitions, derive."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

from cellar.application.inventory.export_plate_layout import (
    ExportPlateLayoutQuery,
    render_csv,
    render_xlsx,
)
from cellar.application.inventory.get_plate_insights import GetPlateInsightsQuery
from cellar.application.inventory.list_runs_for_plate import ListRunsForPlateQuery
from cellar.application.inventory.plate_insights_reader import PlateInsightsData
from cellar.application.inventory.plate_read_model import (
    MoleculePlateEntry,
)
from cellar.application.inventory.plate_runs_reader import PlateRunRow
from cellar.application.inventory.registered_plates import (
    ChangeStatusCommand,
    DeletePlateCommand,
    DerivePlateCommand,
    GetPlateQuery,
    ListChildrenQuery,
    ListPlatesQuery,
    MapWellsCommand,
    RegisterPlateCommand,
    UpdatePlateCommand,
)
from cellar.application.inventory.shipment_reads import ListShipmentsForItemQuery
from cellar.application.shared.sentinel import UNSET
from cellar.domain.inventory.enums import PlateStatus, PlateType, ShipmentItemType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.screening_assay.enums import PlateFormat
from cellar.interface.dependencies import (
    AuthDep,
    ChangeStatusDep,
    DeletePlateDep,
    DerivePlateDep,
    ExportPlateLayoutDep,
    GetPlateDep,
    GetPlateInsightsDep,
    ListChildrenDep,
    ListPlatesDep,
    ListRunsForPlateDep,
    ListShipmentsForItemDep,
    MapWellsDep,
    RegisterPlateDep,
    UpdatePlateDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes.shipments import ShipmentLinkResponse

router = APIRouter(prefix="/api/v1/plates", tags=["plates"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class WellEntryModel(BaseModel):
    """One well's assignment as exposed by the API — flat shape, mirrors storage."""

    batch_id: str | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None
    well_type: str = "sample"
    cdd_batch_id_unresolved: int | None = None


class PlateResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    barcode: str
    plate_label: str
    format: PlateFormat
    plate_type: PlateType
    well_map: dict[str, WellEntryModel] | None = None
    status: PlateStatus
    storage_location_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    parent_plate_id: uuid.UUID | None = None
    registered_by: uuid.UUID
    notes: str | None = None
    owner_org_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None

    @classmethod
    def from_domain(cls, p: RegisteredPlate) -> PlateResponse:
        return cls(
            id=p.id,
            workspace_id=p.workspace_id,
            barcode=p.barcode.value,
            plate_label=p.plate_label,
            format=p.format,
            plate_type=p.plate_type,
            well_map=(
                {pos: WellEntryModel(**wa.to_dict()) for pos, wa in p.well_map.items()}
                if p.well_map
                else None
            ),
            status=p.status,
            storage_location_id=p.storage_location_id,
            project_id=p.project_id,
            template_id=p.template_id,
            parent_plate_id=p.parent_plate_id,
            registered_by=p.registered_by,
            notes=p.notes,
            owner_org_id=p.owner_org_id,
            group_id=p.group_id,
        )


class RegisterPlateBody(BaseModel):
    barcode: str
    plate_label: str
    format: PlateFormat
    plate_type: PlateType
    well_map: dict | None = None
    storage_location_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    parent_plate_id: uuid.UUID | None = None
    notes: str | None = None
    owner_org_id: uuid.UUID | None = None


class UpdatePlateBody(BaseModel):
    plate_label: str | None = None
    plate_type: PlateType | None = None
    notes: str | None = None
    project_id: uuid.UUID | None = None
    storage_location_id: uuid.UUID | None = None

    model_config = {"extra": "forbid"}


class MapWellsBody(BaseModel):
    well_map: dict


class ChangeStatusBody(BaseModel):
    new_status: PlateStatus


class DerivePlateBody(BaseModel):
    barcode: str
    plate_label: str
    plate_type: PlateType = PlateType.DAUGHTER
    storage_location_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    notes: str | None = None


class MoleculePlateResponse(BaseModel):
    plate_id: uuid.UUID
    barcode: str
    plate_label: str
    well_position: str
    concentration_value: float | None = None
    concentration_unit: str | None = None
    plate_type: str
    status: str
    storage_location_name: str | None = None

    @classmethod
    def from_entry(cls, e: MoleculePlateEntry) -> MoleculePlateResponse:
        return cls(
            plate_id=e.plate_id,
            barcode=e.barcode,
            plate_label=e.plate_label,
            well_position=e.well_position,
            concentration_value=e.concentration_value,
            concentration_unit=e.concentration_unit,
            plate_type=e.plate_type,
            status=e.status,
            storage_location_name=e.storage_location_name,
        )


class PlateRunResponse(BaseModel):
    run_id: uuid.UUID
    # Runs have no name — run_date is their display identity (the run page is
    # titled "Run {run_date}"); created_at is the ordering key (newest first).
    run_date: date
    run_status: str
    protocol_id: uuid.UUID
    protocol_name: str
    plate_number: int
    created_at: datetime

    @classmethod
    def from_row(cls, r: PlateRunRow) -> PlateRunResponse:
        return cls(
            run_id=r.run_id,
            run_date=r.run_date,
            run_status=r.run_status,
            protocol_id=r.protocol_id,
            protocol_name=r.protocol_name,
            plate_number=r.plate_number,
            created_at=r.created_at,
        )


class CountBucketResponse(BaseModel):
    key: str
    count: int


class LocationCountResponse(BaseModel):
    location_id: uuid.UUID | None = None
    name: str
    count: int


class GroupSizeResponse(BaseModel):
    group_id: uuid.UUID
    name: str
    count: int


class WeeklyLoanActivityResponse(BaseModel):
    week_start: date
    requested: int
    returned: int


class PlateInsightsResponse(BaseModel):
    org_id: uuid.UUID
    total_plates: int
    open_loans: int
    overdue_count: int
    by_status: list[CountBucketResponse]
    by_type: list[CountBucketResponse]
    by_location: list[LocationCountResponse]
    group_sizes: list[GroupSizeResponse]
    loan_activity_weekly: list[WeeklyLoanActivityResponse]

    @classmethod
    def from_data(cls, org_id: uuid.UUID, data: PlateInsightsData) -> PlateInsightsResponse:
        return cls(
            org_id=org_id,
            total_plates=data.total_plates,
            open_loans=data.open_loans,
            overdue_count=data.overdue_count,
            by_status=[CountBucketResponse(key=b.key, count=b.count) for b in data.by_status],
            by_type=[CountBucketResponse(key=b.key, count=b.count) for b in data.by_type],
            by_location=[
                LocationCountResponse(location_id=loc.location_id, name=loc.name, count=loc.count)
                for loc in data.by_location
            ],
            group_sizes=[
                GroupSizeResponse(group_id=g.group_id, name=g.name, count=g.count)
                for g in data.group_sizes
            ],
            loan_activity_weekly=[
                WeeklyLoanActivityResponse(
                    week_start=w.week_start, requested=w.requested, returned=w.returned
                )
                for w in data.loan_activity_weekly
            ],
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=PlateResponse, status_code=201)
async def register_plate(
    body: RegisterPlateBody,
    auth: AuthDep,
    uc: RegisterPlateDep,
) -> PlateResponse:
    """Register a new physical plate in the inventory."""
    command = RegisterPlateCommand(
        workspace_id=auth.workspace_id,
        barcode=body.barcode,
        plate_label=body.plate_label,
        format=body.format.value,
        plate_type=body.plate_type.value,
        registered_by=auth.user_id,
        well_map=body.well_map,
        storage_location_id=body.storage_location_id,
        project_id=body.project_id,
        template_id=body.template_id,
        parent_plate_id=body.parent_plate_id,
        notes=body.notes,
        owner_org_id=body.owner_org_id,
    )
    plate = result_to_response(await uc(command, auth=auth))
    return PlateResponse.from_domain(plate)


@router.get("", response_model=list[PlateResponse])
async def list_plates(
    auth: AuthDep,
    uc: ListPlatesDep,
    barcode: str | None = None,
    plate_label: str | None = None,
    plate_type: str | None = None,
    status: str | None = None,
    format: str | None = None,
    storage_location_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    owner_org_id: uuid.UUID | None = None,
    group_id: uuid.UUID | None = None,
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
) -> list[PlateResponse]:
    """List registered plates with optional filters."""
    query = ListPlatesQuery(
        workspace_id=auth.workspace_id,
        barcode=barcode,
        plate_label=plate_label,
        plate_type=plate_type,
        status=status,
        format=format,
        storage_location_id=storage_location_id,
        project_id=project_id,
        owner_org_id=owner_org_id,
        group_id=group_id,
        tags=tags,
        tag_logic=tag_logic,
    )
    plates = result_to_response(await uc(query, auth=auth))
    return [PlateResponse.from_domain(p) for p in plates]


@router.get("/insights", response_model=PlateInsightsResponse)
async def get_plate_insights(
    auth: AuthDep, uc: GetPlateInsightsDep, org_id: uuid.UUID | None = None
) -> PlateInsightsResponse:
    """Org-scoped plate/loan insight counts for the dashboard (spec §9, §11)."""
    query = GetPlateInsightsQuery(workspace_id=auth.workspace_id, org_id=org_id)
    resolved_org, data = result_to_response(await uc(query, auth=auth))
    return PlateInsightsResponse.from_data(resolved_org, data)


@router.get("/{plate_id}", response_model=PlateResponse)
async def get_plate(
    plate_id: uuid.UUID,
    auth: AuthDep,
    uc: GetPlateDep,
) -> PlateResponse:
    """Retrieve a single registered plate by ID."""
    query = GetPlateQuery(workspace_id=auth.workspace_id, plate_id=plate_id)
    plate = result_to_response(await uc(query, auth=auth))
    return PlateResponse.from_domain(plate)


@router.patch("/{plate_id}", response_model=PlateResponse)
async def update_plate(
    plate_id: uuid.UUID,
    body: UpdatePlateBody,
    auth: AuthDep,
    uc: UpdatePlateDep,
) -> PlateResponse:
    """Update mutable fields on an existing plate."""
    provided = body.model_fields_set
    command = UpdatePlateCommand(
        workspace_id=auth.workspace_id,
        plate_id=plate_id,
        plate_label=body.plate_label if "plate_label" in provided else None,
        plate_type=body.plate_type.value
        if body.plate_type is not None and "plate_type" in provided
        else None,
        notes=body.notes if "notes" in provided else UNSET,
        project_id=body.project_id if "project_id" in provided else UNSET,
        storage_location_id=body.storage_location_id
        if "storage_location_id" in provided
        else UNSET,
    )
    plate = result_to_response(await uc(command, auth=auth))
    return PlateResponse.from_domain(plate)


@router.put("/{plate_id}/wells", response_model=PlateResponse)
async def map_wells(
    plate_id: uuid.UUID,
    body: MapWellsBody,
    auth: AuthDep,
    uc: MapWellsDep,
) -> PlateResponse:
    """Assign batch/concentration data to wells on a plate."""
    command = MapWellsCommand(
        workspace_id=auth.workspace_id,
        plate_id=plate_id,
        well_map=body.well_map,
    )
    plate = result_to_response(await uc(command, auth=auth))
    return PlateResponse.from_domain(plate)


@router.get("/{plate_id}/export")
async def export_plate_layout(
    plate_id: uuid.UUID,
    auth: AuthDep,
    uc: ExportPlateLayoutDep,
    fmt: str = Query("csv", alias="format", pattern="^(csv|xlsx)$"),
) -> Response:
    """Export a plate's well-map as a round-trippable CSV/XLSX download.

    Columns match the well-mapping import exactly, with batch UUIDs resolved
    back to batch numbers — so the file re-imports losslessly.
    """
    export = result_to_response(
        await uc(
            ExportPlateLayoutQuery(workspace_id=auth.workspace_id, plate_id=plate_id),
            auth=auth,
        )
    )
    if fmt == "xlsx":
        content = render_xlsx(export.rows)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        content = render_csv(export.rows)
        media_type = "text/csv"
        ext = "csv"
    filename = f"{export.barcode}_well_map.{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{plate_id}/status", response_model=PlateResponse)
async def change_status(
    plate_id: uuid.UUID,
    body: ChangeStatusBody,
    auth: AuthDep,
    uc: ChangeStatusDep,
) -> PlateResponse:
    """Transition a plate to a new lifecycle status."""
    command = ChangeStatusCommand(
        workspace_id=auth.workspace_id,
        plate_id=plate_id,
        new_status=body.new_status.value,
    )
    plate = result_to_response(await uc(command, auth=auth))
    return PlateResponse.from_domain(plate)


@router.post("/{plate_id}/derive", response_model=PlateResponse, status_code=201)
async def derive_plate(
    plate_id: uuid.UUID,
    body: DerivePlateBody,
    auth: AuthDep,
    uc: DerivePlateDep,
) -> PlateResponse:
    """Derive a child plate from a parent, copying the well map."""
    command = DerivePlateCommand(
        workspace_id=auth.workspace_id,
        parent_plate_id=plate_id,
        barcode=body.barcode,
        plate_label=body.plate_label,
        registered_by=auth.user_id,
        plate_type=body.plate_type.value,
        storage_location_id=body.storage_location_id,
        project_id=body.project_id,
        notes=body.notes,
    )
    plate = result_to_response(await uc(command, auth=auth))
    return PlateResponse.from_domain(plate)


@router.get("/{plate_id}/children", response_model=list[PlateResponse])
async def list_children(
    plate_id: uuid.UUID,
    auth: AuthDep,
    uc: ListChildrenDep,
) -> list[PlateResponse]:
    """List child plates derived from a given parent plate."""
    query = ListChildrenQuery(
        workspace_id=auth.workspace_id,
        parent_plate_id=plate_id,
    )
    children = result_to_response(await uc(query, auth=auth))
    return [PlateResponse.from_domain(p) for p in children]


@router.get("/{plate_id}/runs", response_model=list[PlateRunResponse])
async def list_plate_runs(
    plate_id: uuid.UUID,
    auth: AuthDep,
    uc: ListRunsForPlateDep,
) -> list[PlateRunResponse]:
    """Runs whose plates are linked to this physical plate, newest first.

    Plate visibility applies — a hidden plate 404s like a missing one.
    """
    query = ListRunsForPlateQuery(workspace_id=auth.workspace_id, plate_id=plate_id)
    rows = result_to_response(await uc(query, auth=auth))
    return [PlateRunResponse.from_row(r) for r in rows]


@router.get("/{plate_id}/shipments", response_model=list[ShipmentLinkResponse])
async def list_plate_shipments(
    plate_id: uuid.UUID,
    auth: AuthDep,
    uc: ListShipmentsForItemDep,
) -> list[ShipmentLinkResponse]:
    """Shipments that carried this plate, newest first (hidden plate 404s like missing)."""
    query = ListShipmentsForItemQuery(
        workspace_id=auth.workspace_id, item_type=ShipmentItemType.PLATE, item_id=plate_id
    )
    rows = result_to_response(await uc(query, auth=auth))
    return [ShipmentLinkResponse.from_row(r) for r in rows]


@router.delete("/{plate_id}", status_code=204)
async def delete_plate(
    plate_id: uuid.UUID,
    auth: AuthDep,
    uc: DeletePlateDep,
) -> None:
    """Delete a registered plate if it has no child plates."""
    command = DeletePlateCommand(
        workspace_id=auth.workspace_id,
        plate_id=plate_id,
    )
    result_to_response(await uc(command, auth=auth))
