# A protocol's condition definitions come back in arbitrary order

**Status:** open · **Found:** 2026-10-09 browser walk of the protocol sp2-6 branch.

Readouts had the same bug and are fixed: `ProtocolModel.readout_definitions` now orders by `display_order`,
`created_at`, `id` (test: `backend/tests/integration/test_protocol_readout_order.py`). Conditions remain.

## Symptom

Readouts used to swap places on the Design tab after a refetch, although their `display_order` values were right.
Condition definitions can do the same, because nothing fixes their order.

## Root cause

`ProtocolModel.condition_definitions` (`backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py`)
is a `lazy="selectin"` relationship with no `order_by`, so Postgres returns rows in heap order, which shifts after
updates. `condition_definitions` has no ordering column. `created_at` exists but is identical for conditions saved
in one transaction, so it can't recover the order the chemist entered them in.

## Fix direction

Add a `display_order` column to `condition_definitions` (migration; backfill from the current row order per
protocol), set it from list position on create and add, and order the relationship by it like readouts.
