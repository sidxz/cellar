"""Cascade rules for research_organization context tables.

Declares what happens to children of Project, Molecule (cross-context), etc.,
when those parents are deleted via Tier-2 admin force-cascade.

Rules are derived from the actual ForeignKey declarations in:
  infrastructure/persistence/sqlalchemy/research_organization/models.py

Schema notes / deviations from plan:
- Association table is molecule_projects (not project_molecules) — corrected.
- saved_searches has project_id FK to projects (ondelete=SET NULL), not a
  protocol_id FK to protocols as stated in the spec; rule corrected accordingly.
- CollectionMoleculeModel.molecule_id → molecules.id (ondelete=CASCADE) — added.
- CollectionModel.project_id → projects.id (ondelete=SET NULL) — added.
- ProjectMemberModel.project_id → projects.id (ondelete=CASCADE) — added.

Campaign rules (spec 2026-09-15) reference screening data by id without an
FK; they are expressed as match predicates.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Table, and_, cast, column, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH

from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.shared.cascade.actions import CascadeAction as A
from cellar.infrastructure.cascade.registry import register_rules
from cellar.infrastructure.cascade.rules import CascadeRule, Match, any_id, any_id_text, uuid_array
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignChannelModel,
    CampaignMeasurementModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ReadoutDefinitionModel,
)


def _campaigns_with_a_channel_on(
    campaign: Table, protocol_ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    """A channel names the protocol, or one of the protocol's readout definitions."""
    channels = CampaignChannelModel.__table__
    readouts = ReadoutDefinitionModel.__table__
    return exists().where(
        channels.c.campaign_id == campaign.c.id,
        or_(
            any_id(channels.c.protocol_id, protocol_ids),
            channels.c.readout_definition_id.in_(
                select(readouts.c.id).where(any_id(readouts.c.protocol_id, protocol_ids))
            ),
        ),
    )


def _campaigns_citing_runs(*, draft: bool) -> Match:
    """A seed run, or a cell's source or contributing run, is one of the runs."""

    def match(campaign: Table, run_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
        results = CampaignResultModel.__table__
        cells = CampaignMeasurementModel.__table__
        # lax: a non-array value yields no rows instead of an error.
        seeds = (
            func.jsonb_path_query(campaign.c.seed_runs, cast("lax $[*]", JSONPATH))
            .table_valued(column("value", JSONB))
            .render_derived(name="seed")
        )
        seeded = exists(
            select(literal(1))
            .select_from(seeds)
            .where(any_id_text(seeds.c.value["run_id"].astext, run_ids))
        )
        sourced = exists().where(
            results.c.campaign_id == campaign.c.id,
            cells.c.result_id == results.c.id,
            or_(
                any_id(cells.c.source_run_id, run_ids),
                cells.c.contributing_run_ids.overlap(uuid_array(run_ids)),
            ),
        )
        is_draft = campaign.c.status == CampaignStatus.DRAFT.value
        return and_(is_draft if draft else ~is_draft, or_(seeded, sourced))

    return match


def _campaigns_with_a_row_for(
    campaign: Table, molecule_ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    results = CampaignResultModel.__table__
    return exists().where(
        results.c.campaign_id == campaign.c.id,
        any_id(results.c.molecule_id, molecule_ids),
    )


_RUN_CITATIONS = (
    "campaign.seed_runs",
    "campaign_measurement.source_run_id",
    "campaign_measurement.contributing_run_ids",
)

register_rules(
    # -------------------------------------------------------------------------
    # molecule_projects association table (FK on both sides with ondelete=CASCADE)
    # -------------------------------------------------------------------------
    CascadeRule(
        child_table="molecule_projects",
        fk_column="molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Project memberships",
    ),
    CascadeRule(
        child_table="molecule_projects",
        fk_column="project_id",
        parent_table="projects",
        action=A.CASCADE,
        label_field=None,
        display_label="Project-molecule links",
    ),
    # -------------------------------------------------------------------------
    # collection_molecules join table
    # -------------------------------------------------------------------------
    # CollectionMoleculeModel.molecule_id → molecules.id (ondelete=CASCADE)
    CascadeRule(
        child_table="collection_molecules",
        fk_column="molecule_id",
        parent_table="molecules",
        action=A.CASCADE,
        label_field=None,
        display_label="Collection memberships",
    ),
    # CollectionMoleculeModel.collection_id → collections.id (ondelete=CASCADE)
    CascadeRule(
        child_table="collection_molecules",
        fk_column="collection_id",
        parent_table="collections",
        action=A.CASCADE,
        label_field=None,
        display_label="Collection-molecule links",
    ),
    # -------------------------------------------------------------------------
    # Collection parent references
    # -------------------------------------------------------------------------
    # CollectionModel.project_id → projects.id (ondelete=SET NULL)
    CascadeRule(
        child_table="collections",
        fk_column="project_id",
        parent_table="projects",
        action=A.SET_NULL,
        label_field="name",
        display_label="Collections (project scope cleared)",
    ),
    # -------------------------------------------------------------------------
    # Project members
    # -------------------------------------------------------------------------
    # ProjectMemberModel.project_id → projects.id (ondelete=CASCADE)
    CascadeRule(
        child_table="project_members",
        fk_column="project_id",
        parent_table="projects",
        action=A.CASCADE,
        label_field=None,
        display_label="Project members",
    ),
    # -------------------------------------------------------------------------
    # Saved searches — scoped to a project (SET NULL on project delete)
    # -------------------------------------------------------------------------
    # SavedSearchModel.project_id → projects.id (ondelete=SET NULL)
    # Note: spec listed protocol_id FK which does not exist; actual FK is project_id.
    CascadeRule(
        child_table="saved_searches",
        fk_column="project_id",
        parent_table="projects",
        action=A.SET_NULL,
        label_field="name",
        display_label="Saved searches (project scope cleared)",
    ),
    # -------------------------------------------------------------------------
    # Campaigns citing force-deleted screening data (ids without an FK)
    # -------------------------------------------------------------------------
    # A channel names its protocol and readout by id. Block in every state: a
    # draft's user can delete the channel; a closed campaign must be reopened.
    CascadeRule(
        child_table="campaign",
        parent_table="protocols",
        action=A.BLOCK,
        match=_campaigns_with_a_channel_on,
        covers=("campaign_channel.protocol_id", "campaign_channel.readout_definition_id"),
        label_field="name",
        display_label="Campaigns with a channel on this protocol",
    ),
    # Closed and superseded campaigns are frozen results. Their row-lock
    # triggers would also reject any change inside the delete.
    CascadeRule(
        child_table="campaign",
        parent_table="runs",
        action=A.BLOCK,
        match=_campaigns_citing_runs(draft=False),
        covers=_RUN_CITATIONS,
        label_field="name",
        display_label="Closed or superseded campaigns citing this run",
    ),
    # A draft re-resolves without the run on its next refresh, and no operation
    # removes a seed run, so warn rather than block. Never prune: dropping a
    # protocol's last seed run would widen its channels to every run.
    CascadeRule(
        child_table="campaign",
        parent_table="runs",
        action=A.WARN,
        match=_campaigns_citing_runs(draft=True),
        covers=_RUN_CITATIONS,
        label_field="name",
        display_label=(
            "Draft campaigns using this run "
            "(their cells re-resolve without it on the next refresh)"
        ),
    ),
    # A result row is the molecule. Block in every state: a draft's user can
    # remove the row; a closed campaign must be reopened.
    CascadeRule(
        child_table="campaign",
        parent_table="molecules",
        action=A.BLOCK,
        match=_campaigns_with_a_row_for,
        covers=("campaign_result.molecule_id",),
        label_field="name",
        display_label="Campaigns with a row for this molecule",
    ),
)
