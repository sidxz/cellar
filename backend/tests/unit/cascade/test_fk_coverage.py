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
import sys

# ---------------------------------------------------------------------------
# Import all SQLAlchemy model modules so that Base.metadata is fully populated.
# Model imports are idempotent (no global registry side-effects) so they are
# safe at module level.
# ---------------------------------------------------------------------------
import chem_vault.infrastructure.persistence.sqlalchemy.audit.audit_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.attachment.attachment_model  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.user_preferences  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.disclosure_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.synthesis_route_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_import_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.cdd_molecule_sync_model  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.inventory.models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.inventory.shipment_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.inventory.sample_request_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.inventory.synthesis_request_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_import_models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_model  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models  # noqa: F401

from chem_vault.infrastructure.persistence.sqlalchemy.base import Base
from chem_vault.infrastructure.cascade.registry import all_rules, _clear_for_test as _clear_cascade_registry

# ---------------------------------------------------------------------------
# Cascade module names.  Imported and unloaded within the test so that:
#   (a) register_rules() re-executes even if a prior test cleared the registry,
#   (b) the cascade modules are evicted from sys.modules after our test so
#       subsequent tests that rely on a fresh first-import still get one.
# ---------------------------------------------------------------------------
_CASCADE_MODULES = [
    "chem_vault.infrastructure.cascade.rules_audit_compliance",
    "chem_vault.infrastructure.cascade.rules_chemical_registration",
    "chem_vault.infrastructure.cascade.rules_inventory",
    "chem_vault.infrastructure.cascade.rules_research_organization",
    "chem_vault.infrastructure.cascade.rules_screening_assay",
]


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
    # Batches → storage_locations: same as samples above
    # -------------------------------------------------------------------------
    ("batches", "storage_location_id", "storage_locations"),

    # -------------------------------------------------------------------------
    # registered_plates → storage_locations: same rationale
    # -------------------------------------------------------------------------
    ("registered_plates", "storage_location_id", "storage_locations"),

    # -------------------------------------------------------------------------
    # registered_plates → runs (screening data link): cross-context soft ref
    # -------------------------------------------------------------------------
    # registered_plates.run_id links a physical plate to a screening run.
    # This is a cross-context reference; the plate is not owned by the run.
    ("registered_plates", "run_id", "runs"),

    # -------------------------------------------------------------------------
    # Protocols → targets: target is a reference entity, not admin-deletable
    # -------------------------------------------------------------------------
    # protocols.target_id is a nullable FK to biological targets. Targets are
    # reference data managed separately; not in the admin-delete cascade path.
    ("protocols", "target_id", "targets"),

    # -------------------------------------------------------------------------
    # Protocols → protocols: self-referential for versioned protocol lineage
    # -------------------------------------------------------------------------
    # protocols.parent_protocol_id links a versioned protocol to its predecessor.
    # Protocol versioning is managed via the protocol lifecycle, not admin delete.
    ("protocols", "parent_protocol_id", "protocols"),

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
    # CDD molecule sync → molecules: sync ledger, survives molecule deletion
    # -------------------------------------------------------------------------
    # cdd_molecule_syncs.molecule_id links the external-import sync record to a
    # registered molecule. The sync ledger is operational metadata and should
    # survive independently; cascade via Tier-2 is not appropriate here because
    # the table tracks the import history, not owned child data.
    ("cdd_molecule_syncs", "molecule_id", "molecules"),

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
    # merge_events → disclosure_requests: append-only audit records
    # -------------------------------------------------------------------------
    # merge_events.disclosure_request_id links a merge event to the disclosure
    # request that triggered it. Merge events are append-only audit records;
    # they must survive deletion of the associated disclosure request.
    # The nullable FK means the DB won't block disclosure_request deletion.
    ("merge_events", "disclosure_request_id", "disclosure_requests"),
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
    return {
        (r.child_table, r.fk_column, r.parent_table) for r in all_rules()
    }


# Tier-1 admin-deletable parent tables — RESTRICT will surface their inbound FKs.
TIER1_PARENT_TABLES = {
    "controlled_vocabularies", "registration_forms", "protocol_forms",
    "salt_catalog", "ontology_slot_definitions", "custom_field_definitions",
    "data_sources", "external_api_keys", "compound_flags",
    "molecule_relationships", "synthesis_routes", "molecules",
    "protocols", "runs", "plate_templates", "run_import_templates",
    "batches", "samples", "shipments", "synthesis_requests",
    "projects", "collections", "saved_searches",
    # Additional Tier-1 entities referenced by FKs in the schema
    "bulk_registrations", "bulk_disclosures", "readout_definitions",
    "plates",
}


def test_every_fk_is_categorized():
    # 1. Evict cascade modules from sys.modules so that import below
    #    re-executes their top-level register_rules() call unconditionally,
    #    even if a prior test's teardown fixture cleared the registry.
    for mod_name in _CASCADE_MODULES:
        sys.modules.pop(mod_name, None)

    # 2. Import cascade modules fresh — each top-level register_rules() fires.
    for mod_name in _CASCADE_MODULES:
        importlib.import_module(mod_name)

    all_fks = _collect_all_fks()
    tier2_keys = _collect_tier2_rule_keys()

    # 3. Evict cascade modules again so subsequent tests that do
    #    `import chem_vault.domain.X.cascade` for the first time still get
    #    a fresh execution (register_rules fires) rather than a cached no-op.
    #    Also clear the registry so other tests start from a known state.
    _clear_cascade_registry()
    for mod_name in _CASCADE_MODULES:
        sys.modules.pop(mod_name, None)

    uncovered: list[tuple[str, str, str]] = []
    for fk in all_fks:
        child_table, fk_col, parent_table = fk
        if fk in IGNORED_FKS:
            continue
        if parent_table in TIER1_PARENT_TABLES:
            continue  # Tier-1 RESTRICT will handle it
        if fk in tier2_keys:
            continue  # Tier-2 rule covers it
        uncovered.append(fk)

    assert not uncovered, (
        "FKs not covered by Tier-1 RESTRICT or Tier-2 cascade rules:\n"
        + "\n".join(f"  {ct}.{c} -> {pt}" for ct, c, pt in uncovered)
        + "\n\nResolution: either register a CascadeRule, add the parent table "
          "to TIER1_PARENT_TABLES, or add to IGNORED_FKS with a justifying comment."
    )
