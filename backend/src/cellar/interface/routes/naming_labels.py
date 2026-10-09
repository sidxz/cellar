"""Short labels: admin overrides of how ontology terms read inside protocol names."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.workspace_config.naming_labels import (
    CreateNamingLabelCommand,
    DeleteNamingLabelCommand,
    ListNamingLabelsQuery,
    ListNamingTermsInUseQuery,
    NamingTermInUse,
    UpdateNamingLabelCommand,
)
from cellar.domain.workspace_config.naming_label import NamingLabel
from cellar.interface.dependencies import (
    AuthDep,
    CreateNamingLabelDep,
    DeleteNamingLabelDep,
    ListNamingLabelsDep,
    ListNamingTermsInUseDep,
    UpdateNamingLabelDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/naming-labels", tags=["naming-labels"])


class NamingLabelResponse(BaseModel):
    id: uuid.UUID
    term_id: str
    term_label: str
    ontology_source: str
    short_label: str
    version: int

    @classmethod
    def from_domain(cls, label: NamingLabel) -> NamingLabelResponse:
        return cls(
            id=label.id,
            term_id=label.term_id,
            term_label=label.term_label,
            ontology_source=label.ontology_source,
            short_label=label.short_label,
            version=label.version,
        )


class NamingTermInUseResponse(BaseModel):
    slot: str
    term_id: str
    term_label: str
    ontology_source: str
    protocol_count: int
    default_short_label: str
    override_id: uuid.UUID | None = None
    override_short_label: str | None = None

    @classmethod
    def from_domain(cls, t: NamingTermInUse) -> NamingTermInUseResponse:
        return cls(
            slot=t.slot,
            term_id=t.term_id,
            term_label=t.term_label,
            ontology_source=t.ontology_source,
            protocol_count=t.protocol_count,
            default_short_label=t.default_short_label,
            override_id=t.override.id if t.override else None,
            override_short_label=t.override.short_label if t.override else None,
        )


class CreateNamingLabelBody(BaseModel):
    term_id: str
    term_label: str
    ontology_source: str
    short_label: str
    model_config = {"extra": "forbid"}


class UpdateNamingLabelBody(BaseModel):
    short_label: str
    model_config = {"extra": "forbid"}


@router.get("", response_model=list[NamingLabelResponse])
async def list_naming_labels(
    auth: AuthDep, use_case: ListNamingLabelsDep
) -> list[NamingLabelResponse]:
    labels = result_to_response(
        await use_case(ListNamingLabelsQuery(workspace_id=auth.workspace_id), auth=auth)
    )
    return [NamingLabelResponse.from_domain(label) for label in labels]


@router.get("/terms-in-use", response_model=list[NamingTermInUseResponse])
async def list_naming_terms_in_use(
    auth: AuthDep, use_case: ListNamingTermsInUseDep
) -> list[NamingTermInUseResponse]:
    """Every term protocol names draw on, its default short label and any override."""
    terms = result_to_response(
        await use_case(ListNamingTermsInUseQuery(workspace_id=auth.workspace_id), auth=auth)
    )
    return [NamingTermInUseResponse.from_domain(t) for t in terms]


@router.post("", response_model=NamingLabelResponse, status_code=201)
async def create_naming_label(
    body: CreateNamingLabelBody, auth: AuthDep, use_case: CreateNamingLabelDep
) -> NamingLabelResponse:
    cmd = CreateNamingLabelCommand(
        workspace_id=auth.workspace_id,
        term_id=body.term_id,
        term_label=body.term_label,
        ontology_source=body.ontology_source,
        short_label=body.short_label,
    )
    return NamingLabelResponse.from_domain(result_to_response(await use_case(cmd, auth=auth)))


@router.patch("/{label_id}", response_model=NamingLabelResponse)
async def update_naming_label(
    label_id: uuid.UUID, body: UpdateNamingLabelBody, auth: AuthDep, use_case: UpdateNamingLabelDep
) -> NamingLabelResponse:
    cmd = UpdateNamingLabelCommand(
        workspace_id=auth.workspace_id, label_id=label_id, short_label=body.short_label
    )
    return NamingLabelResponse.from_domain(result_to_response(await use_case(cmd, auth=auth)))


@router.delete("/{label_id}", status_code=204)
async def delete_naming_label(
    label_id: uuid.UUID, auth: AuthDep, use_case: DeleteNamingLabelDep
) -> None:
    cmd = DeleteNamingLabelCommand(workspace_id=auth.workspace_id, label_id=label_id)
    result_to_response(await use_case(cmd, auth=auth))
