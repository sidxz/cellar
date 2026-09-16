"""CascadeRule: one reference from a child table to a parent row.

A reference is either a plain column holding the parent id (``fk_column``,
with or without an FK constraint) or, where a column can't express it, a SQL
predicate (``match``). Predicates cover ids inside JSON or arrays, polymorphic
links, and conditions on the child's state. This is a persistence concept, so
it lives in infrastructure: renaming a table only touches rule files.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    ARRAY,
    BindParameter,
    ColumnElement,
    String,
    Table,
    Uuid,
    any_,
    bindparam,
    func,
)

from cellar.domain.shared.cascade.actions import CascadeAction  # re-export for convenience

__all__ = ["CascadeAction", "CascadeRule", "Match", "any_id", "any_id_text", "uuid_array"]

Match = Callable[[Table, Sequence[uuid.UUID]], ColumnElement[bool]]


def uuid_array(ids: Sequence[uuid.UUID]) -> BindParameter[Any]:
    """The ids as one ``uuid[]`` bind parameter.

    ``IN (...)`` binds one parameter per id, and asyncpg refuses a statement
    with more than 32,767 of them. A single HTS protocol has more wells than that.
    """
    return bindparam(None, list(ids), type_=ARRAY(Uuid(as_uuid=True)))


def any_id(column: ColumnElement[Any], ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
    """``column = ANY(:ids)``, with the ids bound as one array parameter."""
    return column == any_(uuid_array(ids))


def any_id_text(expr: ColumnElement[Any], ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
    """``any_id`` for ids stored as JSON strings.

    Compares as text, so a malformed value inside the JSON can't fail the
    whole statement on a uuid cast. Compares case-insensitively, since JSON
    writers aren't guaranteed to write the lowercase hex ``str(uuid)`` form.
    """
    return func.lower(expr) == any_(bindparam(None, [str(i) for i in ids], type_=ARRAY(String())))


@dataclass(frozen=True)
class CascadeRule:
    """Rows of ``child_table`` that reference a ``parent_table`` row get ``action``
    when that parent is deleted.

    Owned by the module whose table holds the reference. Exactly one of
    ``fk_column`` (a column on ``child_table``) and ``match`` (a predicate) says
    how rows reference the parent. A ``match`` rule lists the ``"table.column"``
    references it accounts for in ``covers``, so the coverage test can see them.
    """

    child_table: str
    parent_table: str
    action: CascadeAction
    fk_column: str | None = None
    match: Match | None = None
    covers: tuple[str, ...] = ()
    label_field: str | None = None  # column on child_table used for named samples
    display_label: str = ""  # group label in previews and refusals, e.g. "Runs"
    recurse_into_entity: str | None = None  # also walk the child's own rules

    def __post_init__(self) -> None:
        if (self.fk_column is None) == (self.match is None):
            raise ValueError(f"{self.child_table}: set exactly one of fk_column and match")
        if self.match is not None and not self.covers:
            raise ValueError(f"{self.child_table}: a match rule must list what it covers")
        if self.action == CascadeAction.SET_NULL and self.fk_column is None:
            raise ValueError(f"{self.child_table}: set_null needs an fk_column to clear")

    def where(self, table: Table, parent_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        """Rows of ``table`` (this rule's child table) that reference any of ``parent_ids``."""
        if self.fk_column is not None:
            return any_id(table.c[self.fk_column], parent_ids)
        assert self.match is not None
        return self.match(table, parent_ids)

    @property
    def references(self) -> tuple[str, ...]:
        """The ``"table.column"`` references this rule accounts for."""
        if self.fk_column is not None:
            return (f"{self.child_table}.{self.fk_column}",)
        return self.covers
