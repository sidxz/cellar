# Tabular imports: unbounded columns and spreadsheet unpacked size

**Found:** 2026-11-13, review of `feat/curves-relabel-compare`.
**Status:** Open for every tabular import except the layout file reader. Pre-existing.

## Root cause

The shared tabular parser (`backend/src/cellar/infrastructure/parsers/tabular_file.py`) builds
one dict per data row with an entry for every header column, padding short rows with `""`
(`_parse_csv` and `_parse_xlsx`). Width is not capped, so memory grows with header width ×
row count, not with file size. For spreadsheets, openpyxl reads the whole shared-strings table
during `load_workbook`, before any row is read, so a small compressed archive can expand to
many times its size.

Measured with a 20 MB upload limit and the layout reader's 2,000-row cap in place: a 0.34 MB
CSV with a 50,000-column header and 2,001 one-cell rows took 3.3 s of synchronous parsing on
the event loop and reached 3.1 GB resident memory. A spreadsheet can do the same up to 16,384
columns, or through a compressed shared-strings table.

The layout file reader now passes `max_columns=64` and `max_uncompressed_bytes=50 MB`. The other
callers pass neither: bulk registration (`start_bulk_registration.py`,
`preview_bulk_registration_file.py`), plate setup (`plate_setup.py`), run readout import
(`import_run_readouts.py`, `preview_run_file.py`) and summary import
(`preview_summary_file.py`, `preview_summary_import.py`, `import_summary_file.py`).

## Suggested fix

Give every importer a column cap that fits its format (a few hundred is ample for any of
them) and the same unpacked-size check for spreadsheets, both already supported by
`TabularParser.parse`. Add a wide-header test per importer. Consider also building rows without
padding them to every header, since callers read cells with `.get(header, "")`.
