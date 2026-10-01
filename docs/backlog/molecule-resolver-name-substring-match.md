# Name references resolve by substring — one partial match links the wrong compound

**Found:** 2026-10-01, whole-branch review of register-to-projects.

**Symptom:** adding compounds to a collection or project by `ref_type: "name"`
resolves through `find_active(search_term=value, limit=2)` — a substring search.
Two or more hits come back `ambiguous`, but exactly one *partial* hit resolves:
pasting "Asp" links "Aspirin" when that is the only name containing it.

**Root cause:** `MoleculeResolver._resolve_name` (`application/shared/molecule_resolver.py`)
reuses the list endpoint's search instead of an exact (case-insensitive) name /
identifier match.

**Fix direction:** match names exactly (case-insensitive) against molecule names and
custom identifiers; keep substring search for autocomplete only. Shared by
collections and the project bulk-add endpoint, so one fix covers both.
