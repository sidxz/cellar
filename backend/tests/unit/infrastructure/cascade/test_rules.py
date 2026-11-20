"""CascadeRule: how a reference is expressed, and what an ambiguous rule gets rejected for."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from cellar.infrastructure.cascade.rules import CascadeAction, CascadeRule, any_id

_child = sa.Table(
    "child",
    sa.MetaData(),
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("parent_id", sa.Uuid),
    sa.Column("kind", sa.String),
)


def test_a_column_rule_binds_any_number_of_ids_as_one_parameter() -> None:
    rule = CascadeRule(
        child_table="child",
        parent_table="parent",
        action=CascadeAction.CASCADE,
        fk_column="parent_id",
    )
    compiled = rule.where(_child, [uuid.uuid4() for _ in range(40_000)]).compile(
        dialect=postgresql.dialect()
    )
    assert "child.parent_id = ANY" in str(compiled)
    assert len(compiled.params) == 1
    assert rule.references == ("child.parent_id",)


def test_a_predicate_rule_uses_its_predicate_and_reports_what_it_covers() -> None:
    def match(table: sa.Table, ids: list[uuid.UUID]) -> sa.ColumnElement[bool]:
        return sa.and_(table.c.kind == "run", any_id(table.c.parent_id, ids))

    rule = CascadeRule(
        child_table="child",
        parent_table="runs",
        action=CascadeAction.CASCADE,
        match=match,
        covers=("child.parent_id",),
    )
    sql = str(rule.where(_child, [uuid.uuid4()]).compile(dialect=postgresql.dialect()))
    assert "child.kind" in sql
    assert rule.references == ("child.parent_id",)


def _first(table: sa.Table, ids: list[uuid.UUID]) -> sa.ColumnElement[bool]:
    return table.c.id == ids[0]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "exactly one of fk_column and match"),
        (
            {"fk_column": "parent_id", "match": _first, "covers": ("child.parent_id",)},
            "exactly one of fk_column and match",
        ),
        ({"match": _first}, "must list what it covers"),
    ],
)
def test_an_ambiguous_rule_is_rejected(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        CascadeRule(
            child_table="child", parent_table="parent", action=CascadeAction.BLOCK, **kwargs
        )


def test_set_null_needs_a_column_to_clear() -> None:
    with pytest.raises(ValueError, match="set_null needs an fk_column"):
        CascadeRule(
            child_table="child",
            parent_table="parent",
            action=CascadeAction.SET_NULL,
            match=_first,
            covers=("child.parent_id",),
        )
