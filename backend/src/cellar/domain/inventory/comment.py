"""Comment — an append-only note on a plate loan, plate group, or plate.

The legacy plate tracker's activity log: free text a scientist leaves on a
transaction, and the mandatory "what did you do with these plates" note per
set at check-in. Comments are never edited or deleted (audit alignment).
``loan_id`` is the context link: a group/plate comment written while
returning a loan carries that loan so the loan card can show it too.
``author_name`` is denormalized at write time (legacy authors have no user id).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from cellar.domain.inventory.enums import CommentTarget
from cellar.domain.inventory.events import CommentAdded
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

MAX_COMMENT_BODY = 5000
MAX_AUTHOR_NAME = 200


def _required_text(value: str | None, *, max_len: int, label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"{label} must not be empty")
    if len(cleaned) > max_len:
        raise ValidationError(f"{label} must be at most {max_len} characters")
    return cleaned


class Comment(AggregateRoot):
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        target_type: CommentTarget,
        target_id: uuid.UUID,
        body: str,
        author_id: uuid.UUID | None,
        author_name: str,
        loan_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.target_type = target_type
        self.target_id = target_id
        self.body = _required_text(body, max_len=MAX_COMMENT_BODY, label="body")
        self.author_id = author_id
        self.author_name = _required_text(
            author_name, max_len=MAX_AUTHOR_NAME, label="author_name"
        )
        self.loan_id = loan_id

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        target_type: CommentTarget,
        target_id: uuid.UUID,
        body: str,
        author_id: uuid.UUID | None,
        author_name: str,
        loan_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
    ) -> Comment:
        """``created_at`` is only for the legacy importer (historical timestamps)."""
        comment = cls(
            workspace_id=workspace_id,
            target_type=target_type,
            target_id=target_id,
            body=body,
            author_id=author_id,
            author_name=author_name,
            loan_id=loan_id,
            created_at=created_at,
        )
        comment.register_event(
            CommentAdded(
                aggregate_id=comment.id,
                aggregate_type="Comment",
                workspace_id=workspace_id,
                target_type=target_type,
                target_id=target_id,
                loan_id=loan_id,
                user_id=author_id,
            )
        )
        return comment
