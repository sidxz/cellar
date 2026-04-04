"""Controlled vocabulary CRUD endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.workspace_config.create_vocabulary import CreateVocabularyCommand
from chem_vault.application.workspace_config.delete_vocabulary import DeleteVocabularyCommand
from chem_vault.application.workspace_config.list_vocabularies import ListVocabulariesQuery
from chem_vault.application.workspace_config.update_vocabulary import UpdateVocabularyCommand
from chem_vault.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateVocabularyDep,
    DeleteVocabularyDep,
    ListVocabulariesDep,
    UpdateVocabularyDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/vocabularies", tags=["vocabularies"])


class VocabularyResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    terms: list[str]
    is_locked: bool
    created_by: uuid.UUID
    version: int

    @classmethod
    def from_domain(cls, v: ControlledVocabulary) -> VocabularyResponse:
        return cls(
            id=v.id,
            workspace_id=v.workspace_id,
            name=v.name,
            terms=v.terms,
            is_locked=v.is_locked,
            created_by=v.created_by,
            version=v.version,
        )


class CreateVocabularyBody(BaseModel):
    name: str
    terms: list[str] | None = None


class UpdateVocabularyBody(BaseModel):
    name: str | None = None
    terms: list[str] | None = None
    is_locked: bool | None = None


@router.get("", response_model=list[VocabularyResponse])
async def list_vocabularies(
    auth: AuthDep,
    use_case: ListVocabulariesDep,
) -> list[VocabularyResponse]:
    query = ListVocabulariesQuery(workspace_id=auth.workspace_id)
    vocabs = result_to_response(await use_case(query))
    return [VocabularyResponse.from_domain(v) for v in vocabs]


@router.post("", response_model=VocabularyResponse, status_code=201)
async def create_vocabulary(
    body: CreateVocabularyBody,
    auth: AuthDep,
    use_case: CreateVocabularyDep,
) -> VocabularyResponse:
    command = CreateVocabularyCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        terms=body.terms,
        created_by=auth.user_id,
    )
    vocab = result_to_response(await use_case(command))
    return VocabularyResponse.from_domain(vocab)


@router.patch("/{vocab_id}", response_model=VocabularyResponse)
async def update_vocabulary(
    vocab_id: uuid.UUID,
    body: UpdateVocabularyBody,
    auth: AuthDep,
    use_case: UpdateVocabularyDep,
) -> VocabularyResponse:
    command = UpdateVocabularyCommand(
        workspace_id=auth.workspace_id,
        vocab_id=vocab_id,
        name=body.name,
        terms=body.terms,
        is_locked=body.is_locked,
    )
    vocab = result_to_response(await use_case(command))
    return VocabularyResponse.from_domain(vocab)


@router.delete("/{vocab_id}", status_code=204)
async def delete_vocabulary(
    vocab_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteVocabularyDep,
) -> None:
    command = DeleteVocabularyCommand(
        workspace_id=auth.workspace_id, vocab_id=vocab_id
    )
    result_to_response(await use_case(command))
