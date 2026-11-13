# The instrument file reader loads every sheet before choosing the ones it needs

**Found:** 2026-11-12, in the whole-branch review of the instrument file import (`feat/instrument-curves`).

**Root cause:** the reader in `backend/src/cellar/infrastructure/instrument_readers/` (its `_load`) reads every row of every sheet of the workbook into memory, and only then picks the overview sheet and the sheets in the raw layout. The 20 MB upload limit is applied to the compressed bytes of the file, so a workbook that is small on the wire can expand to far more rows in memory than its size suggests.

**Exposure:** editors only (preview and import both require the editor role). The existing tabular importers (run file, summary file, plate map) parse whole uploads into memory in the same way, so this is hardening, not a regression introduced by the instrument import.

**Fix direction:** read only the first row of each sheet (the reader's `recognises` already does this with `iter_rows(max_row=1)`), decide from those rows which sheets belong to the recognised layout, and then load only those sheets in full. A cap on rows per sheet would bound the rest.

**Status:** recorded, not fixed.
