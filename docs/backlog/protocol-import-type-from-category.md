# Imported protocols become Biochemical unless the category is literally a type name

**Found:** 2026-10-04, importing "Whole Cell Growth Inhibition HTS" (external-vault category "Cell") during a walkthrough. It arrived with Type = Biochemical.

**Root cause:** `ImportCddProtocol` (`backend/src/cellar/application/cdd_import/import_cdd_protocol.py:131-136`) turns the external category into a `ProtocolType` only by exact match after lower-casing and replacing spaces and dashes: "Cell" becomes `cell` and "Cell-Based Assay" becomes `cell_based_assay`. Anything that isn't literally a type value (`cell_based`, `admet`, `in_vivo`, ...) silently stays `biochemical`. External categories are free text, so whole-cell protocols are routinely mis-typed, and the Type facet on the Assays page then misleads.

**Fix direction:** map the categories that actually occur in the vault (for example Cell, Cell-Based Assay and Whole cell to `cell_based`, Enzyme Assay to `biochemical`) with an explicit table, and show the chosen type in the import preview so it can be changed before importing. Until then, check the Type after an import.
