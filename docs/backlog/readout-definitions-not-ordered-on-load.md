# A protocol's readouts come back in arbitrary order, not by display_order

**Status:** open · **Found:** 2026-10-09 browser walk of the protocol sp2-6 branch. Not caused by that branch's behaviour; the relationship predates it.

## Symptom

On the Design tab, a protocol whose readouts are stored as Signal (`display_order` 1), GI50 (2) and % inhibition (3) showed % inhibition before GI50 after a refetch. The `readout_definitions.display_order` values in the database were correct; only the order the API returned them in was wrong, and it can change between loads.

## Root cause

`ProtocolModel.readout_definitions` (`backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py`) is a `lazy="selectin"` relationship with no `order_by`, so Postgres returns the child rows in whatever order the selectin query produces (heap order, which shifts after updates). `ProtocolRepository._to_domain` (`.../protocol_repository.py`, the `for rd in model.readout_definitions` comprehension) keeps that order, the aggregate keeps it, and `interface/routes/protocols.py` serializes it unchanged. Nothing downstream sorts on `display_order` either: the Design tab renders the array as received. By contrast `aliases` on the same model declares `order_by="ProtocolAliasModel.position"`, which is why aliases are stable. `condition_definitions` has no ordering column and the same unordered relationship.

## Fix direction

Add `order_by="ReadoutDefinitionModel.display_order"` to the relationship, with a tiebreaker (`created_at` or `id`) because several readouts can share a `display_order` (the default is 0). Fixing it at the relationship covers every reader (detail, list, export, versioning, which copies `display_order`). Add a repository integration test: save readouts with out-of-order `display_order` values, update one so its heap position moves, reload, and assert the order. Check whether `condition_definitions` needs a stable order too (its model has no `display_order` or timestamp column, so it would need one first).
