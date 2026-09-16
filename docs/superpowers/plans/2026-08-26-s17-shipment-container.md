# S17 — Shipment as the container for the trip — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shipments carry plates and samples (polymorphic items), have a direction and an optional loan link, resolve items by barcode, and surface on the plate, sample and loan pages — records only.

**Spec:** `docs/superpowers/specs/2026-08-26-shipment-container-spec.md` — read it first.

## Global Constraints
Identical to `docs/superpowers/plans/2026-08-26-s15-run-plate-inventory-link.md` "Global Constraints" (read them) — guidelines first, guard order, Railway, workspace scoping, ruff/pytest (`DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock` for API/integration), biome/tsc, generated types only, **subagents never commit**, exactly one migration `071_shipment_container` (revises `070_plate_group_collection`).

## File map
| Task | Files |
|---|---|
| T1 domain + persistence | `domain/inventory/enums.py`, `domain/inventory/shipment.py`, `infrastructure/persistence/sqlalchemy/inventory/shipment_models.py`, `.../shipment_repository.py`, `alembic/versions/071_shipment_container.py`; tests: the existing shipment domain unit test (`grep -rln "Shipment.create" tests/unit`), the shipment repo integration test (`grep -rln "Shipment" tests/integration`), `tests/unit/cascade` stays green |
| T2 application + API | `application/inventory/shipments.py`, `application/inventory/preview_shipment_import.py` (only if it constructs `ShipmentItemInput`), new `application/inventory/shipment_reads.py` (resolve-items, the two link reads, reader Protocol, `enrich_shipments`), `infrastructure/persistence/sqlalchemy/inventory/shipments_reader.py`, DI (`grep -n "CreateShipment" src/cellar/infrastructure/di/*.py`), `interface/dependencies/*`, `interface/routes/shipments.py`, `registered_plates.py`, `samples.py`, `plate_loans.py`; tests: `tests/unit/application/inventory/test_shipments*.py`, `tests/api/test_shipments.py` (+ new `tests/api/test_shipment_links.py`) |
| T3 frontend | `features/inventory/hooks/use-shipments.ts`, `components/create-shipment-dialog.tsx`, `shipment-detail.tsx`, `shipment-list.tsx`, `plate-detail.tsx`, `sample-detail.tsx`, `loan-page.tsx` (+ tests: extend the existing ones, add `shipment-links-card.test.tsx` for the shared card) |
| T4 docs (orchestrator) | `docs/domain-model/03-inventory.md` |

Waves: **W1** T1 · **W2** T2 · regen · **W3** T3.

---

### Task 1: Domain + persistence + migration 071
- [ ] Failing tests: item invariants (sample without amount / plate with amount → `ValidationError`), `direction` default + explicit inbound, `loan_id` create + `update` sentinel/clear; repo round-trip of a mixed shipment (plate item without amount, sample item with amount, inbound, loan_id pointing at a seeded loan row); raw-SQL insert of a `shipments` row without `direction` reads back `outbound` (server default).
- [ ] Implement per spec §3–§4. Model changes: `ShipmentItemModel.item_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="sample")`, `item_id: Mapped[uuid.UUID]`, amount columns `Mapped[float | None]` / `Mapped[str | None]`, `Index("ix_shipment_items_item", "item_type", "item_id")`; `ShipmentModel.direction: Mapped[str] = mapped_column(String(10), nullable=False, server_default="outbound")`, `loan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("plate_loans.id", ondelete="SET NULL"))` + `Index("ix_shipments_loan", "loan_id")`. Migration:

```python
def upgrade() -> None:
    op.add_column("shipment_items", sa.Column("item_type", sa.String(20), nullable=False, server_default="sample"))
    op.alter_column("shipment_items", "sample_id", new_column_name="item_id")
    op.alter_column("shipment_items", "amount_shipped_value", nullable=True)
    op.alter_column("shipment_items", "amount_shipped_unit", nullable=True)
    op.create_index("ix_shipment_items_item", "shipment_items", ["item_type", "item_id"])
    op.add_column("shipments", sa.Column("direction", sa.String(10), nullable=False, server_default="outbound"))
    op.add_column("shipments", sa.Column("loan_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_shipments_loan", "shipments", "plate_loans", ["loan_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_shipments_loan", "shipments", ["loan_id"])

def downgrade() -> None:
    op.execute("DELETE FROM shipment_items WHERE item_type <> 'sample'")
    op.drop_index("ix_shipments_loan", table_name="shipments")
    op.drop_constraint("fk_shipments_loan", "shipments", type_="foreignkey")
    op.drop_column("shipments", "loan_id")
    op.drop_column("shipments", "direction")
    op.drop_index("ix_shipment_items_item", table_name="shipment_items")
    op.alter_column("shipment_items", "amount_shipped_unit", nullable=False)
    op.alter_column("shipment_items", "amount_shipped_value", nullable=False)
    op.alter_column("shipment_items", "item_id", new_column_name="sample_id")
    op.drop_column("shipment_items", "item_type")
```
- [ ] Run the tests; `uv run pytest tests/unit/cascade -q` (add an `IGNORED_FKS` entry or rule only if it fails — `plate_loans` is not an admin-deletable tier); ruff.

### Task 2: Application + API
- [ ] Failing tests first (unit + API per spec §5–§6; existing `tests/api/test_shipments.py` cases move to the new item shape — read every one).
- [ ] Implement per spec §5–§6. Mirror: `application/inventory/plate_loans.py` lines ~184–215 for plate resolution + visibility; `plate_runs_reader.py` / `collection_plate_groups.py` for the reader pattern; `resolve_barcode` for plates, `SampleRepository.find_by_barcode` for samples. DI: plate repo + visibility + sample repo into `CreateShipment`/`AddShipmentItem`/`ResolveShipmentItems`; reader singleton + the two link use cases. Route placement: `GET /plates/{id}/shipments` next to `/{plate_id}/runs`; `GET /samples/{id}/shipments` in `samples.py`; `GET /plate-loans/{id}/shipments` in `plate_loans.py` (above any `:verb` routes that could shadow).
- [ ] Run unit + API (`test_shipments.py`, `test_shipment_links.py`, `test_registered_plates.py`, `test_plate_loans.py`); ruff.

### Task 3: Frontend (after regen)
- [ ] Failing tests, then implement per spec §7. A single shared `ShipmentLinksCard({ title, rows, emptyText })` in `features/inventory/components/shipment-links-card.tsx` renders the three cards (plate, sample, loan). Direction arrow: outbound `→ {org}`, inbound `← {org}` (org name via `useOrganizations` as the dialog already does). Barcode box: textarea + "Resolve" → `useResolveShipmentItems` → rows appended to the items list with a type badge; sample rows require an amount before submit.
- [ ] Run vitest for `src/features/inventory`, biome, tsc.

## Wrap-up (orchestrator)
`make migrate`; backend unit + API for touched modules; regen; W3; FE suite; browser check (create an inbound shipment with one plate + one sample by barcode, see it on the plate and sample pages; link an outbound one to a loan, see it on the loan page); commits backend + frontend (author panda-sas); review; sync note; push; #71.
