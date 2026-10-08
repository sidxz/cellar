# Import failures show "Activity task failed" instead of the cause

**Found:** 2026-10-04, while making the external-vault export poll fail fast on a dead export (branch `fix/vault-api-alignment`).

**Root cause:** the molecule and plate import workflows (`backend/src/cellar/infrastructure/temporal/workflows/cdd_vault_import.py`, `cdd_plate_import.py`) record failures with `str(exc)` or `f"Export poll failed: {exc}"`, where `exc` is Temporal's `ActivityError`. Its text is always "Activity task failed"; the activity's own message sits in `exc.cause`. So the import page reads "Export poll failed: Activity task failed" whether the vault export failed, was canceled, or the key was rejected. The real message only reaches the worker log and the Temporal UI.

**Fix direction:** record the cause when there is one (`str(exc.cause or exc)`) at the `_fail` call sites of both workflows. It only changes an activity argument, not the command sequence, so in-flight histories still replay. Add one workflow test with a failing activity that asserts the stored reason.
