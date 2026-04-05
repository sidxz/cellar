"""Synthesis route API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from chem_vault.application.chemical_registration.synthesis_routes import (
    AddReactionStep,
    AddReactionStepCommand,
    CreateSynthesisRoute,
    CreateSynthesisRouteCommand,
    DeprecateSynthesisRoute,
    GetSynthesisRoute,
    GetSynthesisRouteQuery,
    ListSynthesisRoutesByMolecule,
    ListSynthesisRoutesByMoleculeQuery,
    RecordStepOutcome,
    RecordStepOutcomeCommand,
    SetPreferredRoute,
    ValidateSynthesisRoute,
)
from chem_vault.interface.dependencies import AuthDep, _get_use_case
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["synthesis-routes"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ReagentResponse(BaseModel):
    role: str
    molecule_id: uuid.UUID | None = None
    name: str
    cas_number: str | None = None
    catalog_number: str | None = None
    supplier: str | None = None
    equivalents: float | None = None


class StepResponse(BaseModel):
    id: uuid.UUID
    step_number: int
    branch_label: str | None = None
    name: str | None = None
    named_reaction: str | None = None
    reaction_smiles: str | None = None
    product_molecule_id: uuid.UUID | None = None
    product_description: str | None = None
    conditions: dict | None = None
    outcome: dict | None = None
    reagents: list[ReagentResponse]
    preceding_step_ids: list[uuid.UUID]
    eln_entry_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    notes: str | None = None

    @classmethod
    def from_domain(cls, s) -> StepResponse:  # type: ignore[no-untyped-def]
        conditions_dict = None
        if s.conditions:
            conditions_dict = {
                "solvent": s.conditions.solvent,
                "temperature": s.conditions.temperature,
                "pressure": s.conditions.pressure,
                "catalyst": s.conditions.catalyst,
                "atmosphere": s.conditions.atmosphere,
                "time": s.conditions.time,
            }

        outcome_dict = None
        if s.outcome:
            outcome_dict = {
                "yield_percent": s.outcome.yield_percent,
                "crude_yield_percent": s.outcome.crude_yield_percent,
                "purity_percent": s.outcome.purity_percent,
                "purification_method": s.outcome.purification_method,
            }

        return cls(
            id=s.id,
            step_number=s.step_number,
            branch_label=s.branch_label,
            name=s.name,
            named_reaction=s.named_reaction,
            reaction_smiles=s.reaction_smiles,
            product_molecule_id=s.product_molecule_id,
            product_description=s.product_description,
            conditions=conditions_dict,
            outcome=outcome_dict,
            reagents=[
                ReagentResponse(
                    role=r.role.value,
                    molecule_id=r.molecule_id,
                    name=r.name,
                    cas_number=r.cas_number,
                    catalog_number=r.catalog_number,
                    supplier=r.supplier,
                    equivalents=r.equivalents,
                )
                for r in s.reagents
            ],
            preceding_step_ids=s.preceding_step_ids,
            eln_entry_id=s.eln_entry_id,
            batch_id=s.batch_id,
            notes=s.notes,
        )


class SynthesisRouteResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    target_molecule_id: uuid.UUID
    name: str
    description: str | None = None
    route_type: str
    status: str
    total_steps: int
    overall_yield: float | None = None
    scale: str | None = None
    source: str
    source_reference: str | None = None
    created_by: uuid.UUID
    steps: list[StepResponse]

    @classmethod
    def from_domain(cls, r) -> SynthesisRouteResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=r.id,
            workspace_id=r.workspace_id,
            target_molecule_id=r.target_molecule_id,
            name=r.name,
            description=r.description,
            route_type=r.route_type.value,
            status=r.status.value,
            total_steps=r.total_steps,
            overall_yield=r.overall_yield,
            scale=r.scale.value if r.scale else None,
            source=r.source.value,
            source_reference=r.source_reference,
            created_by=r.created_by,
            steps=[StepResponse.from_domain(s) for s in r.steps],
        )


class SynthesisRouteSummaryResponse(BaseModel):
    """Lightweight response for list endpoints (no steps)."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    target_molecule_id: uuid.UUID
    name: str
    route_type: str
    status: str
    total_steps: int
    overall_yield: float | None = None
    scale: str | None = None
    source: str

    @classmethod
    def from_domain(cls, r) -> SynthesisRouteSummaryResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=r.id,
            workspace_id=r.workspace_id,
            target_molecule_id=r.target_molecule_id,
            name=r.name,
            route_type=r.route_type.value,
            status=r.status.value,
            total_steps=r.total_steps,
            overall_yield=r.overall_yield,
            scale=r.scale.value if r.scale else None,
            source=r.source.value,
        )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateSynthesisRouteRequest(BaseModel):
    target_molecule_id: uuid.UUID
    name: str
    description: str | None = None
    route_type: str = "linear"
    scale: str | None = None
    source: str = "manual"
    source_reference: str | None = None


class AddStepRequest(BaseModel):
    step_number: int
    branch_label: str | None = None
    name: str | None = None
    named_reaction: str | None = None
    reaction_smiles: str | None = None
    reaction_smarts: str | None = None
    product_molecule_id: uuid.UUID | None = None
    product_description: str | None = None
    conditions: dict | None = None
    reagents: list[dict] = []
    preceding_step_ids: list[uuid.UUID] = []
    notes: str | None = None


class RecordOutcomeRequest(BaseModel):
    yield_percent: float | None = None
    crude_yield_percent: float | None = None
    purity_percent: float | None = None
    purification_method: str | None = None
    batch_id: uuid.UUID | None = None


class DeprecateRequest(BaseModel):
    reason: str | None = None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


CreateSynthesisRouteDep = Annotated[CreateSynthesisRoute, Depends(_get_use_case(CreateSynthesisRoute))]
GetSynthesisRouteDep = Annotated[GetSynthesisRoute, Depends(_get_use_case(GetSynthesisRoute))]
ListSynthesisRoutesByMoleculeDep = Annotated[ListSynthesisRoutesByMolecule, Depends(_get_use_case(ListSynthesisRoutesByMolecule))]
AddReactionStepDep = Annotated[AddReactionStep, Depends(_get_use_case(AddReactionStep))]
RecordStepOutcomeDep = Annotated[RecordStepOutcome, Depends(_get_use_case(RecordStepOutcome))]
ValidateSynthesisRouteDep = Annotated[ValidateSynthesisRoute, Depends(_get_use_case(ValidateSynthesisRoute))]
SetPreferredRouteDep = Annotated[SetPreferredRoute, Depends(_get_use_case(SetPreferredRoute))]
DeprecateSynthesisRouteDep = Annotated[DeprecateSynthesisRoute, Depends(_get_use_case(DeprecateSynthesisRoute))]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/synthesis-routes", response_model=SynthesisRouteResponse, status_code=201)
async def create_synthesis_route(
    body: CreateSynthesisRouteRequest, auth: AuthDep, uc: CreateSynthesisRouteDep
) -> SynthesisRouteResponse:
    result = await uc(
        CreateSynthesisRouteCommand(
            workspace_id=auth.workspace_id,
            target_molecule_id=body.target_molecule_id,
            name=body.name,
            description=body.description,
            route_type=body.route_type,
            scale=body.scale,
            source=body.source,
            source_reference=body.source_reference,
        ),
        auth=auth,
    )
    route = result_to_response(result)
    return SynthesisRouteResponse.from_domain(route)


@router.get("/synthesis-routes", response_model=list[SynthesisRouteSummaryResponse])
async def list_synthesis_routes(
    molecule_id: uuid.UUID, auth: AuthDep, uc: ListSynthesisRoutesByMoleculeDep
) -> list[SynthesisRouteSummaryResponse]:
    result = await uc(
        ListSynthesisRoutesByMoleculeQuery(target_molecule_id=molecule_id),
        auth=auth,
    )
    routes = result_to_response(result)
    return [SynthesisRouteSummaryResponse.from_domain(r) for r in routes]


@router.get("/synthesis-routes/{route_id}", response_model=SynthesisRouteResponse)
async def get_synthesis_route(
    route_id: uuid.UUID, auth: AuthDep, uc: GetSynthesisRouteDep
) -> SynthesisRouteResponse:
    result = await uc(GetSynthesisRouteQuery(route_id=route_id), auth=auth)
    route = result_to_response(result)
    return SynthesisRouteResponse.from_domain(route)


@router.post(
    "/synthesis-routes/{route_id}/steps",
    response_model=SynthesisRouteResponse,
    status_code=201,
)
async def add_reaction_step(
    route_id: uuid.UUID, body: AddStepRequest, auth: AuthDep, uc: AddReactionStepDep
) -> SynthesisRouteResponse:
    result = await uc(
        AddReactionStepCommand(
            workspace_id=auth.workspace_id,
            route_id=route_id,
            step_number=body.step_number,
            branch_label=body.branch_label,
            name=body.name,
            named_reaction=body.named_reaction,
            reaction_smiles=body.reaction_smiles,
            reaction_smarts=body.reaction_smarts,
            product_molecule_id=body.product_molecule_id,
            product_description=body.product_description,
            conditions=body.conditions,
            reagents=body.reagents,
            preceding_step_ids=body.preceding_step_ids,
            notes=body.notes,
        ),
        auth=auth,
    )
    route = result_to_response(result)
    return SynthesisRouteResponse.from_domain(route)


@router.put(
    "/synthesis-routes/{route_id}/steps/{step_id}/outcome",
    response_model=SynthesisRouteResponse,
)
async def record_step_outcome(
    route_id: uuid.UUID,
    step_id: uuid.UUID,
    body: RecordOutcomeRequest,
    auth: AuthDep,
    uc: RecordStepOutcomeDep,
) -> SynthesisRouteResponse:
    result = await uc(
        RecordStepOutcomeCommand(
            workspace_id=auth.workspace_id,
            route_id=route_id,
            step_id=step_id,
            yield_percent=body.yield_percent,
            crude_yield_percent=body.crude_yield_percent,
            purity_percent=body.purity_percent,
            purification_method=body.purification_method,
            batch_id=body.batch_id,
        ),
        auth=auth,
    )
    route = result_to_response(result)
    return SynthesisRouteResponse.from_domain(route)


@router.post("/synthesis-routes/{route_id}/validate", response_model=SynthesisRouteResponse)
async def validate_route(
    route_id: uuid.UUID, auth: AuthDep, uc: ValidateSynthesisRouteDep
) -> SynthesisRouteResponse:
    result = await uc(route_id, auth=auth)
    route = result_to_response(result)
    return SynthesisRouteResponse.from_domain(route)


@router.post("/synthesis-routes/{route_id}/prefer", response_model=SynthesisRouteResponse)
async def set_preferred(
    route_id: uuid.UUID, auth: AuthDep, uc: SetPreferredRouteDep
) -> SynthesisRouteResponse:
    result = await uc(route_id, auth=auth)
    route = result_to_response(result)
    return SynthesisRouteResponse.from_domain(route)


@router.post("/synthesis-routes/{route_id}/deprecate", response_model=SynthesisRouteResponse)
async def deprecate_route(
    route_id: uuid.UUID, body: DeprecateRequest, auth: AuthDep, uc: DeprecateSynthesisRouteDep
) -> SynthesisRouteResponse:
    result = await uc(route_id, reason=body.reason, auth=auth)
    route = result_to_response(result)
    return SynthesisRouteResponse.from_domain(route)
