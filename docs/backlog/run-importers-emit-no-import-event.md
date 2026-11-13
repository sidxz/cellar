# The run file importers record no "data imported" domain event

**Found:** 2026-11-12, while adding the instrument file import (`feat/instrument-curves`).

**Root cause:** neither existing run importer emits a domain event saying that data was imported into a run, so the audit trail cannot show who loaded which file into which run, or how many values it wrote.

- `backend/src/cellar/application/screening/import_run_file.py` takes an `EventDispatcherProtocol` and stores it as `self._dispatcher`, but never calls it, and it discards the events returned by `await self._uow.commit()`.
- `backend/src/cellar/application/screening/import_summary_file.py` takes no dispatcher at all. Its rows are written through `BulkCreateReadoutData`, which does dispatch, but `ReadoutData` registers no events, so nothing is dispatched.
- `backend/src/cellar/domain/screening_assay/events.py` has no event for either import.

The only audit footprint of either import today is the `AttachmentUploaded` event from attaching the uploaded file to the run, which is best-effort and says nothing about what was written.

**Contrast:** the instrument file import (`import_instrument_file.py`) records `RunInstrumentFileImported` (run, reader, file name, positions, curves, readout values) through `Run.record_instrument_import` and dispatches it after the unit of work. The event's `audit_changes()` puts the file name, reader and the three counts into its audit record; without that method the generic audit handler writes only the event's name.

**Fix direction:** add an equivalent event for each of the two importers (for example a run method that records the file name and the counts of plates, wells and values written), register it on the run inside the import's unit of work, and dispatch the events `commit()` returns after the block. For `import_run_file.py` that also means actually using the dispatcher it already holds.

**Status:** recorded, not fixed. Kept out of the instrument import change to keep that work scoped.
