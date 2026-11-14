"""Shared SQL helpers for SQLAlchemy repositories."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ARRAY, BindParameter, ColumnElement, Uuid, any_, bindparam
from sqlalchemy.orm import QueryableAttribute


def uuid_array(ids: Sequence[uuid.UUID]) -> BindParameter[Any]:
    """The ids as one ``uuid[]`` bind parameter.

    ``IN (...)`` binds one parameter per id, and asyncpg refuses a statement
    with more than 32,767 of them. A single HTS protocol has more wells than that.
    """
    return bindparam(None, list(ids), type_=ARRAY(Uuid(as_uuid=True)))


def any_id(
    column: ColumnElement[Any] | QueryableAttribute[Any], ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    """``column = ANY(:ids)``, with the ids bound as one array parameter."""
    return column == any_(uuid_array(ids))


def escape_like(value: str) -> str:
    """Escape SQL LIKE/ILIKE metacharacters so they match literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
