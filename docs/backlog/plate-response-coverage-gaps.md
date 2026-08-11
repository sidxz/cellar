# Plate API coverage gaps touched-but-not-closed by S3

**Status:** open · **Found:** 2026-08-11 (S3 final whole-branch review triage) · **Origin:** predates S3; recorded because S3 changed the exact lines these gaps guard

Both items are pre-existing test-coverage gaps that S3's Task 1 cleanup commit (`79d39e13`)
modified without adding coverage (deliberately scoped out; verified correct by review +
runtime instead). Recording per the repo convention so they are tracked, not verbal.

## 1. `DeletePlate` 409-children conflict path has no test at all

`DeletePlate` returns `ConflictError("Cannot delete plate '<barcode>': it has child plates")`
when children exist (`application/inventory/registered_plates.py`). No unit or API test
exercises that branch — before or after S3 dropped the child COUNT from the message (the
count was a visibility oracle: it tallied children the caller may not be allowed to see).
A regression re-adding the count, or breaking the 409 entirely, would go unnoticed.

**Fix shape:** one API test — register parent, derive child, `DELETE parent` → assert 409 +
message contains no digit; delete child then parent → 204s. (The equivalent *group* path IS
tested: `tests/api/test_plate_groups.py::TestUpdateMoveDelete::test_delete_with_children_conflict_then_ok`.)

## 2. No response-body round-trip assertion on `PlateResponse.format/plate_type/status`

S3 retyped these three fields from `str` to their StrEnums (OpenAPI tightening for orval).
Wire values are unchanged (StrEnum serializes to its value) — verified by type-level
reasoning, the passing suite, and runtime verification — but no API test asserts the
serialized values of those three fields on a plate response, so the str↔enum equivalence
rests on Pydantic semantics rather than an explicit check. (`confirmation` on the org-plate-policy
response, retyped in the same commit, IS round-trip-asserted — the mechanism is shared.)

**Fix shape:** extend one existing register-plate API test with
`assert data["format"] == "96" and data["plate_type"] == "assay" and data["status"] == "registered"`.
