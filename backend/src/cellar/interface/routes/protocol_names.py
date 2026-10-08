"""Workspace-wide protocol naming: preview what an admin naming edit would rename."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.workspace_config.naming_changes import (
    NamingChangePreview,
    PreviewNamingChangeQuery,
)
from cellar.interface.dependencies import AuthDep, PreviewNamingChangeDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/protocol-names", tags=["protocol-names"])


class NamingTermBody(BaseModel):
    term_id: str
    label: str
    ontology_source: str = "NCBITAXON"


class NamingChangeRequest(BaseModel):
    """One admin naming edit. ``category``: category_id + new label and/or name_pattern.
    ``label``: the term + short_label (null = back to the default). ``home_organism``: term."""

    kind: Literal["category", "label", "home_organism"]
    category_id: uuid.UUID | None = None
    label: str | None = None
    name_pattern: str | None = None
    term_id: str | None = None
    term_label: str | None = None
    ontology_source: str | None = None
    short_label: str | None = None
    term: NamingTermBody | None = None
    model_config = {"extra": "forbid"}


class NameChangeResponse(BaseModel):
    protocol_id: uuid.UUID
    code: str | None
    before: str
    after: str


class NameCollisionResponse(BaseModel):
    name: str
    codes: list[str]


class NamingChangePreviewResponse(BaseModel):
    changes: list[NameChangeResponse]
    collisions: list[NameCollisionResponse]

    @classmethod
    def from_domain(cls, p: NamingChangePreview) -> NamingChangePreviewResponse:
        return cls(
            changes=[
                NameChangeResponse(
                    protocol_id=c.protocol_id, code=c.code, before=c.before, after=c.after
                )
                for c in p.changes
            ],
            collisions=[NameCollisionResponse(name=c.name, codes=c.codes) for c in p.collisions],
        )


@router.post("/preview-change", response_model=NamingChangePreviewResponse)
async def preview_naming_change(
    body: NamingChangeRequest, auth: AuthDep, use_case: PreviewNamingChangeDep
) -> NamingChangePreviewResponse:
    """Before -> after for every protocol the edit would rename, and any resulting clash."""
    query = PreviewNamingChangeQuery(
        workspace_id=auth.workspace_id,
        kind=body.kind,
        category_id=body.category_id,
        name_pattern=body.name_pattern,
        label=body.label,
        term_id=body.term_id,
        term_label=body.term_label,
        short_label=body.short_label,
        home_organism=body.term.model_dump() if body.term else None,
    )
    return NamingChangePreviewResponse.from_domain(
        result_to_response(await use_case(query, auth=auth))
    )
