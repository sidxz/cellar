# Enum-valued command fields return 500 on invalid values

**Found:** 2026-06-05, during Collection `type` attribute work (code review of Task 4).
**Status:** Open. Pre-existing pattern-wide gap — not introduced by the collection-type change.

## Root cause

Command DTOs carry enum-valued fields as plain `str` (e.g. `CreateCollectionCommand.visibility`,
now also `.type`) and convert at the use-case boundary via `EnumClass(input.value)`.
An invalid string (e.g. `"bogus"`) raises `ValueError`, which no exception handler catches —
`error_handlers.py` only registers handlers for `DomainError` subclasses — so FastAPI returns
a 500 instead of a 422.

Affected (at minimum): `visibility` and `type` on collection create/update. Any other route
that converts a body `str` to a domain enum the same way shares the gap.

**Update (same day):** `type` bodies were shipped enum-typed (option 1 below), so invalid
*strings* for `type` now 422 at the Pydantic boundary. Residual gap for `type` is only the
explicit-`null` PATCH edge (`body.type.value` → AttributeError → 500); `visibility` retains
the full gap.

## Fix options (pick one, apply pattern-wide)

1. **Pydantic `Literal` constraints on body models** — FastAPI rejects invalid values with 422
   before the use case runs. Matches how `tag_logic: Literal["any", "all"]` is already handled
   in `collections.py`. Preferred.
2. Global `ValueError`/`ValidationError` exception handler mapping to 422.
3. try/except around enum conversion in each use case returning `Failure(ValidationError(...))`.

## Notes

- Not user-reachable from the UI (selects only send valid values); affects direct API callers.
- Keep the command-DTO-carries-`str` convention either way; the fix belongs at the interface
  (body model) or error-handler layer.
