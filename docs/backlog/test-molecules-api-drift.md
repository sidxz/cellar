# `tests/api/test_molecules.py` has 2 pre-existing failures

**Found:** 2026-09-11, running the full API suite before finishing `feat/remove-campaign-decisions`
(that branch never touches molecules; failures reproduce independently of it).

- `TestMoleculeTestCounts::test_tested_molecule_returns_count` and `::test_project_scoped_count` —
  fixture inserts a `dose_response_curves` row with `batch_id = NULL`, which violates the column's
  NOT NULL constraint. The fixture predates the batch-required DRC change; give it a batch.

Also pre-existing: `tests/unit/application/export/renderers/test_pdf_renderer.py::test_pdf_renders_a_small_report`
fails on a clean `main` (verified by stashing during the decision-removal work); not investigated.

**2026-10-01 (search chemist pass):** both still fail on `fix/search-chemist-pass`, unrelated to it.
PDF root cause: WeasyPrint can't `dlopen('libgobject-2.0-0')` — the GLib/Pango system libs aren't
installed on this Mac (`brew install pango` provides them); not a code bug.
