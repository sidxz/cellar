"""Unit tests for the append-only Comment aggregate."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.comment import MAX_COMMENT_BODY, Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.domain.inventory.events import CommentAdded
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
USER = uuid.uuid4()


def _comment(**over) -> Comment:
    kwargs = dict(
        workspace_id=WS,
        target_type=CommentTarget.PLATE_LOAN,
        target_id=uuid.uuid4(),
        body="  0.5 uL taken for NadE screening  ",
        author_id=USER,
        author_name="  Jane Doe ",
    )
    kwargs.update(over)
    return Comment.create(**kwargs)


def test_create_strips_and_emits_event_with_actor() -> None:
    loan = uuid.uuid4()
    c = _comment(loan_id=loan)
    assert c.body == "0.5 uL taken for NadE screening"
    assert c.author_name == "Jane Doe"
    assert c.loan_id == loan
    events = c.collect_events()
    assert len(events) == 1 and isinstance(events[0], CommentAdded)
    assert events[0].user_id == USER
    assert events[0].target_type == CommentTarget.PLATE_LOAN
    assert events[0].aggregate_type == "Comment"


def test_legacy_author_may_have_no_user_id() -> None:
    c = _comment(author_id=None, author_name="Legacy Scientist")
    assert c.author_id is None
    assert c.collect_events()[0].user_id is None


@pytest.mark.parametrize("body", ["", "   ", "x" * (MAX_COMMENT_BODY + 1)])
def test_body_validation(body: str) -> None:
    with pytest.raises(ValidationError):
        _comment(body=body)


@pytest.mark.parametrize("name", ["", "  ", "x" * 201])
def test_author_name_validation(name: str) -> None:
    with pytest.raises(ValidationError):
        _comment(author_name=name)
