# Collection `type` attribute — Design

**Date:** 2026-06-05
**Context:** Research Organization (05)
**Aggregate:** Collection

## Summary

Add a first-class `type` attribute to the `Collection` aggregate to categorize
collections by their role in the early-discovery screening cascade (modeled on
neglected-disease consortiums like MMV and the TB Drug Accelerator).

The attribute is **descriptive today** but modeled as a **first-class domain
enum** (not free text) so it can drive behavior later. No type-driven behavior
is built in this change — only the data model, persistence, API, and display.

## Type values

`CollectionType` (StrEnum), default `generic`:

| value | meaning | cascade stage |
|-------|---------|---------------|
| `generic` | default ad-hoc grouping | — (catch-all) |
| `reference_set` | controls / standards / known actives shared across assays | inputs |
| `library` | screening library (diversity or focused) — assay input | inputs |
| `hit_list` | confirmed hits emerging from a screen | primary output |
| `series` | chemical / SAR series around a chemotype (hit-to-lead → lead-opt) | optimization |
| `distribution_set` | curated set published/shared to partners (MMV "Box" style) | shared artifact |

Why an enum, not the admin-configurable `ControlledVocabulary`: future behavior
keys off values the code knows by name, which free-text vocab can't provide.

## Layers

### 1. Domain (`backend/.../domain/research_organization/`)

- **`enums.py`** — add `CollectionType(StrEnum)` with the six values above;
  add to `__all__`.
- **`collection.py`**:
  - `__init__` gains `type: CollectionType = CollectionType.GENERIC`, stored as
    `self.type`.
  - `create()` gains `type: CollectionType = CollectionType.GENERIC`, passed
    through.
  - `update()` gains `type: CollectionType | None = None`; when not `None`, set
    `self.type`. The existing frozen-guard at the top of `update()` already
    raises `CollectionFrozenError`, so type edits are blocked on frozen
    collections with no extra code.
- **`events.py`** — `CollectionCreated` carries `type` (cheap; benefits the
  append-only audit trail).

### 2. Persistence (`backend/.../infrastructure/persistence/sqlalchemy/research_organization/`)

- **`models.py`** — `CollectionModel.type`:
  `mapped_column(String(32), nullable=False, server_default="generic")`
  (mirrors `visibility`).
- **Alembic migration** — add `type VARCHAR(32) NOT NULL DEFAULT 'generic'` to
  `collections`. Existing rows backfill to `generic` via the server default; no
  data migration step needed.
- **`collection_repository.py`** — map `type` in both `_to_domain` and
  `_to_model`.

### 3. Application (`backend/.../application/research_organization/`)

- **`create_collection.py`** — `CreateCollectionInput` gains
  `type: CollectionType = CollectionType.GENERIC`, passed to `Collection.create`.
- **`close_campaign.py`** — the published collection is created with
  `type=CollectionType.HIT_LIST` (it holds the SELECTED hits from a screen).
- **`compose_collections.py`** — unchanged; uses the `GENERIC` default (a
  boolean composition implies no cascade stage).
- **`update_collection.py`** — `UpdateCollectionInput` gains
  `type: CollectionType | None = None`, threaded through to `Collection.update`.

### 4. Interface (API)

- `CollectionResponse` gains `type`.
- Create / update request schemas gain optional `type` (defaults to `generic`
  on create).
- Regenerate orval in the same change (CLAUDE.md: no hand-rolled DTOs).

### 5. Frontend (`frontend/src/features/research-organization/`)

- Run `pnpm generate:api` so `type` lands on the generated `CollectionResponse`;
  alias in `types/index.ts` if the feature wants a domain name.
- **`create-collection-dialog.tsx`** — add a **Type** `<Select>` with the six
  options and friendly labels (Generic / Reference Set / Library / Hit List /
  Series / Distribution Set), default `generic`, wired into the zod schema and
  submit payload. Editable in edit-mode unless the collection is frozen.
- **`collection-list.tsx` (the collection dashboard)** — add a **Type** column
  rendering the value as a `Badge` (alongside the existing Visibility/Molecules
  badges).
- **`collection-detail.tsx`** — render `type` as a badge in the detail header.

### UI labels

| value | label |
|-------|-------|
| `generic` | Generic |
| `reference_set` | Reference Set |
| `library` | Library |
| `hit_list` | Hit List |
| `series` | Series |
| `distribution_set` | Distribution Set |

## Testing (per layer)

- **Domain** — create with default `generic`; create with explicit type;
  `update()` changes type; frozen collection rejects type change.
- **Persistence** — round-trip a non-default type through the repository.
- **Application** — `close_campaign` emits a collection with `type=hit_list`;
  `create_collection` honors the input type.
- **API** — create/response contract includes `type`; round-trip a non-default
  value.
- **Frontend** — dialog renders and submits the Type field; dashboard column
  renders the badge.

## Mutability

`type` is editable via the edit dialog / `update()` use case, except on frozen
collections (campaign-published / distribution artifacts), where the existing
frozen-guard blocks all edits.

## Out of scope (YAGNI)

No type-driven behavior yet. The enum *enables* but this change does not build:

- `reference_set` → auto-available as assay controls
- `library` → bulk-import / screening-input flows
- `distribution_set` → freeze + external export ("Box" sharing)
- `series` → SAR analysis hooks
- filter-by-type in the collection dashboard (follow-on)
