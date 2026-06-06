"""Protocol API routes."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from cellar.application.screening._dose_response_config_serde import (
    serialize_dose_response_config,
)
from cellar.application.screening.create_protocol import CreateProtocolCommand
from cellar.application.screening.get_protocol import (
    GetProtocolQuery,
    ListProtocolsQuery,
)
from cellar.application.screening.list_protocol_summaries import (
    ListProtocolSummariesQuery,
)
from cellar.application.screening.lock_protocol import (
    LockProtocolCommand,
    UnlockProtocolCommand,
)
from cellar.application.screening.manage_condition_definitions import (
    AddConditionDefinitionCommand,
    RemoveConditionDefinitionCommand,
    UpdateConditionDefinitionCommand,
)
from cellar.application.screening.manage_control_layouts import (
    RemoveControlLayoutCommand,
    SetControlLayoutCommand,
)
from cellar.application.screening.manage_ontology_annotations import (
    RemoveOntologyAnnotationCommand,
    SetOntologyAnnotationCommand,
)
from cellar.application.screening.manage_protocol import (
    AddProtocolTargetCommand,
    AddProtocolToProjectCommand,
    DeleteProtocolCommand,
    ListProtocolsByProjectQuery,
    PublishProtocolCommand,
    RemoveProtocolFromProjectCommand,
    RemoveProtocolTargetCommand,
    RetireProtocolCommand,
    UpdateProtocolCommand,
    VersionProtocolCommand,
)
from cellar.application.screening.manage_readout_definitions import (
    AddReadoutDefinitionCommand,
    RemoveReadoutDefinitionCommand,
    UpdateReadoutDefinitionCommand,
)
from cellar.application.screening.resolve_target_links import (
    GetProtocolTargetsQuery,
    ResolveProtocolTargetsQuery,
)
from cellar.application.shared.sentinel import UNSET
from cellar.domain.screening_assay.protocol import Protocol
from cellar.interface.dependencies import (
    AddConditionDefinitionDep,
    AddProtocolTargetDep,
    AddProtocolToProjectDep,
    AddReadoutDefinitionDep,
    AuthDep,
    ConditionGroupingServiceDep,
    CreateProtocolDep,
    DeleteProtocolDep,
    GetProtocolDep,
    GetProtocolTargetsDep,
    ListProtocolsByProjectDep,
    ListProtocolsDep,
    ListProtocolSummariesDep,
    LockProtocolDep,
    PublishProtocolDep,
    RemoveConditionDefinitionDep,
    RemoveControlLayoutDep,
    RemoveOntologyAnnotationDep,
    RemoveProtocolFromProjectDep,
    RemoveProtocolTargetDep,
    RemoveReadoutDefinitionDep,
    ResolveProtocolTargetsDep,
    RetireProtocolDep,
    SetControlLayoutDep,
    SetOntologyAnnotationDep,
    UnlockProtocolDep,
    UpdateConditionDefinitionDep,
    UpdateProtocolDep,
    UpdateReadoutDefinitionDep,
    VersionProtocolDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import PaginatedResponse, clamp_limit, parse_cursor
from cellar.interface.routes._target_refs import (
    ProtocolTargetRefResponse,
    TargetRefResponse,
)

router = APIRouter(prefix="/api/v1")


async def _protocol_response(targets_uc, auth, result) -> ProtocolResponse:
    """Build a ProtocolResponse from a mutation Result, resolving targets.

    Mutation responses must carry the same ``targets`` the GET endpoints do —
    a 201/200 with ``targets: []`` right after target_ids were linked misleads
    API consumers.
    """
    protocol = result_to_response(result)
    targets_by_protocol = result_to_response(
        await targets_uc(
            ResolveProtocolTargetsQuery(
                workspace_id=auth.workspace_id, protocol_ids=(protocol.id,)
            ),
            auth=auth,
        )
    )
    return ProtocolResponse.from_domain(
        protocol,
        targets=[
            TargetRefResponse.from_ref(t)
            for t in targets_by_protocol.get(protocol.id, [])
        ],
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ReadoutDefinitionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    data_type: str
    unit: str | None = None
    aggregation: str
    precision: int | None = None
    # List of normalization formulas this readout def emits. Empty = raw / no normalization.
    normalizations: list[str] = []
    is_calculated: bool
    calculation_formula: str | None = None
    display_order: int
    # Pick-list values for PICK_LIST data_type. Each is `{label, color}`
    # where color is a 7-char hex (#rrggbb) or null for "auto". The shape
    # diverges from ConditionDefinition (which stays list[str]) — colors
    # are only meaningful for measurement classifications, not condition
    # variables.
    pick_list_values: list[dict] | None = None
    dose_response_config: dict | None = None


class ConditionDefinitionResponse(BaseModel):
    id: uuid.UUID
    name: str
    data_type: str
    unit: str | None = None
    pick_list_values: list[str] | None = None


class ProtocolResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    protocol_type: str
    # Effective targets (direct union run-derived), lightweight for display.
    # The design tab fetches the richer provenance list via
    # GET /protocols/{id}/targets.
    targets: list[TargetRefResponse] = []
    category: str | None = None
    protocol_version: int
    parent_protocol_id: uuid.UUID | None = None
    status: str
    created_by: uuid.UUID
    # Canonical dose unit for all wells + IC50 fits of runs of this protocol.
    dose_unit: str
    # POS control signal direction — "high" (uninhibited reference) or
    # "low" (known-inhibitor reference). Drives normalization formula.
    pos_control_signal: str
    readout_definitions: list[ReadoutDefinitionResponse]
    condition_definitions: list[ConditionDefinitionResponse]
    control_layouts: dict[str, str] | None = None
    ontology_annotations: dict[str, list[dict]] | None = None
    project_ids: list[uuid.UUID] = []
    recommended_hit_criteria: list[dict] | None = None
    # Lock state — orthogonal to status. Mirrors RunResponse lock fields.
    is_locked: bool = False
    locked_by: uuid.UUID | None = None
    lock_reason: str | None = None
    locked_at: datetime | None = None

    @classmethod
    def from_domain(
        cls,
        p: Protocol,
        *,
        project_ids: list[uuid.UUID] | None = None,
        targets: list[TargetRefResponse] | None = None,
    ) -> ProtocolResponse:
        # Serialize ontology_annotations
        onto_annots = None
        if p.ontology_annotations:
            onto_annots = {
                slot: [
                    {
                        "term_id": t.term_id,
                        "label": t.label,
                        "ontology_source": t.ontology_source,
                        "uri": t.uri,
                    }
                    for t in terms
                ]
                for slot, terms in p.ontology_annotations.items()
            }

        return cls(
            id=p.id,
            workspace_id=p.workspace_id,
            name=p.name,
            description=p.description,
            protocol_type=p.protocol_type.value,
            targets=targets or [],
            category=p.category,
            protocol_version=p.protocol_version,
            parent_protocol_id=p.parent_protocol_id,
            status=p.status.value,
            created_by=p.created_by,
            dose_unit=p.dose_unit.value,
            pos_control_signal=p.pos_control_signal.value,
            readout_definitions=[
                ReadoutDefinitionResponse(
                    id=rd.id,
                    name=rd.name,
                    description=rd.description,
                    data_type=rd.data_type.value,
                    unit=rd.unit,
                    aggregation=rd.aggregation.value,
                    precision=rd.precision,
                    normalizations=sorted(n.value for n in rd.normalizations),
                    is_calculated=rd.is_calculated,
                    calculation_formula=rd.calculation_formula,
                    display_order=rd.display_order,
                    pick_list_values=(
                        [v.to_dict() for v in rd.pick_list_values] if rd.pick_list_values else None
                    ),
                    dose_response_config=(
                        serialize_dose_response_config(rd.dose_response_config)
                        if rd.dose_response_config is not None
                        else None
                    ),
                )
                for rd in p.readout_definitions
            ],
            condition_definitions=[
                ConditionDefinitionResponse(
                    id=cd.id,
                    name=cd.name,
                    data_type=cd.data_type.value,
                    unit=cd.unit,
                    pick_list_values=cd.pick_list_values,
                )
                for cd in p.condition_definitions
            ],
            control_layouts=(
                {k: str(v) for k, v in p.control_layouts.items()} if p.control_layouts else None
            ),
            ontology_annotations=onto_annots,
            project_ids=project_ids or [],
            recommended_hit_criteria=(
                [c.to_dict() for c in p.recommended_hit_criteria]
                if p.recommended_hit_criteria
                else None
            ),
            is_locked=p.is_locked,
            locked_by=p.locked_by,
            lock_reason=p.lock_reason,
            locked_at=p.locked_at,
        )


class ConditionGroupReadoutResponse(BaseModel):
    readout_definition_id: uuid.UUID
    name: str
    value: float
    unit: str | None = None
    aggregation: str
    count: int


class ConditionGroupResponse(BaseModel):
    condition_value: str
    run_count: int
    aggregated_readouts: list[ConditionGroupReadoutResponse]


class ConditionGroupsResponse(BaseModel):
    condition_name: str
    groups: list[ConditionGroupResponse]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateProtocolRequest(BaseModel):
    name: str
    description: str | None = None
    protocol_type: str
    target_ids: list[uuid.UUID] = []
    category: str | None = None
    dose_unit: str = "uM"
    pos_control_signal: str = "high"
    readout_definitions: list[dict[str, Any]]
    condition_definitions: list[dict[str, Any]] | None = None

    # The single target_id field was replaced by target_ids (migration 051);
    # forbid extras so a client still sending it gets a 422 instead of a
    # silent no-op.
    model_config = {"extra": "forbid"}


class RetireRequest(BaseModel):
    reason: str | None = None


class AddReadoutDefinitionRequest(BaseModel):
    name: str
    description: str | None = None
    data_type: str
    unit: str | None = None
    aggregation: str = "none"
    precision: int | None = None
    # List of normalization formula names. Empty list = no normalization.
    normalizations: list[str] = []
    is_calculated: bool = False
    calculation_formula: str | None = None
    display_order: int = 0
    # Pick-list values: each item is either a `{label, color?}` dict
    # (preferred) or a bare string (legacy). The use case lifts strings
    # to `{label}` automatically.
    pick_list_values: list[dict | str] | None = None
    dose_response_config: dict | None = None


class UpdateReadoutDefinitionRequest(BaseModel):
    """Partial-update payload. Only fields present in the JSON are applied."""

    name: str | None = None
    description: str | None = None
    data_type: str | None = None
    unit: str | None = None
    aggregation: str | None = None
    precision: int | None = None
    # List of normalization formulas. Sending [] clears all formulas.
    normalizations: list[str] | None = None
    is_calculated: bool | None = None
    calculation_formula: str | None = None
    display_order: int | None = None
    pick_list_values: list[dict | str] | None = None
    dose_response_config: dict | None = None


# ---------------------------------------------------------------------------
# Protocol routes
# ---------------------------------------------------------------------------


@router.post("/protocols", response_model=ProtocolResponse, status_code=201, tags=["protocols"])
async def create_protocol(
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    body: CreateProtocolRequest,
    uc: CreateProtocolDep,
) -> ProtocolResponse:
    cmd = CreateProtocolCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        protocol_type=body.protocol_type,
        target_ids=body.target_ids,
        category=body.category,
        dose_unit=body.dose_unit,
        pos_control_signal=body.pos_control_signal,
        readout_definitions=body.readout_definitions,
        condition_definitions=body.condition_definitions or [],
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


class ProtocolSummaryResponse(BaseModel):
    """Lightweight row for the protocol picker — name + status + run stats."""

    id: uuid.UUID
    name: str
    status: str
    protocol_type: str
    description: str | None = None
    targets: list[TargetRefResponse] = []
    run_count: int = 0
    last_run_date: date | None = None


@router.get(
    "/protocols/summary",
    response_model=list[ProtocolSummaryResponse],
    tags=["protocols"],
)
async def list_protocol_summaries(
    auth: AuthDep,
    uc: ListProtocolSummariesDep,
    project_ids: list[uuid.UUID] | None = Query(default=None),
) -> list[ProtocolSummaryResponse]:
    """List protocols enriched with run_count + last_run_date for the picker.

    When ``project_ids`` is provided, the summaries are restricted to protocols
    linked to any of those projects (union). Empty/omitted ⇒ workspace-wide.
    """
    result = await uc(
        ListProtocolSummariesQuery(
            workspace_id=auth.workspace_id,
            project_ids=tuple(project_ids) if project_ids else None,
        ),
        auth=auth,
    )
    summaries = result_to_response(result)
    return [
        ProtocolSummaryResponse(
            id=s.id,
            name=s.name,
            status=s.status,
            protocol_type=s.protocol_type,
            description=s.description,
            targets=[TargetRefResponse.from_ref(t) for t in s.targets],
            run_count=s.run_count,
            last_run_date=s.last_run_date,
        )
        for s in summaries
    ]


@router.get("/protocols", response_model=PaginatedResponse[ProtocolResponse], tags=["protocols"])
async def list_protocols(
    auth: AuthDep,
    uc: ListProtocolsDep,
    uc_by_project: ListProtocolsByProjectDep,
    project_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = None,
    limit: int | None = None,
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
) -> PaginatedResponse[ProtocolResponse]:
    parsed_cursor = parse_cursor(cursor)
    clamped_limit = clamp_limit(limit)
    if project_id is not None:
        result = await uc_by_project(
            ListProtocolsByProjectQuery(
                workspace_id=auth.workspace_id,
                project_id=project_id,
                cursor_id=parsed_cursor,
                limit=clamped_limit,
                tags=tags,
                tag_logic=tag_logic,
            ),
            auth=auth,
        )
        page = result_to_response(result)
    else:
        result = await uc(
            ListProtocolsQuery(
                workspace_id=auth.workspace_id,
                cursor_id=parsed_cursor,
                limit=clamped_limit,
                tags=tags,
                tag_logic=tag_logic,
            ),
            auth=auth,
        )
        page = result_to_response(result)

    # Targets ride along from the use case — same transaction as the rows.
    return PaginatedResponse(
        items=[
            ProtocolResponse.from_domain(
                item.protocol,
                targets=[TargetRefResponse.from_ref(t) for t in item.targets],
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/protocols/{protocol_id}", response_model=ProtocolResponse, tags=["protocols"])
async def get_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: GetProtocolDep,
) -> ProtocolResponse:
    result = await uc(
        GetProtocolQuery(workspace_id=auth.workspace_id, protocol_id=protocol_id),
        auth=auth,
    )
    item = result_to_response(result)
    return ProtocolResponse.from_domain(
        item.protocol,
        targets=[TargetRefResponse.from_ref(t) for t in item.targets],
    )


@router.post(
    "/protocols/{protocol_id}/publish", response_model=ProtocolResponse, tags=["protocols"]
)
async def publish_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: PublishProtocolDep,
) -> ProtocolResponse:
    result = await uc(
        PublishProtocolCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id), auth=auth
    )
    return await _protocol_response(targets_uc, auth, result)


@router.post(
    "/protocols/{protocol_id}/retire", response_model=ProtocolResponse, tags=["protocols"]
)
async def retire_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    body: RetireRequest,
    uc: RetireProtocolDep,
) -> ProtocolResponse:
    result = await uc(
        RetireProtocolCommand(
            workspace_id=auth.workspace_id, protocol_id=protocol_id, reason=body.reason
        ),
        auth=auth,
    )
    return await _protocol_response(targets_uc, auth, result)


class LockProtocolRequest(BaseModel):
    reason: str


@router.post(
    "/protocols/{protocol_id}/lock",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def lock_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    body: LockProtocolRequest,
    uc: LockProtocolDep,
) -> ProtocolResponse:
    """Freeze the protocol's metadata. While locked, every mutation
    method raises until ``unlock`` is called. Workflow gate, orthogonal
    to status — see ``Protocol.lock`` for invariants."""
    result = await uc(
        LockProtocolCommand(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            reason=body.reason,
        ),
        auth=auth,
    )
    return await _protocol_response(targets_uc, auth, result)


@router.post(
    "/protocols/{protocol_id}/unlock",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def unlock_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    body: LockProtocolRequest,
    uc: UnlockProtocolDep,
) -> ProtocolResponse:
    """Release the lock. Reason is required for the audit log."""
    result = await uc(
        UnlockProtocolCommand(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            reason=body.reason,
        ),
        auth=auth,
    )
    return await _protocol_response(targets_uc, auth, result)


@router.post(
    "/protocols/{protocol_id}/version",
    response_model=ProtocolResponse,
    status_code=201,
    tags=["protocols"],
)
async def version_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: VersionProtocolDep,
) -> ProtocolResponse:
    result = await uc(
        VersionProtocolCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id), auth=auth
    )
    return await _protocol_response(targets_uc, auth, result)


class UpdateProtocolRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    recommended_hit_criteria: list[dict] | None = None
    # Allowed on ACTIVE protocols (unlike the other fields above which are
    # DRAFT-only). The use case applies it via Protocol.set_pos_control_signal.
    pos_control_signal: str | None = None

    # The single target_id field was replaced by the /targets sub-resource
    # (migration 051); forbid extras so an old client PATCHing target_id gets
    # a 422 instead of a silent 200 no-op.
    model_config = {"extra": "forbid"}


@router.patch("/protocols/{protocol_id}", response_model=ProtocolResponse, tags=["protocols"])
async def update_protocol(
    protocol_id: uuid.UUID,
    body: UpdateProtocolRequest,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: UpdateProtocolDep,
) -> ProtocolResponse:
    """Update a DRAFT protocol's metadata."""

    # ``name`` and ``pos_control_signal`` are typed as ``str | None`` on the
    # command — None means "leave unchanged". The other fields are nullable
    # and use UNSET to distinguish omission from "set to null".
    cmd = UpdateProtocolCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        name=body.name,
        description=body.description if "description" in body.model_fields_set else UNSET,
        category=body.category if "category" in body.model_fields_set else UNSET,
        recommended_hit_criteria=body.recommended_hit_criteria
        if "recommended_hit_criteria" in body.model_fields_set
        else UNSET,
        pos_control_signal=body.pos_control_signal,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


@router.delete("/protocols/{protocol_id}", status_code=204, tags=["protocols"])
async def delete_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: DeleteProtocolDep,
) -> None:
    """Delete a DRAFT protocol. Only drafts can be deleted."""
    result_to_response(
        await uc(
            DeleteProtocolCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id),
            auth=auth,
        )
    )


# ---------------------------------------------------------------------------
# Readout definition routes
# ---------------------------------------------------------------------------


@router.post(
    "/protocols/{protocol_id}/readout-definitions",
    response_model=ProtocolResponse,
    status_code=201,
    tags=["protocols"],
)
async def add_readout_definition(
    protocol_id: uuid.UUID,
    body: AddReadoutDefinitionRequest,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: AddReadoutDefinitionDep,
) -> ProtocolResponse:
    """Add a readout definition to a DRAFT protocol."""
    cmd = AddReadoutDefinitionCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        name=body.name,
        description=body.description,
        data_type=body.data_type,
        unit=body.unit,
        aggregation=body.aggregation,
        precision=body.precision,
        normalizations=body.normalizations,
        is_calculated=body.is_calculated,
        calculation_formula=body.calculation_formula,
        display_order=body.display_order,
        pick_list_values=body.pick_list_values,
        dose_response_config=body.dose_response_config,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


@router.put(
    "/protocols/{protocol_id}/readout-definitions/{definition_id}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def update_readout_definition(
    protocol_id: uuid.UUID,
    definition_id: uuid.UUID,
    body: UpdateReadoutDefinitionRequest,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: UpdateReadoutDefinitionDep,
) -> ProtocolResponse:
    """Edit a readout definition on a DRAFT protocol. Partial-update semantics."""
    sent = body.model_fields_set
    cmd_kwargs: dict = {}
    # Mandatory IDs
    cmd_kwargs["workspace_id"] = auth.workspace_id
    cmd_kwargs["protocol_id"] = protocol_id
    cmd_kwargs["definition_id"] = definition_id
    # Only forward keys explicitly present in the request body. Otherwise
    # the use case keeps its sentinel default ("leave unchanged").
    for key in (
        "name",
        "data_type",
        "aggregation",
        "is_calculated",
        "display_order",
    ):
        if key in sent:
            cmd_kwargs[key] = getattr(body, key)
    for key in (
        "unit",
        "precision",
        "calculation_formula",
        "description",
        "normalizations",
        "pick_list_values",
        "dose_response_config",
    ):
        if key in sent:
            cmd_kwargs[key] = getattr(body, key)

    cmd = UpdateReadoutDefinitionCommand(**cmd_kwargs)
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


@router.delete(
    "/protocols/{protocol_id}/readout-definitions/{definition_id}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def remove_readout_definition(
    protocol_id: uuid.UUID,
    definition_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: RemoveReadoutDefinitionDep,
) -> ProtocolResponse:
    """Remove a readout definition from a DRAFT protocol."""
    cmd = RemoveReadoutDefinitionCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        definition_id=definition_id,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


# ---------------------------------------------------------------------------
# Condition definition routes
# ---------------------------------------------------------------------------


class AddConditionDefinitionRequest(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    pick_list_values: list[str] | None = None


@router.post(
    "/protocols/{protocol_id}/condition-definitions",
    response_model=ProtocolResponse,
    status_code=201,
    tags=["protocols"],
)
async def add_condition_definition(
    protocol_id: uuid.UUID,
    body: AddConditionDefinitionRequest,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: AddConditionDefinitionDep,
) -> ProtocolResponse:
    """Add a condition definition to a DRAFT protocol."""
    cmd = AddConditionDefinitionCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        name=body.name,
        data_type=body.data_type,
        unit=body.unit,
        pick_list_values=body.pick_list_values,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


class UpdateConditionDefinitionRequest(BaseModel):
    """Partial-update payload."""

    name: str | None = None
    data_type: str | None = None
    unit: str | None = None
    pick_list_values: list[str] | None = None


@router.put(
    "/protocols/{protocol_id}/condition-definitions/{definition_id}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def update_condition_definition(
    protocol_id: uuid.UUID,
    definition_id: uuid.UUID,
    body: UpdateConditionDefinitionRequest,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: UpdateConditionDefinitionDep,
) -> ProtocolResponse:
    """Edit a condition definition on a DRAFT protocol. Partial-update semantics."""
    sent = body.model_fields_set
    cmd_kwargs: dict = {
        "workspace_id": auth.workspace_id,
        "protocol_id": protocol_id,
        "definition_id": definition_id,
    }
    for key in ("name", "data_type", "unit", "pick_list_values"):
        if key in sent:
            cmd_kwargs[key] = getattr(body, key)

    cmd = UpdateConditionDefinitionCommand(**cmd_kwargs)
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


@router.delete(
    "/protocols/{protocol_id}/condition-definitions/{definition_id}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def remove_condition_definition(
    protocol_id: uuid.UUID,
    definition_id: uuid.UUID,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: RemoveConditionDefinitionDep,
) -> ProtocolResponse:
    """Remove a condition definition from a DRAFT protocol."""
    cmd = RemoveConditionDefinitionCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        definition_id=definition_id,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


# ---------------------------------------------------------------------------
# Control layout routes
# ---------------------------------------------------------------------------


class SetControlLayoutRequest(BaseModel):
    plate_format: str
    template_id: uuid.UUID


@router.put(
    "/protocols/{protocol_id}/control-layouts",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def set_control_layout(
    protocol_id: uuid.UUID,
    body: SetControlLayoutRequest,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: SetControlLayoutDep,
) -> ProtocolResponse:
    """Set a default control layout (plate template) for a plate format on a DRAFT protocol."""
    cmd = SetControlLayoutCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        plate_format=body.plate_format,
        template_id=body.template_id,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


@router.delete(
    "/protocols/{protocol_id}/control-layouts/{plate_format}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def remove_control_layout(
    protocol_id: uuid.UUID,
    plate_format: str,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: RemoveControlLayoutDep,
) -> ProtocolResponse:
    """Remove the default control layout for a plate format from a DRAFT protocol."""
    cmd = RemoveControlLayoutCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        plate_format=plate_format,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


# ---------------------------------------------------------------------------
# Ontology annotation routes
# ---------------------------------------------------------------------------


class SetOntologyAnnotationRequest(BaseModel):
    slot: str
    terms: list[dict]


@router.put(
    "/protocols/{protocol_id}/ontology-annotations",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def set_ontology_annotation(
    protocol_id: uuid.UUID,
    body: SetOntologyAnnotationRequest,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: SetOntologyAnnotationDep,
) -> ProtocolResponse:
    """Set ontology terms for a slot on a DRAFT protocol."""
    cmd = SetOntologyAnnotationCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        slot=body.slot,
        terms=body.terms,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


@router.delete(
    "/protocols/{protocol_id}/ontology-annotations/{slot}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def remove_ontology_annotation(
    protocol_id: uuid.UUID,
    slot: str,
    auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep,
    uc: RemoveOntologyAnnotationDep,
) -> ProtocolResponse:
    """Remove all ontology terms for a slot from a DRAFT protocol."""
    cmd = RemoveOntologyAnnotationCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        slot=slot,
    )
    result = await uc(cmd, auth=auth)
    return await _protocol_response(targets_uc, auth, result)


# ---------------------------------------------------------------------------
# Protocol-Project association routes
# ---------------------------------------------------------------------------


@router.post(
    "/protocols/{protocol_id}/projects/{project_id}",
    status_code=204,
    tags=["protocols"],
)
async def add_protocol_to_project(
    protocol_id: uuid.UUID,
    project_id: uuid.UUID,
    auth: AuthDep,
    uc: AddProtocolToProjectDep,
) -> Response:
    """Link a protocol to a project (idempotent)."""
    result = await uc(
        AddProtocolToProjectCommand(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            project_id=project_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.delete(
    "/protocols/{protocol_id}/projects/{project_id}",
    status_code=204,
    tags=["protocols"],
)
async def remove_protocol_from_project(
    protocol_id: uuid.UUID,
    project_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveProtocolFromProjectDep,
) -> Response:
    """Unlink a protocol from a project."""
    result = await uc(
        RemoveProtocolFromProjectCommand(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            project_id=project_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Protocol-Target association routes
# ---------------------------------------------------------------------------


@router.get(
    "/protocols/{protocol_id}/targets",
    response_model=list[ProtocolTargetRefResponse],
    tags=["protocols"],
)
async def list_protocol_targets(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: GetProtocolTargetsDep,
) -> list[ProtocolTargetRefResponse]:
    """Effective targets for a protocol with provenance (direct vs from-runs)."""
    result = await uc(
        GetProtocolTargetsQuery(workspace_id=auth.workspace_id, protocol_id=protocol_id),
        auth=auth,
    )
    return [ProtocolTargetRefResponse.from_effective(t) for t in result_to_response(result)]


@router.post(
    "/protocols/{protocol_id}/targets/{target_id}",
    status_code=204,
    tags=["protocols"],
)
async def add_protocol_target(
    protocol_id: uuid.UUID,
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: AddProtocolTargetDep,
) -> Response:
    """Attach a direct target to a protocol (idempotent)."""
    result = await uc(
        AddProtocolTargetCommand(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            target_id=target_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.delete(
    "/protocols/{protocol_id}/targets/{target_id}",
    status_code=204,
    tags=["protocols"],
)
async def remove_protocol_target(
    protocol_id: uuid.UUID,
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveProtocolTargetDep,
) -> Response:
    """Remove a direct target from a protocol."""
    result = await uc(
        RemoveProtocolTargetCommand(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            target_id=target_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Condition grouping routes
# ---------------------------------------------------------------------------


@router.get(
    "/protocols/{protocol_id}/condition-groups",
    response_model=ConditionGroupsResponse,
    tags=["protocols"],
)
async def get_condition_groups(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    condition_name: Annotated[str, Query(...)],
    svc: ConditionGroupingServiceDep,
) -> ConditionGroupsResponse:
    """Aggregate readout data grouped by a condition value."""
    result = await svc.group_by_condition(auth.workspace_id, protocol_id, condition_name)
    groups = result_to_response(result)
    return ConditionGroupsResponse(
        condition_name=condition_name,
        groups=[
            ConditionGroupResponse(
                condition_value=g.condition_value,
                run_count=g.run_count,
                aggregated_readouts=[
                    ConditionGroupReadoutResponse(
                        readout_definition_id=ar.readout_definition_id,
                        name=ar.name,
                        value=ar.value,
                        unit=ar.unit,
                        aggregation=ar.aggregation,
                        count=ar.count,
                    )
                    for ar in g.aggregated_readouts
                ],
            )
            for g in groups
        ],
    )
