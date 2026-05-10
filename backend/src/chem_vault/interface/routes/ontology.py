"""Ontology slot definitions and search endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from chem_vault.application.screening.search_ontology import (
    SearchOntology,
    SearchOntologyQuery,
)
from chem_vault.application.workspace_config.create_ontology_slot import (
    CreateOntologySlot,
    CreateOntologySlotCommand,
)
from chem_vault.application.workspace_config.delete_ontology_slot import (
    DeleteOntologySlot,
    DeleteOntologySlotCommand,
)
from chem_vault.application.workspace_config.list_ontology_slots import (
    ListOntologySlots,
    ListOntologySlotsQuery,
)
from chem_vault.application.workspace_config.update_ontology_slot import (
    UpdateOntologySlot,
    UpdateOntologySlotCommand,
)
from chem_vault.domain.shared.ontology import OntologyTerm
from chem_vault.domain.workspace_config.ontology_slot_definition import OntologySlotDefinition
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateOntologySlotDep,
    DeleteOntologySlotDep,
    ListOntologySlotsDep,
    SearchOntologyDep,
    UpdateOntologySlotDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["ontology"])


# ---------------------------------------------------------------------------
# Response / Request models
# ---------------------------------------------------------------------------


class OntologyTermResponse(BaseModel):
    term_id: str
    label: str
    ontology_source: str
    uri: str | None = None

    @classmethod
    def from_domain(cls, t: OntologyTerm) -> OntologyTermResponse:
        return cls(
            term_id=t.term_id,
            label=t.label,
            ontology_source=t.ontology_source,
            uri=t.uri,
        )


class OntologySlotResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    label: str
    ontology_sources: list[str]
    root_concept_id: str | None = None
    is_required: bool
    allow_free_text: bool
    display_order: int
    version: int

    @classmethod
    def from_domain(cls, slot: OntologySlotDefinition) -> OntologySlotResponse:
        return cls(
            id=slot.id,
            workspace_id=slot.workspace_id,
            name=slot.name,
            label=slot.label,
            ontology_sources=list(slot.ontology_sources),
            root_concept_id=slot.root_concept_id,
            is_required=slot.is_required,
            allow_free_text=slot.allow_free_text,
            display_order=slot.display_order,
            version=slot.version,
        )


class CreateOntologySlotBody(BaseModel):
    name: str
    label: str
    ontology_sources: list[str]
    root_concept_id: str | None = None
    is_required: bool = False
    allow_free_text: bool = True
    display_order: int = 0


class UpdateOntologySlotBody(BaseModel):
    label: str | None = None
    ontology_sources: list[str] | None = None
    root_concept_id: str | None = None
    is_required: bool | None = None
    allow_free_text: bool | None = None
    display_order: int | None = None


# ---------------------------------------------------------------------------
# Ontology search
# ---------------------------------------------------------------------------


@router.get("/ontology/search", response_model=list[OntologyTermResponse])
async def search_ontology(
    auth: AuthDep,
    use_case: SearchOntologyDep,
    q: str = Query(..., min_length=1),
    ontologies: str = Query(default=""),
    subtree_root_id: str | None = Query(default=None),
) -> list[OntologyTermResponse]:
    sources = [s.strip() for s in ontologies.split(",") if s.strip()] if ontologies else []
    query = SearchOntologyQuery(
        workspace_id=auth.workspace_id,
        query=q,
        ontology_sources=sources,
        subtree_root_id=subtree_root_id,
    )
    terms = result_to_response(await use_case(query, auth=auth))
    return [OntologyTermResponse.from_domain(t) for t in terms]


@router.get("/ontology/descendants", response_model=list[OntologyTermResponse])
async def list_ontology_descendants(
    auth: AuthDep,
    use_case: SearchOntologyDep,
    ontology: str = Query(...),
    root_concept_id: str = Query(...),
) -> list[OntologyTermResponse]:
    """List all descendants of a concept — for dropdown-style selection."""
    # Access the BioPortalClient through the search service (same DI instance)
    bioportal = use_case._search_service  # type: ignore[attr-defined]
    terms = await bioportal.list_descendants(
        ontology=ontology,
        root_concept_id=root_concept_id,
        workspace_id=auth.workspace_id,
    )
    return [OntologyTermResponse.from_domain(t) for t in terms]


# ---------------------------------------------------------------------------
# Ontology slot CRUD
# ---------------------------------------------------------------------------


@router.get("/ontology-slots", response_model=list[OntologySlotResponse])
async def list_ontology_slots(
    auth: AuthDep,
    use_case: ListOntologySlotsDep,
) -> list[OntologySlotResponse]:
    query = ListOntologySlotsQuery(workspace_id=auth.workspace_id)
    slots = result_to_response(await use_case(query, auth=auth))
    return [OntologySlotResponse.from_domain(s) for s in slots]


@router.post("/ontology-slots", response_model=OntologySlotResponse, status_code=201)
async def create_ontology_slot(
    body: CreateOntologySlotBody,
    auth: AuthDep,
    use_case: CreateOntologySlotDep,
) -> OntologySlotResponse:
    command = CreateOntologySlotCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        label=body.label,
        ontology_sources=body.ontology_sources,
        root_concept_id=body.root_concept_id,
        is_required=body.is_required,
        allow_free_text=body.allow_free_text,
        display_order=body.display_order,
    )
    slot = result_to_response(await use_case(command, auth=auth))
    return OntologySlotResponse.from_domain(slot)


@router.patch("/ontology-slots/{slot_id}", response_model=OntologySlotResponse)
async def update_ontology_slot(
    slot_id: uuid.UUID,
    body: UpdateOntologySlotBody,
    auth: AuthDep,
    use_case: UpdateOntologySlotDep,
) -> OntologySlotResponse:
    from chem_vault.application.shared.sentinel import UNSET

    cmd_fields: dict[str, Any] = {
        "workspace_id": auth.workspace_id,
        "slot_id": slot_id,
    }
    for attr in ("label", "ontology_sources", "root_concept_id", "is_required", "allow_free_text", "display_order"):
        cmd_fields[attr] = getattr(body, attr) if attr in body.model_fields_set else UNSET

    command = UpdateOntologySlotCommand(**cmd_fields)
    slot = result_to_response(await use_case(command, auth=auth))
    return OntologySlotResponse.from_domain(slot)


@router.delete("/ontology-slots/{slot_id}", status_code=204)
async def delete_ontology_slot(
    slot_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteOntologySlotDep,
) -> None:
    command = DeleteOntologySlotCommand(
        workspace_id=auth.workspace_id,
        slot_id=slot_id,
    )
    result_to_response(await use_case(command, auth=auth))
