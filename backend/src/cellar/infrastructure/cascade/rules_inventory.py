"""Cascade rules for inventory context tables.

Declares what happens to children of Batch, Sample, etc., when those parents
are deleted via Tier-2 admin force-cascade.

Rules are derived from the actual ForeignKey declarations in:
  infrastructure/persistence/sqlalchemy/inventory/models.py
  infrastructure/persistence/sqlalchemy/inventory/shipment_models.py
  infrastructure/persistence/sqlalchemy/inventory/sample_request_models.py

Schema notes / deviations from plan:
- shipment_items.sample_id: plain UUID, no FK constraint declared; rule removed.
- sample_requests: no sample_id FK column at all (fulfilled_sample_id is plain UUID);
  rule for SET_NULL on sample_id removed.
- batches.molecule_id: no ondelete clause but is a FK — CASCADE rule added.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Table, and_, cast, column, exists, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH

from cellar.domain.inventory.enums import SampleRequestStatus, SynthesisRequestStatus
from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule, Match, any_id, any_id_text

_SYNTHESIS_FINISHED = (
    SynthesisRequestStatus.FULFILLED,
    SynthesisRequestStatus.REJECTED,
    SynthesisRequestStatus.CANCELLED,
    SynthesisRequestStatus.FAILED,
)
_SAMPLE_FINISHED = (
    SampleRequestStatus.FULFILLED,
    SampleRequestStatus.REJECTED,
    SampleRequestStatus.CANCELLED,
)


def _requests_for(finished_statuses: Sequence[str], *, finished: bool) -> Match:
    """Requests for the molecules, in (or, for open ones, not in) a finished status.

    "Not finished" is the fail-safe reading: a status added later counts as open.
    """
    values = [str(s) for s in finished_statuses]

    def match(requests: Table, molecule_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        in_state = requests.c.status.in_(values) if finished else requests.c.status.not_in(values)
        return and_(any_id(requests.c.molecule_id, molecule_ids), in_state)

    return match


def _plates_holding_batches(plates: Table, batch_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
    """well_map is {"A1": {"batch_id": "<uuid>", ...}}, or JSON null on legacy plates.

    lax: a null or non-object map yields no rows instead of an error.
    """
    wells = (
        func.jsonb_path_query(plates.c.well_map, cast("lax $.*", JSONPATH))
        .table_valued(column("value", JSONB))
        .render_derived(name="well")
    )
    return exists(
        select(literal(1))
        .select_from(wells)
        .where(any_id_text(wells.c.value["batch_id"].astext, batch_ids))
    )


register_rules(
    # -------------------------------------------------------------------------
    # Batch children — Batch is child of Molecule
    # -------------------------------------------------------------------------
    # BatchModel.molecule_id → molecules.id (no ondelete clause)
    CascadeRule(
        child_table="batches",
        fk_column="molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field="batch_number",
        display_label="Batches",
        recurse_into_entity="batch",
    ),
    # -------------------------------------------------------------------------
    # Sample children — Sample is child of Batch
    # -------------------------------------------------------------------------
    # SampleModel.batch_id → batches.id (no ondelete clause)
    CascadeRule(
        child_table="samples",
        fk_column="batch_id",
        parent_table="batches",
        action=A.CASCADE,
        label_field="barcode",
        display_label="Samples",
        recurse_into_entity="sample",
    ),
    # -------------------------------------------------------------------------
    # Plate group → Collection link (spec 2026-08-26)
    # -------------------------------------------------------------------------
    # PlateGroupModel.collection_id → collections.id (ondelete=SET NULL)
    CascadeRule(
        child_table="plate_groups",
        fk_column="collection_id",
        parent_table="collections",
        action=A.SET_NULL,
        label_field="name",
        display_label="Plate groups (collection link cleared)",
    ),
    # -------------------------------------------------------------------------
    # Plate import template default protocol (no FK)
    # -------------------------------------------------------------------------
    # ImportTemplateModel.default_protocol_id. The template's readout mappings
    # belong to that protocol, so refuse rather than leave a template that
    # imports into nothing. The user deletes the template.
    CascadeRule(
        child_table="import_templates",
        parent_table="protocols",
        action=A.BLOCK,
        fk_column="default_protocol_id",
        label_field="name",
        display_label="Plate import templates defaulting to this protocol",
    ),
    # -------------------------------------------------------------------------
    # Requests for a force-deleted molecule (molecule_id, no FK)
    # -------------------------------------------------------------------------
    # Open requests are live work: refuse, as merge does. Finished ones mean
    # nothing without the compound: remove them.
    CascadeRule(
        child_table="synthesis_requests",
        parent_table="molecules",
        action=A.BLOCK,
        match=_requests_for(_SYNTHESIS_FINISHED, finished=False),
        covers=("synthesis_requests.molecule_id",),
        label_field="purpose",
        display_label="Open synthesis requests (cancel or fulfil them first)",
    ),
    CascadeRule(
        child_table="synthesis_requests",
        parent_table="molecules",
        action=A.CASCADE,
        match=_requests_for(_SYNTHESIS_FINISHED, finished=True),
        covers=("synthesis_requests.molecule_id",),
        label_field="purpose",
        display_label="Finished synthesis requests",
    ),
    CascadeRule(
        child_table="sample_requests",
        parent_table="molecules",
        action=A.BLOCK,
        match=_requests_for(_SAMPLE_FINISHED, finished=False),
        covers=("sample_requests.molecule_id",),
        label_field="purpose",
        display_label="Open sample requests (cancel them first)",
    ),
    CascadeRule(
        child_table="sample_requests",
        parent_table="molecules",
        action=A.CASCADE,
        match=_requests_for(_SAMPLE_FINISHED, finished=True),
        covers=("sample_requests.molecule_id",),
        label_field="purpose",
        display_label="Finished sample requests",
    ),
    # -------------------------------------------------------------------------
    # Batch references without an FK
    # -------------------------------------------------------------------------
    # A physical plate still holds the compound. Removing its batch would also
    # fail every later well edit with "Batch not found".
    CascadeRule(
        child_table="registered_plates",
        parent_table="batches",
        action=A.BLOCK,
        match=_plates_holding_batches,
        covers=("registered_plates.well_map",),
        label_field="barcode",
        display_label="Inventory plates holding these batches",
    ),
    # SampleRequestModel.batch_id: an optional preferred batch.
    CascadeRule(
        child_table="sample_requests",
        parent_table="batches",
        action=A.SET_NULL,
        fk_column="batch_id",
        label_field="purpose",
        display_label="Sample requests (preferred batch cleared)",
    ),
)
