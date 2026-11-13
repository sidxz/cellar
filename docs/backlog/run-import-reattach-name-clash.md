# Run imports cannot re-attach a file after a reset

**Found:** 2026-11-12, in a live check of the instrument file import (`feat/instrument-curves`).

**Root cause:** each run importer attaches the uploaded file to the run under the uploaded name. Attachment file names are unique per entity (`uq_attachment_entity_filename` on workspace, entity type, entity id, file name). Resetting a run's data keeps its attachments by design, so importing the same file again after a reset fails to attach, and the importer puts the raw exception text into `attachment_warning` ("attachment failed: Database constraint violated: uq_attachment_entity_filename"), which the wizard shows to the user. The data itself imports correctly.

The two older importers still carry the same attach block:

- `backend/src/cellar/application/screening/import_run_file.py` (`_attach_raw_file`)
- `backend/src/cellar/application/screening/import_summary_file.py` (`_attach_raw_file`)

**Fixed for the instrument import:** `backend/src/cellar/application/screening/import_instrument_file.py` lists the run's attachments (workspace-scoped, `AttachmentRepository.find_by_entity`) and attaches under `numbered_file_name(...)` from `backend/src/cellar/domain/attachment/file_name.py` (`name (2).ext`, then `name (3).ext`; a name with no extension gets ` (2)` appended). The result carries `stored_file_name` when the name changed, and the wizard says where the file is. Any attach failure gives the plain sentence "The file could not be attached. Upload it on the Files tab." and the reason goes to the log (`instrument_import.attachment_failed`).

**Fix direction:** give the two older importers the same treatment (inject `AttachmentRepository`, use `numbered_file_name`, plain warning, reason to the log), and surface the stored name in their wizards.

**Status:** recorded, not fixed.
