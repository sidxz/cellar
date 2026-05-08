"""Maps SQL table name → (entity_type, label_column).

Used by the inbound FK utility to render human-readable samples in
blocker payloads and cascade previews.

Column names are verified against actual SQLAlchemy models.
"""

# table_name -> (entity_type, label_column or None)
TABLE_LABELS: dict[str, tuple[str, str | None]] = {
    # --- Screening & Assay ---
    "protocols": ("protocol", "name"),
    "runs": ("run", "notes"),               # RunModel has no name; notes is best human label
    "plates": ("plate", "barcode"),         # barcode: Mapped[str | None]
    "wells": ("well", None),                # leaf, count-only
    "targets": ("target", "name"),
    "plate_templates": ("plate_template", "name"),
    "readout_definitions": ("readout_definition", "name"),
    "condition_definitions": ("condition_definition", "name"),
    "readout_data": ("readout_data", None),
    "dose_response_curves": ("dose_response_curve", None),
    "run_import_templates": ("run_import_template", "name"),
    "compound_flags": ("compound_flag", None),  # no name column
    # --- Chemical Registration ---
    "molecules": ("molecule", "registration_number"),
    "molecule_identifiers": ("molecule_identifier", "identifier"),
    "mixture_components": ("mixture_component", None),
    "molecule_relationships": ("molecule_relationship", None),
    "synthesis_routes": ("synthesis_route", "name"),
    "reaction_steps": ("reaction_step", None),
    "bulk_registrations": ("bulk_registration", None),
    "bulk_registration_items": ("bulk_registration_item", None),
    "bulk_disclosures": ("bulk_disclosure", None),
    "disclosure_requests": ("disclosure_request", None),
    "merge_events": ("merge_event", None),
    # --- Inventory ---
    "batches": ("batch", "batch_number"),   # actual column is batch_number, not lot_number
    "samples": ("sample", "barcode"),
    "storage_locations": ("storage_location", "name"),
    "registered_plates": ("registered_plate", "barcode"),
    "import_templates": ("import_template", "name"),
    "shipments": ("shipment", "tracking_number"),
    "shipment_items": ("shipment_item", None),   # actual table is shipment_items, not shipment_lines
    "synthesis_requests": ("synthesis_request", None),  # no title/name column
    "sample_requests": ("sample_request", None),
    # --- Research Organization ---
    "projects": ("project", "name"),
    "collections": ("collection", "name"),
    "collection_molecules": ("collection_molecule", None),
    "saved_searches": ("saved_search", "name"),
    "project_members": ("project_member", None),
    # --- Workspace Config ---
    "organizations": ("organization", "name"),
    "workspace_settings": ("workspace_settings", None),
    "controlled_vocabularies": ("vocabulary", "name"),
    "custom_field_definitions": ("custom_field", "label"),
    "salt_catalog": ("salt_entry", "code"),      # actual table is salt_catalog, not salt_entries
    "registration_forms": ("registration_form", "name"),
    "external_api_keys": ("api_key", "label"),
    "ontology_slot_definitions": ("ontology_slot", "name"),
    "protocol_forms": ("protocol_form", "name"),
    "data_sources": ("data_source", "name"),
    # --- Audit & Compliance ---
    "audit_operations": ("audit_operation", None),
    "audit_entries": ("audit_entry", None),
    "electronic_signatures": ("electronic_signature", None),
    # --- Attachments ---
    "attachments": ("attachment", None),
    # --- Association tables (no id column) ---
    "protocol_projects": ("protocol_project", None),
    "molecule_projects": ("molecule_project", None),
}


def label_for_table(table: str) -> tuple[str, str | None]:
    """Return (entity_type, label_column) for a table, defaulting to (table, None)."""
    return TABLE_LABELS.get(table, (table, None))


def table_for_entity_type(entity_type: str) -> str | None:
    """Reverse lookup: entity_type → table name."""
    for tbl, (et, _label) in TABLE_LABELS.items():
        if et == entity_type:
            return tbl
    return None
