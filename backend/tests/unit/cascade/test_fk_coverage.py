"""CI-enforced FK coverage check.

Asserts that every inbound FK referencing a Tier-1 or Tier-2 admin entity
is either picked up by Tier-1 introspection (which is automatic — it walks
all FKs) or has a registered CascadeRule (Tier-2). Listed in IGNORED_FKS
are FKs that legitimately should not be cascaded or surfaced.

This test enforces: when a developer adds a new FK to the schema, they
either (a) accept the default Tier-1 RESTRICT behavior (no action needed
if parent is Tier-1-deletable), or (b) declare a Tier-2 cascade rule, or
(c) explicitly add it to IGNORED_FKS with a justifying comment.
"""

import importlib
import pkgutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import ARRAY, JSON, Uuid

import cellar.infrastructure.persistence.sqlalchemy as _persistence
from cellar.application.admin.tier2_entities import TIER2_ENTITY_TYPES
from cellar.domain.shared.cascade.actions import CascadeAction
from cellar.infrastructure.cascade.label_fields import table_for_entity_type
from cellar.infrastructure.cascade.registry import (
    _clear_for_test as _clear_cascade_registry,
)
from cellar.infrastructure.cascade.registry import (
    all_rules,
    get_rules_for_parent,
)
from cellar.infrastructure.persistence.sqlalchemy.base import Base

# Import every persistence module so Base.metadata holds every table. A hand-kept
# list lets a new model's columns escape the checks below.
for _module in pkgutil.walk_packages(_persistence.__path__, _persistence.__name__ + "."):
    importlib.import_module(_module.name)

# ---------------------------------------------------------------------------
# Cascade module names.  Imported and unloaded within the test so that:
#   (a) register_rules() re-executes even if a prior test cleared the registry,
#   (b) the cascade modules are evicted from sys.modules after our test so
#       subsequent tests that rely on a fresh first-import still get one.
# ---------------------------------------------------------------------------
_CASCADE_MODULES = [
    "cellar.infrastructure.cascade.rules_audit_compliance",
    "cellar.infrastructure.cascade.rules_chemical_registration",
    "cellar.infrastructure.cascade.rules_inventory",
    "cellar.infrastructure.cascade.rules_research_organization",
    "cellar.infrastructure.cascade.rules_screening_assay",
    "cellar.infrastructure.cascade.rules_attachment",
]


@contextmanager
def _rules_loaded() -> Iterator[None]:
    """Register every rule module fresh; afterwards evict them and clear the registry.

    Eviction lets later tests that import a rule module get a fresh
    registration instead of a cached no-op.
    """
    _clear_cascade_registry()
    for name in _CASCADE_MODULES:
        sys.modules.pop(name, None)
    for name in _CASCADE_MODULES:
        importlib.import_module(name)
    try:
        yield
    finally:
        _clear_cascade_registry()
        for name in _CASCADE_MODULES:
            sys.modules.pop(name, None)


# (child_table, fk_column, parent_table) — explicitly ignored.
IGNORED_FKS: set[tuple[str, str, str]] = {
    # -------------------------------------------------------------------------
    # Audit context — append-only, must survive entity deletion (21 CFR Part 11)
    # -------------------------------------------------------------------------
    # audit_operations.correlation_id is a self-referential FK for operation
    # grouping; the parent operation survives independently.
    ("audit_operations", "correlation_id", "audit_operations"),
    # audit_entries and electronic_signatures reference audit_operations which is
    # append-only and never admin-deleted; cascade handled by ORM relationship.
    ("audit_entries", "operation_id", "audit_operations"),
    ("electronic_signatures", "operation_id", "audit_operations"),
    # -------------------------------------------------------------------------
    # Organizations — referenced as provenance (no admin delete cascade needed)
    # -------------------------------------------------------------------------
    # cdd_molecule_imports.originating_org_id is import provenance metadata;
    # deleting an org doesn't require cascading import records.
    ("cdd_molecule_imports", "originating_org_id", "organizations"),
    # collections.organization_id is a loose scope reference (SET NULL in schema);
    # the FK is to organizations which is a Tier-1 entity — RESTRICT surfaces it.
    # The cascade rule is declared in research_organization/cascade.py (SET_NULL).
    # No additional categorization needed — covered by Tier-2 rule.
    # -------------------------------------------------------------------------
    # Storage hierarchy — self-referential; storage_locations is not admin-deletable
    # -------------------------------------------------------------------------
    # storage_locations.parent_id is a self-referential FK for the storage hierarchy.
    # Admins manage storage via the inventory UI, not the admin-delete pathway.
    ("storage_locations", "parent_id", "storage_locations"),
    # -------------------------------------------------------------------------
    # Registered plates — self-referential for daughter-plate tracking
    # -------------------------------------------------------------------------
    # registered_plates.parent_plate_id links daughter plates to parent plates.
    # registered_plates is not a Tier-1 admin-deletable entity; plate lifecycle
    # is managed via the inventory module.
    ("registered_plates", "parent_plate_id", "registered_plates"),
    # -------------------------------------------------------------------------
    # Samples → storage_locations: loose location reference, not cascade-deleted
    # -------------------------------------------------------------------------
    # samples.location_id is a nullable storage location reference. Deleting a
    # storage location does not delete the samples within it; samples are
    # reassigned or manually managed. Not a Tier-1 delete path.
    ("samples", "location_id", "storage_locations"),
    # -------------------------------------------------------------------------
    # registered_plates → storage_locations: same rationale
    # -------------------------------------------------------------------------
    ("registered_plates", "storage_location_id", "storage_locations"),
    # -------------------------------------------------------------------------
    # plate_groups → storage_locations: SET NULL by design (migration 067)
    # -------------------------------------------------------------------------
    # plate_groups.storage_location_id is a nullable loose location reference,
    # ondelete=SET NULL. A deleted location just un-places the group; nothing
    # to cascade — same rationale as the samples.location_id and
    # registered_plates.storage_location_id entries above.
    ("plate_groups", "storage_location_id", "storage_locations"),
    # -------------------------------------------------------------------------
    # Plate groups — org-owned hierarchy (migration 062); same rationale as
    # storage_locations/registered_plates self-refs above
    # -------------------------------------------------------------------------
    # plate_groups.parent_group_id is a self-referential FK for the group
    # hierarchy (ondelete=RESTRICT — deleting a group with children fails at
    # the DB level and is surfaced by the delete-group use case, not silently
    # bypassed). plate_groups is not a Tier-1 admin-deletable entity; lifecycle
    # is managed via the inventory module, same as storage_locations.parent_id
    # and registered_plates.parent_plate_id above.
    ("plate_groups", "parent_group_id", "plate_groups"),
    # registered_plates.group_id is a nullable plate-to-group membership
    # reference (ondelete=SET NULL). Deleting a group does not delete its
    # plates — the DB clears the reference automatically, same rationale as
    # the storage_locations loose-reference entries above.
    ("registered_plates", "group_id", "plate_groups"),
    # -------------------------------------------------------------------------
    # custom_field_definitions → controlled_vocabularies: SET NULL on delete
    # -------------------------------------------------------------------------
    # custom_field_definitions.vocabulary_id is nullable; if the vocabulary is
    # deleted the field definition remains with vocabulary_id set to NULL.
    # This is a Tier-1 RESTRICT scenario (controlled_vocabularies is Tier-1),
    # but the ondelete=SET NULL means it shouldn't block deletion.
    # Documented here so the intent is explicit.
    ("custom_field_definitions", "vocabulary_id", "controlled_vocabularies"),
    # -------------------------------------------------------------------------
    # bulk_registration_items → bulk_registrations: owned, ORM cascade handles it
    # -------------------------------------------------------------------------
    # This FK has ondelete=CASCADE at the DB level and the ORM relationship has
    # cascade="all, delete-orphan". Tier-1 RESTRICT surfaces it; the DB engine
    # will cascade automatically. No Tier-2 rule needed.
    ("bulk_registration_items", "bulk_registration_id", "bulk_registrations"),
    # -------------------------------------------------------------------------
    # protocol_projects → projects: join table, cascade handled by Tier-2 rule
    # -------------------------------------------------------------------------
    # protocol_projects.project_id → projects is the projects side of the
    # protocol_projects association table. The projects side is covered by
    # Tier-2 cascade rules; the protocol side is covered by screening_assay/cascade.py.
    # The FK to projects goes via the protocol_projects join table — Tier-1 will
    # surface it as a RESTRICT blocker when deleting a project. No additional
    # Tier-2 rule needed because the Tier-1 introspection already picks it up.
    ("protocol_projects", "project_id", "projects"),
    # -------------------------------------------------------------------------
    # shipment_items → shipments: owned, ORM + DB cascade handles it
    # -------------------------------------------------------------------------
    # shipment_items.shipment_id has ondelete=CASCADE at the DB level.
    # Shipments are not a Tier-1 admin-deletable entity; lifecycle managed by
    # the inventory module. No cascade rule needed.
    ("shipment_items", "shipment_id", "shipments"),
    # -------------------------------------------------------------------------
    # plate_loan_items → plate_loans: owned, ORM + DB cascade handles it
    # -------------------------------------------------------------------------
    # plate_loan_items.loan_id has ondelete=CASCADE at the DB level (migration
    # 063, fk_loan_items_loan) and cascade="all, delete-orphan" on the ORM
    # relationship. plate_loans is not a Tier-1 admin-deletable entity;
    # lifecycle is managed via the loan use cases, not the admin-delete
    # pathway — same rationale as shipment_items.shipment_id above. No Tier-2
    # rule needed — the DB engine cascades automatically.
    #
    # plate_loan_items.plate_id is deliberately NOT a declared FK (loose
    # reference to registered_plates, migration 063) — loan history must
    # survive plate deletion. With no FK declared it never appears in
    # _collect_all_fks(), so there is nothing to categorize for it.
    ("plate_loan_items", "loan_id", "plate_loans"),
    # SET NULL by design — a deleted loan detaches its comments
    ("plate_comments", "loan_id", "plate_loans"),
    # SET NULL by design — a deleted loan detaches the shipments that carried it
    # (migration 071); the shipment record itself survives.
    ("shipments", "loan_id", "plate_loans"),
    # -------------------------------------------------------------------------
    # batches → salt_catalog: SET NULL on salt entry delete
    # -------------------------------------------------------------------------
    # batches.salt_entry_id is nullable (ondelete=SET NULL). The salt catalog
    # is a Tier-1 admin entity; RESTRICT will surface this as a blocker.
    # Documented here: the FK has SET NULL semantics so deleting a salt entry
    # should null-out the reference, not block or cascade-delete the batch.
    ("batches", "salt_entry_id", "salt_catalog"),
    # -------------------------------------------------------------------------
    # collections → organizations: SET NULL on org delete (research org context)
    # -------------------------------------------------------------------------
    # Already covered by a Tier-2 SET_NULL cascade rule in research_organization/cascade.py.
    # Listed here to document that the FK to organizations is intentional.
    # -------------------------------------------------------------------------
    # molecules → organizations: provenance, not cascade-deletable via org delete
    # -------------------------------------------------------------------------
    # molecules.originating_org_id is the organization that registered the molecule
    # (provenance/attribution). Deleting an organization should not cascade-delete
    # all molecules it registered — that would be catastrophic data loss.
    # Organizations are reference entities; admin deletion is rare and requires
    # manual molecule reassignment beforehand.
    ("molecules", "originating_org_id", "organizations"),
    # -------------------------------------------------------------------------
    # collections → organizations (owned_by_org_id): SET NULL on org delete
    # -------------------------------------------------------------------------
    # collections.owned_by_org_id is a nullable org ownership reference
    # (ondelete=SET NULL). If the org is deleted the collection's org link is
    # cleared automatically by the DB; no cascade rule needed.
    ("collections", "owned_by_org_id", "organizations"),
    # -------------------------------------------------------------------------
    # Campaign aggregate — owned children, ORM + DB cascade handles them
    # -------------------------------------------------------------------------
    # campaign_channel.campaign_id, campaign_result.campaign_id,
    # campaign_measurement.result_id, campaign_measurement.channel_id all have
    # ondelete=CASCADE at the DB level and cascade="all, delete-orphan" on the
    # ORM relationships. Campaigns are aggregate roots whose lifecycle is
    # managed via the campaign use cases, not the Tier-1 admin-delete pathway.
    # No additional categorization needed — the DB engine cascades automatically.
    ("campaign_channel", "campaign_id", "campaign"),
    ("campaign_result", "campaign_id", "campaign"),
    ("campaign_measurement", "result_id", "campaign_result"),
    ("campaign_measurement", "channel_id", "campaign_channel"),
    # campaign_stage.campaign_id and campaign_stage_override.result_id /
    # .stage_id (migration 074) are the same owned-children shape — ondelete=
    # CASCADE at the DB level, cascade="all, delete-orphan" on the ORM
    # relationships (CampaignModel.stages, CampaignResultModel.stage_overrides).
    ("campaign_stage", "campaign_id", "campaign"),
    ("campaign_stage_override", "result_id", "campaign_result"),
    ("campaign_stage_override", "stage_id", "campaign_stage"),
    # campaign_stage.parent_stage_id is a self-referential FK for the stage
    # forest (ondelete=RESTRICT — deleting a stage with children fails at the
    # DB level; Campaign.remove_stage already guards this in the domain
    # layer). campaign_stage is not a Tier-1 admin-deletable entity; same
    # rationale as plate_groups.parent_group_id / storage_locations.parent_id
    # self-refs above.
    ("campaign_stage", "parent_stage_id", "campaign_stage"),
    # -------------------------------------------------------------------------
    # batch_identifiers → molecule_identifiers: auto-mirror cascade on synonym removal
    # -------------------------------------------------------------------------
    # batch_identifiers.derived_from_molecule_identifier_id is a nullable FK to
    # molecule_identifiers with ondelete=CASCADE. When a molecule synonym
    # (MoleculeIdentifier) is deleted, the DB engine automatically cascades the
    # delete to all derived batch identifier mirrors that reference it. This is
    # intentional — mirror rows should not outlive their parent synonym.
    # molecule_identifiers is not a Tier-1 admin-deletable entity (it's a child
    # of molecules); removal happens through the RemoveIdentifier use case.
    # No Tier-2 rule or TIER1_PARENT_TABLE registration needed — the DB CASCADE
    # ondelete clause handles this automatically.
    ("batch_identifiers", "derived_from_molecule_identifier_id", "molecule_identifiers"),
    # -------------------------------------------------------------------------
    # Target link tables → targets: RESTRICT blocks deleting an in-use target
    # -------------------------------------------------------------------------
    # protocol_targets / run_targets have ondelete=RESTRICT on target_id ->
    # targets (migration 053): a referenced target cannot be deleted, so links
    # are never silently stripped. Moot in practice — targets are a read-only
    # mirror of prot-cellar and are never deleted locally (see sync_targets).
    # `targets` is a reference entity, not a Tier-1 admin-deletable aggregate.
    # The protocol_id/run_id owner sides are ondelete=CASCADE: deleting a
    # protocol/run drops its own link rows at the DB engine, which is
    # intentional for pure association rows.
    ("protocol_targets", "target_id", "targets"),
    ("run_targets", "target_id", "targets"),
    # -------------------------------------------------------------------------
    # Tag link tables → tags: DB CASCADE clears links on tag delete
    # -------------------------------------------------------------------------
    # The per-entity tag link tables (molecule_tags, protocol_tags, project_tags,
    # collection_tags, run_tags, campaign_tags, batch_tags, registered_plate_tags)
    # have ondelete=CASCADE on tag_id -> tags.
    # `tags` is not a Tier-1 admin-deletable entity; tags are deleted via the
    # tagging admin use cases (Phase 4) and the DB engine cascades the delete to
    # the link rows automatically (verified by test_cascade_on_tag_delete). The
    # <entity>_id side of each link table points at a Tier-1 parent
    # (molecules/protocols/projects/collections/runs/batches) and is covered by
    # Tier-1 RESTRICT; the two non-Tier-1 entity sides (campaign, registered
    # plates) are categorized separately below.
    ("molecule_tags", "tag_id", "tags"),
    ("protocol_tags", "tag_id", "tags"),
    ("project_tags", "tag_id", "tags"),
    ("collection_tags", "tag_id", "tags"),
    ("run_tags", "tag_id", "tags"),
    ("campaign_tags", "tag_id", "tags"),
    ("batch_tags", "tag_id", "tags"),
    ("registered_plate_tags", "tag_id", "tags"),
    # -------------------------------------------------------------------------
    # Tag link tables → non-Tier-1 entity parents: DB CASCADE on entity delete
    # -------------------------------------------------------------------------
    # campaign_tags.campaign_id has ondelete=CASCADE — campaigns are aggregate
    # roots whose lifecycle is managed via the campaign use cases, not the
    # Tier-1 admin-delete pathway (same rationale as the campaign children
    # block above); deleting a campaign clears its tag links automatically.
    ("campaign_tags", "campaign_id", "campaign"),
    # campaign_collections.campaign_id (migration 080) is the same shape —
    # ondelete=CASCADE, so deleting a campaign drops the links to the
    # libraries it screened. The other side, campaign_collections.collection_id,
    # is deliberately RESTRICT and needs no entry: collections IS Tier-1, so a
    # library a campaign points at is blocked from deletion (as with
    # run_collections).
    ("campaign_collections", "campaign_id", "campaign"),
    # registered_plate_tags.registered_plate_id has ondelete=CASCADE —
    # registered_plates is not a Tier-1 admin-deletable entity; plate lifecycle
    # is managed via the inventory module (same rationale as the
    # registered_plates self-ref block above); deleting a plate clears its tag
    # links automatically.
    ("registered_plate_tags", "registered_plate_id", "registered_plates"),
    # -------------------------------------------------------------------------
    # SAR async-job result tables → their run/projection parent: DB CASCADE
    # -------------------------------------------------------------------------
    # rgroup_assignments.run_id and sar_activity_values.projection_id have
    # ondelete=CASCADE at the DB level (migrations 057/058). The parents are
    # AsyncJob-owned result aggregates, not Tier-1 admin-deletable entities;
    # deleting a run/projection clears its rows automatically — same rationale
    # as the campaign_* block above.
    ("rgroup_assignments", "run_id", "rgroup_decomposition_runs"),
    ("sar_activity_values", "projection_id", "sar_activity_projections"),
}


def _collect_all_fks() -> set[tuple[str, str, str]]:
    fks: set[tuple[str, str, str]] = set()
    for table in Base.metadata.tables.values():
        for col in table.columns:
            for fk in col.foreign_keys:
                parent = fk.target_fullname.split(".")[0]
                fks.add((table.name, col.name, parent))
    return fks


def _collect_tier2_rule_keys() -> set[tuple[str, str, str]]:
    return {(r.child_table, r.fk_column, r.parent_table) for r in all_rules()}


# DB-level ondelete clauses that resolve the FK at delete time.
# RESTRICT and NO ACTION still raise FK violations, so they don't count.
_DB_ONDELETE_HANDLERS = {"CASCADE", "SET NULL", "SET DEFAULT"}


def _has_db_ondelete_handling(child_table: str, fk_col: str) -> bool:
    """True if the FK column has a DB ondelete clause that resolves the FK
    automatically when the parent row is deleted.
    """
    table = Base.metadata.tables[child_table]
    col = table.c[fk_col]
    for fk in col.foreign_keys:
        if fk.ondelete and fk.ondelete.upper() in _DB_ONDELETE_HANDLERS:
            return True
    return False


# Tier-1 admin-deletable parent tables — RESTRICT will surface their inbound FKs.
TIER1_PARENT_TABLES = {
    "controlled_vocabularies",
    "registration_forms",
    "protocol_forms",
    "salt_catalog",
    "ontology_slot_definitions",
    "custom_field_definitions",
    "data_sources",
    "external_api_keys",
    "compound_flags",
    "molecule_relationships",
    "synthesis_routes",
    "molecules",
    "protocols",
    "runs",
    "plate_templates",
    "run_import_templates",
    "batches",
    "samples",
    "shipments",
    "synthesis_requests",
    "projects",
    "collections",
    "saved_searches",
    # Additional Tier-1 entities referenced by FKs in the schema
    "bulk_registrations",
    "bulk_disclosures",
    "readout_definitions",
    "plates",
}


def test_every_fk_is_categorized():
    with _rules_loaded():
        all_fks = _collect_all_fks()
        tier2_keys = _collect_tier2_rule_keys()

    uncovered: list[tuple[str, str, str]] = []
    unsafe_self_refs: list[tuple[str, str, str]] = []
    for fk in all_fks:
        child_table, fk_col, parent_table = fk

        # Self-refs in Tier-1 tables are a structural blind spot for the
        # generic "Tier-1 RESTRICT will handle it" shortcut:
        #   1. The Tier-1 RESTRICT walk in inbound_refs.find_inbound_references
        #      explicitly skips the parent table itself, so a self-ref is
        #      never surfaced as a blocker at the entry point.
        #   2. Inside a Tier-2 cascade, multiple rows of the same Tier-1 table
        #      can be deleted in one shot (e.g. a versioning chain), or a
        #      successor row can point at the row being deleted — both raise
        #      a FK violation at DELETE time.
        # Either case requires explicit handling: a Tier-2 cascade rule
        # (typically SET_NULL for lineage links) or a DB-level ondelete
        # clause that resolves the FK automatically. IGNORED_FKS does NOT
        # bypass this — silent ignore is exactly the bug pattern that sent
        # protocol cascade-deletes into ForeignKeyViolationError.
        if child_table == parent_table and parent_table in TIER1_PARENT_TABLES:
            if fk in tier2_keys:
                continue
            if _has_db_ondelete_handling(child_table, fk_col):
                continue
            unsafe_self_refs.append(fk)
            continue

        if fk in IGNORED_FKS:
            continue
        if parent_table in TIER1_PARENT_TABLES:
            continue  # Tier-1 RESTRICT will handle it
        if fk in tier2_keys:
            continue  # Tier-2 rule covers it
        uncovered.append(fk)

    assert not unsafe_self_refs, (
        "Self-referential FKs in Tier-1 tables MUST have explicit delete-time "
        "handling.\n"
        "Tier-1 RESTRICT walking explicitly skips the parent table (so it never "
        "surfaces self-refs as blockers), and Tier-2 cascade can delete multiple "
        "rows of the same table together — both paths hit the FK at DELETE time. "
        "Add a Tier-2 cascade rule (SET_NULL is typical for lineage links) or a "
        "DB-level ondelete clause (CASCADE / SET NULL / SET DEFAULT). "
        "IGNORED_FKS does NOT bypass this check.\n\n"
        + "\n".join(f"  {ct}.{c} -> {pt}" for ct, c, pt in unsafe_self_refs)
    )

    assert not uncovered, (
        "FKs not covered by Tier-1 RESTRICT or Tier-2 cascade rules:\n"
        + "\n".join(f"  {ct}.{c} -> {pt}" for ct, c, pt in uncovered)
        + "\n\nResolution: either register a CascadeRule, add the parent table "
        "to TIER1_PARENT_TABLES, or add to IGNORED_FKS with a justifying comment."
    )


# ---------------------------------------------------------------------------
# Id-only references: every uuid column without an FK, and every JSON column,
# says what a force delete does to it: a rule covers it, or it is listed here
# with the reason dangling is acceptable.
# ---------------------------------------------------------------------------

_NOT_REFERENCES = {"id", "workspace_id", "created_by", "updated_by"}

_USER = "Duar user id, not a Cellar row"
_ORG = "organization id; organizations are never force-deleted"
_AUDIT = "append-only audit trail; it must outlive what it describes"
_NO_IDS = "JSON holding no Cellar ids (values, settings, labels)"
_BY_NAME = "JSON naming definitions by name, not id"
_SNAPSHOT = "snapshot carrying its own labels"
_HISTORY = "record of what happened; the id stays as provenance"
_NEVER_WRITTEN = "never written"
_MEMBERSHIP_CACHE = "cache keyed on membership; misses and recomputes once members change"
_SAR_PROJECTION = (
    "SAR projection cache; its staleness is "
    "docs/backlog/sar-activity-projection-cache-no-data-version.md"
)
_FILTER = "a filter on a missing id matches nothing; pruning it would widen results"
_TIER1_ONLY = "parent is Tier-1 only; see docs/backlog/tier1-only-parents-id-references.md"

LEFT_ALONE: dict[str, str] = {
    "attachments.uploaded_by": _USER,
    "audit_operations.user_id": _USER,
    "batch_identifiers.registered_by": _USER,
    "batch_tags.assigned_by": _USER,
    "batches.chemist": _USER,
    "bulk_disclosures.submitted_by": _USER,
    "bulk_registrations.submitted_by": _USER,
    "campaign.closed_by": _USER,
    "campaign_stage_override.overridden_by": _USER,
    "campaign_tags.assigned_by": _USER,
    "cdd_molecule_imports.submitted_by": _USER,
    "cdd_plate_imports.submitted_by": _USER,
    "collection_tags.assigned_by": _USER,
    "compound_flags.flagged_by": _USER,
    "disclosure_requests.requested_by": _USER,
    "electronic_signatures.user_id": _USER,
    "export_jobs.requested_by": _USER,
    "favorites.user_id": _USER,
    "merge_events.merged_by": _USER,
    "molecule_identifiers.registered_by": _USER,
    "molecule_tags.assigned_by": _USER,
    "molecules.disclosed_by": _USER,
    "plate_comments.author_id": _USER,
    "plate_loans.approved_by": _USER,
    "plate_loans.requested_by": _USER,
    "project_members.user_id": _USER,
    "project_tags.assigned_by": _USER,
    "projects.archived_by": _USER,
    "protocol_tags.assigned_by": _USER,
    "protocols.locked_by": _USER,
    "registered_plate_tags.assigned_by": _USER,
    "registered_plates.registered_by": _USER,
    "rgroup_decomposition_runs.requested_by": _USER,
    "run_tags.assigned_by": _USER,
    "runs.hit_criteria_set_by": _USER,
    "runs.locked_by": _USER,
    "runs.operator": _USER,
    "sample_requests.assigned_to": _USER,
    "sample_requests.requester_id": _USER,
    "sar_activity_projections.requested_by": _USER,
    "scaffold_tree_jobs.requested_by": _USER,
    "shipments.sender_id": _USER,
    "synthesis_requests.approved_by": _USER,
    "synthesis_requests.assigned_to": _USER,
    "synthesis_requests.requester_id": _USER,
    "umap_jobs.requested_by": _USER,
    "user_preferences.user_id": _USER,
    "batches.supplier_org_id": _ORG,
    "bulk_disclosures.partner_org_id": _ORG,
    "disclosure_requests.disclosing_org_id": _ORG,
    "kiosk_devices.org_id": _ORG,
    "org_plate_policies.org_id": _ORG,
    "plate_groups.owner_org_id": _ORG,
    "plate_loans.borrower_org_id": _ORG,
    "plate_loans.owner_org_id": _ORG,
    "registered_plates.owner_org_id": _ORG,
    "runs.performed_at_org_id": _ORG,
    "shipments.destination_org_id": _ORG,
    "synthesis_requests.assigned_org_id": _ORG,
    "audit_entries.entity_id": _AUDIT,
    "audit_operations.entity_id": _AUDIT,
    "batches.custom_fields": _NO_IDS,
    "campaign_channel.intercept_key": _NO_IDS,
    "campaign_channel.qc_filter": _NO_IDS,
    "cdd_molecule_imports.filter_criteria": _NO_IDS,
    "collection_import_templates.column_mapping": _NO_IDS,
    "condition_definitions.pick_list_values": _NO_IDS,
    "custom_field_definitions.default_value": _NO_IDS,
    "custom_field_definitions.pick_list_values": _NO_IDS,
    "data_sources.config": _NO_IDS,
    "data_sources.entity_mappings": _NO_IDS,
    "dose_response_curves.excluded_points": _NO_IDS,
    "dose_response_curves.fit_quality_warnings": _NO_IDS,
    "dose_response_curves.intercept_values": _NO_IDS,
    "dose_response_curves.raw_data": _NO_IDS,
    "molecules.custom_fields": _NO_IDS,
    "ontology_slot_definitions.ontology_sources": _NO_IDS,
    "plate_templates.template_map": _NO_IDS,
    "plates.plate_map": _NO_IDS,
    "protocol_forms.condition_templates": _NO_IDS,
    "protocol_forms.ontology_defaults": _NO_IDS,
    "protocol_forms.readout_templates": _NO_IDS,
    "protocols.fingerprint": _NO_IDS,
    "reaction_steps.condition_additional": _NO_IDS,
    "readout_definitions.pick_list_values": _NO_IDS,
    "rgroup_assignments.rgroups": _NO_IDS,
    "rgroup_decomposition_runs.rgroup_labels": _NO_IDS,
    "umap_jobs.picker_params": _NO_IDS,
    "user_preferences.preferences": _NO_IDS,
    "workspace_settings.audit_reason_policy": _NO_IDS,
    "workspace_settings.custom_field_definitions": _NO_IDS,
    "workspace_settings.formulation_number_scheme": _NO_IDS,
    "workspace_settings.registration_rules": _NO_IDS,
    "dose_response_curves.dose_response_config_snapshot": _BY_NAME,
    "protocols.ontology_annotations": _BY_NAME,
    "protocols.recommended_hit_criteria": _BY_NAME,
    "readout_definitions.dose_response_config": _BY_NAME,
    "readout_definitions.normalizations": _BY_NAME,
    "run_import_templates.column_mapping": _BY_NAME,
    "runs.conditions": _BY_NAME,
    "runs.hit_criteria": _BY_NAME,
    "campaign.source_protocols": _SNAPSHOT,
    "campaign_measurement.curve_snapshot": _SNAPSHOT,
    "campaign_result.added_from": _SNAPSHOT,
    "merge_events.snapshot": _SNAPSHOT,
    "bulk_registration_items.batch_id": _HISTORY,
    "bulk_registration_items.molecule_id": _HISTORY,
    "sample_requests.fulfilled_sample_id": _HISTORY,
    "shipment_items.item_id": _HISTORY,
    "synthesis_requests.fulfilled_batch_id": _HISTORY,
    "batches.synthesis_request_id": _NEVER_WRITTEN,
    "batches.synthesis_route_id": _NEVER_WRITTEN,
    "batches.synthesis_step_id": _NEVER_WRITTEN,
    "campaign_result.representative_batch_id": _NEVER_WRITTEN,
    "plates.parent_plate_id": _NEVER_WRITTEN,
    "plates.template_id": _NEVER_WRITTEN,
    "synthesis_requests.bulk_request_id": _NEVER_WRITTEN,
    "rgroup_assignments.molecule_id": _MEMBERSHIP_CACHE,
    "scaffold_tree_jobs.result_json": _MEMBERSHIP_CACHE,
    "umap_jobs.result_json": _MEMBERSHIP_CACHE,
    "sar_activity_projections.channel_spec": _SAR_PROJECTION,
    "sar_activity_values.molecule_id": _SAR_PROJECTION,
    "sar_activity_values.snapshot": _SAR_PROJECTION,
    "export_jobs.query_snapshot": _FILTER,
    "saved_searches.columns": _FILTER,
    "saved_searches.query": _FILTER,
    "campaign.project_id": _TIER1_ONLY,
    "collection_import_templates.used_in_collections": _TIER1_ONLY,
    "favorites.entity_id": _TIER1_ONLY,
    "protocols.control_layouts": _TIER1_ONLY,
    "registered_plates.project_id": _TIER1_ONLY,
    "registered_plates.template_id": _TIER1_ONLY,
    "registration_forms.field_overrides": _TIER1_ONLY,
    "synthesis_requests.parent_request_id": (
        "parent request link; a molecule force delete can remove a finished parent "
        "(docs/backlog/tier1-only-parents-id-references.md)"
    ),
    "synthesis_requests.project_id": _TIER1_ONLY,
    "campaign.superseded_by_campaign_id": "campaigns can't be deleted",
    "campaign.supersedes_campaign_id": "campaigns can't be deleted",
    "campaign_measurement.source_curve_id": (
        "provenance that every refit already replaces; the cell keeps curve_snapshot"
    ),
    "campaign_measurement.source_readout_id": (
        "provenance that every recompute already replaces; the cell keeps its value"
    ),
    "campaign_stage.criteria": "channel ids inside the same campaign",
    "cdd_plate_sync.plate_id": (
        "inventory plates aren't force-deleted; see "
        "docs/backlog/non-admin-deletes-leave-id-references.md"
    ),
    "collections.derived_from_campaign_id": "campaigns can't be deleted",
    "import_templates.column_mappings": (
        "readout ids of the template's default protocol, whose delete that template blocks"
    ),
    "plate_comments.target_id": (
        "inventory plates, groups and loans aren't force-deleted; see "
        "docs/backlog/non-admin-deletes-leave-id-references.md"
    ),
    "plate_loan_items.plate_id": "loan history outlives the plate by design",
    "reaction_steps.eln_entry_id": "ELN entries don't exist yet",
    "reaction_steps.preceding_step_ids": "step ids inside one route, deleted with it",
    "reaction_steps.reagents": (
        "not rendered; unchecked reagent ids are docs/backlog/writers-accept-unchecked-ids.md"
    ),
    "readout_data.well_id": "always deleted together with its wells",
    "runs.eln_entry_id": "ELN entries don't exist yet",
    "runs.qc_metrics": "keyed by the run's own plates, deleted with it",
    "synthesis_requests.proposed_route_id": (
        "a route for the request's own molecule, whose requests block or go first"
    ),
}


def _id_bearing_columns() -> Iterator[str]:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if col.name in _NOT_REFERENCES or col.foreign_keys:
                continue
            kind = col.type
            holds_ids = (
                isinstance(kind, Uuid)
                or (isinstance(kind, ARRAY) and isinstance(kind.item_type, Uuid))
                or isinstance(kind, JSON)
            )
            if holds_ids:
                yield f"{table.name}.{col.name}"


def test_every_id_only_reference_is_classified():
    with _rules_loaded():
        covered = {ref for rule in all_rules() for ref in rule.references}
    unclassified = sorted(
        c for c in _id_bearing_columns() if c not in covered and c not in LEFT_ALONE
    )
    assert not unclassified, (
        "These columns can hold another row's id with no FK. Say what a force "
        "delete does to them:\n"
        + "\n".join(f"  {c}" for c in unclassified)
        + "\n\nResolution: cover the column with a CascadeRule (fk_column, or match "
        "plus covers), or add it to LEFT_ALONE with the reason dangling is acceptable."
    )


_FORCE_DELETE_ROOTS = sorted(table_for_entity_type(et) for et in TIER2_ENTITY_TYPES)


def _force_delete_reach(root: str) -> tuple[set[str], set[str]]:
    """Tables a force delete of ``root`` removes rows from, and the tables whose rules it walks."""
    removed, walked, stack = {root}, {root}, [root]
    while stack:
        for rule in get_rules_for_parent(stack.pop()):
            if rule.action != CascadeAction.CASCADE:
                continue
            removed.add(rule.child_table)
            if rule.recurse_into_entity and rule.child_table not in walked:
                walked.add(rule.child_table)
                stack.append(rule.child_table)
    return removed, walked


# A BLOCK rule stops the whole delete before any row is touched, so the FK is
# never hit. CASCADE and SET_NULL each resolve the FK directly. A WARN rule
# does neither: the delete goes ahead and the FK violation still fires.
_HANDLES_FK = (CascadeAction.CASCADE, CascadeAction.SET_NULL, CascadeAction.BLOCK)


def test_every_fk_into_a_force_deleted_table_is_handled():
    problems: list[str] = []
    with _rules_loaded():
        for root in _FORCE_DELETE_ROOTS:
            removed, walked = _force_delete_reach(root)
            handled = {
                (r.child_table, r.fk_column, r.parent_table)
                for table in walked
                for r in get_rules_for_parent(table)
                if r.fk_column is not None and r.action in _HANDLES_FK
            }
            for child, col, parent in sorted(_collect_all_fks()):
                if (
                    parent in removed
                    and (child, col, parent) not in handled
                    and not _has_db_ondelete_handling(child, col)
                ):
                    problems.append(f"  {root}: {child}.{col} -> {parent}")
    assert not problems, (
        "A force delete removes rows these FKs point at, and nothing clears or "
        "removes the referencing rows first, so the delete fails on the constraint:\n"
        + "\n".join(problems)
        + "\n\nResolution: add a CascadeRule on the parent (and recurse into that parent "
        "if a rule deletes it), or give the FK an ondelete of CASCADE or SET NULL."
    )


def test_rules_that_do_not_cascade_target_tables_with_ids():
    """M2: the runner matches, samples and nulls a BLOCK/WARN/SET_NULL rule's rows
    by id (``child.c.id``). A CASCADE rule is the one exception — it may go by
    predicate alone against an id-less join table (``plan.link_deletes``)."""
    with _rules_loaded():
        missing_id = [
            f"{r.child_table} ({r.action.value}, {r.fk_column or ', '.join(r.covers)})"
            for r in all_rules()
            if r.action != CascadeAction.CASCADE
            and "id" not in Base.metadata.tables[r.child_table].c
        ]
    assert not missing_id, (
        "Non-CASCADE rules need an id column on their child table, or the runner "
        "can't match, sample or null their rows:\n" + "\n".join(f"  {m}" for m in missing_id)
    )


def test_classification_names_real_columns():
    columns = {f"{t.name}.{c.name}" for t in Base.metadata.tables.values() for c in t.columns}
    named = {*LEFT_ALONE, *(f"{child}.{col}" for child, col, _ in IGNORED_FKS)}
    stale = sorted(named - columns)
    assert not stale, "Entries naming columns that don't exist:\n" + "\n".join(
        f"  {s}" for s in stale
    )
