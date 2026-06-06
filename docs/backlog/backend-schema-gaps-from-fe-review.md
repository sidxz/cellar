# Backend schema gaps & product issues surfaced by the FE type migration

**Created:** 2026-06-06
**Context:** Completing the orval DTO-alias migration (branch `fe-review-1`)
forced every place the frontend's hand-written types had been papering over
loose backend typing into the open. The FE now uses documented
narrowing/boundary conventions at these spots; the *root* fixes are backend
schema improvements. None block the FE work — but each one currently forces
a cast or client-side reinterpretation that would disappear if the backend
typed its responses precisely.

## Schema gaps (tighten the Pydantic response models, then `pnpm generate:api`)

1. **Opaque `dict` payloads in workspace-config** — `RegistrationForm.field_overrides`
   entries and `WorkspaceSettings.registration_rules` are typed as bare `dict`
   on the backend, so orval emits `{ [key: string]: unknown }`. The FE keeps
   structured views (`FieldOverride` in `use-registration-forms.ts`,
   `RegistrationRules` in `workspace-config/types`) and double-casts at every
   consumption edge. Typing these as proper Pydantic models removes the casts
   and lets the compiler check the editor forms.
2. **Bare-`str` enums** — `CollectionResponse.visibility`/`.type`,
   `ProjectMemberResponse.role`, `UnresolvedMoleculeResponse.ref_type`,
   `MoleculeReferenceBody.ref_type`, `InterceptSpecResponse.kind`/`basis`
   (and the inventory status/source/priority fields) are `str` on the backend
   while the FE legitimately knows the closed value sets. FE re-narrows via
   `Omit<...> & {...}` intersections / `as Enum` label-map lookups. Backend
   `Literal[...]`/`Enum` types would make the generated types carry the union.
3. **`activity_data` untyped** — `/search/execute` types it
   `dict[str, dict[str, Any]]` (`search.py:165`); orval emits `unknown` values
   and the FE casts. A typed per-protocol activity model would flow through.
4. **`CurveDetailResponse.raw_data` / `excluded_points`** — `list[dict[str, Any]]`
   (`molecule_activity.py`); same story.

## Product / feature decisions

5. **Scaffold color mode is inert** — `cluster-map-view.tsx` builds a
   scaffold→molecule map from `bemis_murcko_smiles`, but **no backend route
   serializes that field** (it exists on the domain model only), so "color by
   scaffold" has silently never activated. Decide: serialize the field on the
   molecule/search response (preferred — the data exists) **or** remove the
   color mode. The FE read is now a typed, commented boundary (no `as any`)
   pointing here.
6. **Organization "Active" switch writes to nowhere** — `organization-dialog.tsx`
   renders an Active switch in edit mode and binds it to form state, but
   `UpdateOrganizationBody` has no `is_active` field — the toggle is silently
   dropped on save. Decide: add `is_active` to the update command/route, or
   remove the switch. (21 CFR note: deactivation should likely be a separate
   explicit action with audit reason, not a form field.)
7. **Plate-import preview naming** — backend sends `row_count`
   (`plate_import.py:47`); the FE's old hand type said `total_rows`, which made
   the preview row count silently `undefined` at runtime (now fixed FE-side by
   reading `row_count`). If `total_rows` was the intended public name, rename
   on the backend; otherwise nothing to do — recorded because the bug shipped.
