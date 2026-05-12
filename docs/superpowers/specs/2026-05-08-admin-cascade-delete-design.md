# Admin Hard Delete — Design

**Date:** 2026-05-08
**Branch:** `fe2`
**Status:** Approved by user; awaiting implementation plan.

## Problem

Today every entity in the system has its own delete endpoint, but most are gated by *state-based* preconditions (e.g., `Protocol.delete()` requires `status=DRAFT`). Workspace admins have no escape hatch: a botched run that got committed, a vocabulary entry referenced once-by-mistake, or a protocol whose drafts got promoted by accident — all are stuck. The fallback today is engineering opening a database shell, which is unaudited and risks far more than the entity in question.

Admins need a clearly-scoped, audited way to delete. The naive answer ("admin bypasses all preconditions and cascade-deletes everything") over-rotates: it's a wide blast radius, hard to preview accurately, and over-engineers the 80% case where dependents are zero or shallow.

## Goals

1. **Admin can delete any entity** in their workspace, given they own the consequences via audit trail.
2. **Default behavior is RESTRICT**: if anything depends on the entity, the delete is blocked with a clear, scannable list of blockers. Admin resolves them and retries.
3. **Force-delete with cascade preview** is a separate, opt-in power tool, available only on the three entities where deep cascade is a legitimate workflow: **Protocol, Run, Molecule**.
4. **Every successful delete is audited** as an `AuditOperation` of type `admin_hard_delete`, with snapshots of every deleted row in `AuditEntry.old_value` (existing append-only audit infrastructure — no new tables).
5. **Schema drift is caught at CI**: a coverage test introspects every inbound FK and asserts each is either acknowledged by the RESTRICT path or covered by a force-cascade descriptor.

## Non-Goals

- Soft delete / trash / restore. Hard delete only.
- Bulk admin delete (multi-select). Single entity per request.
- E-signature confirmation (re-auth at delete time). The schema is already there for it; we'll layer it in later if a workspace policy demands it.
- Programmatic admin delete via API key. UI flow only for v1.
- Force-cascade for entities other than Protocol, Run, Molecule. The remaining ~15 aggregates use Tier 1 only; we expand if/when admins hit the wall.

## Two-Tier Approach

### Tier 1 — RESTRICT with Informative Blockers (all entities)

Every entity gains an admin delete endpoint that:

1. Verifies caller has workspace admin role (`require_admin`).
2. Looks up the entity (404 if missing, scoped to workspace).
3. Computes inbound FK references at the moment of attempt: walk SQLAlchemy's `Base.metadata` for tables holding FKs to this row, count matching rows per table.
4. If any blocking references exist, returns 409 with structured payload:
   ```json
   {
     "error": "delete_blocked_by_dependencies",
     "blockers": [
       {"table": "runs", "count": 12, "samples": ["NadD-Q1", "NadD-Q2", "ChlamydiaScreen-2024", "..."]},
       {"table": "saved_searches", "count": 3, "samples": ["My NadD picks", "..."]}
     ]
   }
   ```
5. If no blockers, opens an `AuditOperation('admin_hard_delete')`, snapshots the row, hard-deletes, commits. One row deleted, one operation, two audit entries (the operation + one entry for the deleted row).

**Inbound FK introspection** is a single utility in `infrastructure/cascade/inbound_refs.py`. It uses `Base.metadata.tables` and `Table.foreign_keys` — no per-entity boilerplate, no registry. It also resolves a `label_field` per child table (a small dict) so `samples` in the response are human-readable rather than UUIDs.

Audit references (`audit_entries.entity_id`, `audit_operations.entity_id`) are *not* FKs by design — they store entity_id as a plain UUID. The introspection utility skips them. They become orphan-OK by design; that is the existing pattern.

### Tier 2 — Force Delete With Cascade Preview (Protocol, Run, Molecule only)

For these three entities, an additional admin flow is exposed:

1. **Preview**: `POST /admin/{entity_type}/{id}/cascade-preview` returns a tree of dependents categorized by action.
2. **Execute**: `DELETE /admin/{entity_type}/{id}/cascade` with `{typed_name, reason}` re-runs preview, opens a single AuditOperation, snapshots every cascaded row across all tables, hard-deletes in dependency order, commits.

The cascade engine reads outbound declarations registered per-module (see Registry below). The user types the entity's display name (case-sensitive exact match) and provides a reason; both are required.

## Components

### CascadeRule (domain/shared/cascade)

```python
@dataclass(frozen=True)
class CascadeRule:
    table: str               # table holding the FK
    fk_column: str           # FK column name
    parent_table: str        # table the FK points at
    action: Literal["cascade", "set_null", "block", "warn"]
    label_field: str | None  # for named-heads in preview; None = leaf, count only
    display_label: str       # group label, e.g., "Runs"
```

### Action semantics

| Action | Behavior in preview | Behavior at execute |
|---|---|---|
| `cascade` | Recurses; rows shown with named heads (or count if leaf). | DELETE rows; recurse into their own outbound rules. |
| `set_null` | Shown as "N rows will lose their reference." | UPDATE column to NULL; do not recurse. |
| `block` | Shown as a hard blocker; preview marked unsafe. | Refuse delete with 409 if any rows match. |
| `warn` | Shown as informational; user must acknowledge. | Do nothing; rows persist with potentially-dangling references (e.g., audit entries). |

### Registry (domain/shared/cascade/registry.py)

Modules declare their cascade rules at import time:

```python
# domain/screening_assay/cascade.py
from cellar.domain.shared.cascade import CascadeRule, register_rules

register_rules(
    CascadeRule(table="runs", fk_column="protocol_id",
                parent_table="protocols", action="cascade",
                label_field="name", display_label="Runs"),
    CascadeRule(table="plates", fk_column="run_id",
                parent_table="runs", action="cascade",
                label_field="barcode", display_label="Plates"),
    CascadeRule(table="wells", fk_column="plate_id",
                parent_table="plates", action="cascade",
                label_field=None, display_label="Wells"),
    # ... readout definitions, plate templates, hit call rules, etc.
)
```

Each module owns its own `cascade.py`. Adding a new module that references existing entities does **not** require touching the existing module's cascade.py — the new module simply registers its own outbound rules. This is the scalability property: cascade rules are physically dispersed but assembled at startup.

### CascadeRunner (infrastructure/cascade)

A single class with two methods:

- `async preview(session, entity_type, id) -> CascadeNode` — recursively walks the registry, fetches counts and named heads per cascade level, returns a tree.
- `async execute(session, entity_type, id, audit_op) -> None` — re-runs preview internally as a safety check, then performs deletes/nulls in topological order under one transaction. Snapshots each deleted row to AuditEntry before deletion.

### FK Coverage Test (tests/unit/cascade/test_fk_coverage.py)

Pytest test that:

1. Iterates every Table in `Base.metadata`.
2. For each ForeignKey, asserts that **either**:
   - The FK's child table is in the Tier 1 known-table list (i.e., RESTRICT will surface it as a blocker — so we don't silently ignore it), **or**
   - A registered `CascadeRule` covers the (table, fk_column) pair (Tier 2 force-cascade descriptors).
3. Maintains an explicit `IGNORED_FKS` allow-list for cases that legitimately don't need either treatment (e.g., audit refs that aren't even FKs in the first place — those don't appear in metadata, so nothing to ignore).

If a developer adds a new FK without acknowledging it in either system, the test fails with a message naming the offending table/column.

## API Design

### Tier 1 (all entities)

```
DELETE /admin/{entity_type}/{id}
Body: {"reason": "string, required, max 500 chars"}
204 → success
404 → entity not found
403 → caller not admin
409 → blocked by dependencies (payload as above)
```

`{entity_type}` is a discriminator drawn from a registered allow-list of admin-deletable entity types. The handler dispatches to the right repository based on the discriminator.

### Tier 2 (Protocol, Run, Molecule only)

```
POST /admin/{entity_type}/{id}/cascade-preview
204 → not used; always 200 with tree payload
200 → CascadeNode tree
404 → entity not found
403 → caller not admin

DELETE /admin/{entity_type}/{id}/cascade
Body: {"typed_name": "string, exact case-sensitive match", "reason": "string"}
204 → success
404 → entity not found
403 → caller not admin
422 → typed_name mismatch or reason missing
409 → block-action rule matched between preview and execute (race; rare)
```

CascadeNode payload shape:

```ts
type CascadeNode = {
  entity_type: string
  table: string
  display_label: string
  count: number
  samples: { id: string; label: string }[]   // up to 5
  truncated: boolean                          // true if count > samples.length
  action: "cascade" | "set_null" | "block" | "warn"
  children: CascadeNode[]
}
```

## Frontend Design

### Tier 1 — Standard delete with friendly blocker dialog

- Existing entity menus get an "Admin: Delete" item shown when `auth.isAdmin`.
- Click opens a small dialog with a `reason` textarea and a confirm button.
- On 409, the dialog flips to a "Cannot delete" view listing the blockers with their named samples and a hint: "Delete or unlink these first."
- No type-name confirmation — RESTRICT-blocked + the reason field is enough friction.

### Tier 2 — Force cascade dialog (Protocol, Run, Molecule only)

- Distinct menu item: **"Force delete (cascade)"**, styled with destructive emphasis (red, separated from regular delete by a divider).
- Click → `POST /admin/.../cascade-preview` → renders `<CascadeDeleteDialog>`:
  - Tree of dependents grouped by action, with named heads for non-leaf groups.
  - Total count summary at top: "Will delete 1 protocol, 12 runs, 144 plates, 13,824 wells; will null 3 saved-search references; 5 ELN entries will reference a deleted protocol."
  - "Type the protocol name to confirm" input — case-sensitive exact match.
  - Reason textarea (required).
  - Submit disabled until typed_name matches and reason is non-empty.
- Submit → `DELETE /admin/.../cascade` → toast + redirect to entity-list view on success.

The cascade dialog is a single shared component parameterized by entity_type. Onboarding a new entity to Tier 2 in future is just: register cascade rules, add the menu item.

## Audit Recording

One `AuditOperation` per admin delete:

- `operation_type='admin_hard_delete'` — new enum value, requires migration.
- `reason` — required, from request body.
- `entity_type`, `entity_id` — the root being deleted.
- `actor_type='user'`, `user_id`, `ip_address`, `user_agent` — standard.

Each row deleted (root + every cascaded row) produces one `AuditEntry`:

- `entity_type`, `entity_id` — the deleted row's table and id.
- `field_name='*'` — sentinel meaning "whole row deleted" (existing AuditEntry schema accepts free-form strings; this is a deliberate convention to avoid emitting one entry per column).
- `action='delete'`.
- `old_value` — full row serialized as JSON.
- `new_value=null`.

Volume note: deleting a Protocol with 14k Wells produces ~14k AuditEntries. This is by design — it matches the existing audit pattern, is queryable, and gives forensic recoverability if an admin wants to know what was in a row. If volume becomes a real operational issue we revisit (likely by introducing a `deletion_snapshots` blob table referenced by a single AuditEntry per cascade), but not now.

## Authorization

- All endpoints require `auth.is_admin` for the caller's current workspace.
- Workspace scoping is non-negotiable: an admin in workspace A cannot delete entities in workspace B. The repository layer enforces this; the handler defends-in-depth by passing `auth.workspace_id` into every lookup.
- Cross-workspace admin (Sentinel super-admin) is *out of scope* for this design.

## Pilot Entities (Tier 2)

The three force-cascade entities, with the cascade trees that drive the engine's design:

| Entity | Notable cascade rules |
|---|---|
| **Protocol** | `runs.protocol_id → cascade` (recurse to Plates → Wells → Readouts), `readout_definitions.protocol_id → cascade`, `plate_templates.protocol_id → cascade`, `hit_call_rules.protocol_id → cascade`, `saved_searches.scope_protocol_id → set_null`, ELN mentions → `warn` |
| **Run** | `plates.run_id → cascade` (recurse to Wells → Readouts), `dose_response_curves.run_id → cascade`, `hit_calls.run_id → cascade`, `run_imports.run_id → cascade` |
| **Molecule** | `batches.molecule_id → cascade` (recurse to Samples → ShipmentLines), `synthesis_routes.target_molecule_id → cascade`, `project_molecules.molecule_id → cascade`, `collection_molecules.molecule_id → cascade`, fingerprints/identifiers/relationships → `cascade`, ELN mentions → `warn` |

The actual rule files derive these from current schema during implementation; the table above is illustrative not authoritative.

## Implementation Order

1. **Domain primitives** — `CascadeRule`, `CascadeNode`, registry, `register_rules()` import-time hook.
2. **Inbound FK utility** — Tier 1 introspection helper, with label-field map.
3. **Tier 1 endpoint** — generic `DELETE /admin/{entity_type}/{id}` with admin auth, blocker introspection, AuditOperation. Wire one entity end-to-end (start with Vocabulary — simplest) to validate the path.
4. **Tier 1 broad rollout** — register the remaining ~14 entities. Each is a small handler tweak (already exists) + adding to the `entity_type` allow-list.
5. **Migration** — add `admin_hard_delete` to `audit_operation_type` enum.
6. **Cascade rules for pilot entities** — Protocol, Run, Molecule cascade.py files in their domain modules.
7. **CascadeRunner** — preview + execute, with the safety re-run.
8. **Tier 2 endpoints** — `cascade-preview` and `cascade` for the three entities.
9. **FK coverage test** — wire to CI; allow-list is empty initially, `IGNORED_FKS` only for legitimate cases.
10. **Frontend** — `<AdminDeleteButton>` (Tier 1), `<CascadeDeleteDialog>` (Tier 2). Hook them into menus on Protocol, Run, Molecule, and the ~14 Tier 1 entities.
11. **Tests** — unit (descriptor walk, label-field resolution), integration (real DB cascade with rollback assertions), API (auth, blocked, success), e2e (UI flow).

## Open Questions

None blocking. Items to revisit in a future iteration:

- E-signature confirmation for high-stakes Tier 2 deletes (Molecule with shipped Batches).
- Multi-select bulk delete in admin views.
- Soft-delete / trash period (e.g., 7-day grace before purge).
- Cross-workspace admin actions (Sentinel super-admin).

## Risks

- **Audit volume** on large Tier 2 cascades. Mitigated by acceptance ("by design"), with the snapshots-blob fallback documented.
- **Performance** on cascade preview for very large trees. Mitigated by named-heads being a `LIMIT 5` per group rather than a full enumeration.
- **Schema drift** sneaking past CI. Mitigated by FK coverage test that fails on unknown FKs.
- **Cross-context coupling temptation**. The registry's per-module declaration discipline prevents this; reviewers should reject any cascade.py that registers rules for tables it doesn't own.
