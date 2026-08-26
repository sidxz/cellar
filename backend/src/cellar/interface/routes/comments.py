"""Comment endpoints — feed on plate loans / groups / plates."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from cellar.application.inventory.comments import AddCommentCommand, ListCommentsQuery
from cellar.domain.inventory.comment import MAX_COMMENT_BODY, Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.interface.dependencies import AddCommentDep, AuthDep, ListCommentsDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/comments", tags=["comments"])


class CommentResponse(BaseModel):
    id: uuid.UUID
    target_type: CommentTarget
    target_id: uuid.UUID
    loan_id: uuid.UUID | None = None
    body: str
    author_id: uuid.UUID | None = None
    author_name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, c: Comment) -> CommentResponse:
        return cls(
            id=c.id, target_type=c.target_type, target_id=c.target_id, loan_id=c.loan_id,
            body=c.body, author_id=c.author_id, author_name=c.author_name, created_at=c.created_at,
        )


class AddCommentBody(BaseModel):
    target_type: CommentTarget
    target_id: uuid.UUID
    body: str = Field(min_length=1, max_length=MAX_COMMENT_BODY)
    loan_id: uuid.UUID | None = None

    model_config = {"extra": "forbid"}


@router.get("", response_model=list[CommentResponse])
async def list_comments(
    auth: AuthDep,
    uc: ListCommentsDep,
    target_type: CommentTarget | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    loan_id: uuid.UUID | None = Query(default=None),
) -> list[CommentResponse]:
    """Comments on one target (target_type + target_id) or every comment made
    in a loan's context (loan_id)."""
    query = ListCommentsQuery(
        workspace_id=auth.workspace_id, target_type=target_type,
        target_id=target_id, loan_id=loan_id,
    )
    comments = result_to_response(await uc(query, auth=auth))
    return [CommentResponse.from_domain(c) for c in comments]


@router.post("", response_model=CommentResponse, status_code=201)
async def add_comment(body: AddCommentBody, auth: AuthDep, uc: AddCommentDep) -> CommentResponse:
    command = AddCommentCommand(
        workspace_id=auth.workspace_id, target_type=body.target_type, target_id=body.target_id,
        body=body.body, loan_id=body.loan_id,
    )
    return CommentResponse.from_domain(result_to_response(await uc(command, auth=auth)))
