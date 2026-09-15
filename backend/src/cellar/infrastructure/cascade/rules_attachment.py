"""Cascade rules for file attachments.

``attachments`` points at its owner polymorphically (attachable_type,
attachable_id) with no FK. Rows go with a force-deleted owner. The stored
files stay: each row's audit snapshot keeps its storage_key.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Table, and_

from cellar.domain.attachment.enums import AttachableType
from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule, Match, any_id


def _owned_by(kind: AttachableType) -> Match:
    def match(attachments: Table, owner_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        return and_(
            attachments.c.attachable_type == kind.value,
            any_id(attachments.c.attachable_id, owner_ids),
        )

    return match


def _attachments_of(kind: AttachableType, parent_table: str) -> CascadeRule:
    return CascadeRule(
        child_table="attachments",
        parent_table=parent_table,
        action=A.CASCADE,
        match=_owned_by(kind),
        covers=("attachments.attachable_id",),
        label_field="file_name",
        display_label="Attachments (files stay in storage)",
    )


register_rules(
    _attachments_of(AttachableType.PROTOCOL, "protocols"),
    _attachments_of(AttachableType.RUN, "runs"),
    _attachments_of(AttachableType.MOLECULE, "molecules"),
    _attachments_of(AttachableType.BATCH, "batches"),
)
