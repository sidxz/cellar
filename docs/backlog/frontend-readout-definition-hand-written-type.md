# Frontend `ReadoutDefinition` is hand-written, not the generated type

**Found:** 2026-11-13, thermal shift analysis (Task 11).
**Status:** Open. Pre-existing.

## Root cause

`frontend/src/features/screening-assay/types/index.ts` declares `ReadoutDefinition` by hand
instead of aliasing the orval-generated `ReadoutDefinitionResponse`, against the rule in
`CLAUDE.md` ("Never hand-roll a TypeScript interface that mirrors a backend DTO"). New backend
fields (most recently `melt_config`) have to be added by hand, typed off the DTO.

Swapping to `export type ReadoutDefinition = ReadoutDefinitionResponse` gives about 92 type
errors across about 15 files, because the backend response model is loosely typed:
`dose_response_config`, `normalizations`, `pick_list_values` and `data_type` are untyped dicts or
plain strings in `ReadoutDefinitionResponse` (`backend/src/cellar/interface/routes/protocols.py`).

## Suggested fix

Type those fields precisely on the backend response model (Pydantic models or `Literal`s for the
config, enum for `data_type`, list models for normalizations and pick-list values), regenerate,
then replace the hand-written interface with the alias and fix the remaining fallout.
