# Spec: Shipment as the container for the trip — plates + samples, direction, loan link (S17)

**Date:** 2026-08-26 · **Status:** APPROVED 2026-08-26 (user: shipments should be a container holding plates/samples, tracking + records only; "go with your recommendation" = include inbound, optional loan link, records-only, visible on plate/sample/loan pages)
**Contexts touched:** Inventory (03) — `Shipment`; reads only from plate loans / plates / samples. Backend + frontend. Session **S17**. Tracking sidxz/cellar#71.
**Builds on:** S15/S16 (same shape: optional links, polymorphic ids as in `Comment`, readers + cards).

## 1. Problem
`Shipment` only carries samples (`ShipmentItem.sample_id` + amount), is implicitly outbound, has no relation to plate loans, and shows nowhere but its own pages. Cross-org lends have no logistics record; vendor deliveries of plates have no record at all; a plate/sample page cannot tell you it left the building.

## 2. Decisions
| # | Decision |
|---|---|
| Items | `ShipmentItem { item_type: plate \| sample, item_id, amount_shipped: Amount \| None }`. **Sample items require an amount; plate items carry none** (plates ship whole). Polymorphic id like `Comment.target_id` — no FK; resolved and visibility-checked at write time. |
| Direction | `Shipment.direction: outbound \| inbound`, default `outbound`. Inbound = a box arriving (vendor library, CRO return); same lifecycle words apply (`preparing` = expected, `delivered` = received). |
| Loan link | `Shipment.loan_id: UUID \| None` (FK `plate_loans` `SET NULL`) — "this box carries loan L's plates" (outbound lend or the inbound return leg). Validated: loan exists in the workspace and is visible to the caller (`_loan_visible`) → 404 otherwise. |
| Counterparty | unchanged: `destination_org_id` → provenance `Organization` (for inbound it is the *origin*; the column keeps its name, the UI labels it by direction). |
| Records only | Shipping never mutates a plate or a sample: no amount deduction, no status change; custody stays derived from loans, stock from samples. |
| Resolution | `POST /shipments/resolve-items {barcodes[]}`: each barcode → plate (existing resolver chain, then `PlateVisibilityService.can_view` — hidden == unresolved, same wording as unknown) → else `SampleRepository.find_by_barcode` → else unresolved. Returns `{barcode, item_type, item_id, label}` or `{barcode, error}`. Used by the dialog's barcode box and later by any manifest import. The existing `compound,batch,sample,amount` CSV preview stays as is (samples only). |
| Reads | `GET /plates/{id}/shipments`, `GET /samples/{id}/shipments`, `GET /plate-loans/{id}/shipments` → newest first, each row = shipment summary + (for item reads) that item's amount. Visibility: plate → plate visibility (hidden 404); sample → workspace; loan → `_loan_visible` (404). |
| Enrichment | `ShipmentItemResponse` gains `item_type`, `item_id`, `barcode`, `label` (plate: `plate_label`; sample: `batch_number` or barcode) from one batched plate fetch + one batched sample fetch per response; `amount_value/unit` become nullable. `ShipmentResponse`/`Summary` gain `direction`, `loan_id`; Summary gains `item_count`. |
| Migration | **071**: `shipment_items.item_type` (String 20, NOT NULL, server default `sample`), rename `sample_id` → `item_id`, `amount_shipped_value/unit` nullable, index `(item_type, item_id)`; `shipments.direction` (String 10, NOT NULL, server default `outbound`), `shipments.loan_id` (FK `plate_loans` `SET NULL`, indexed). Downgrade deletes plate items first, then reverses. |
| Cascade | `plate_loans` is not a Tier-1/Tier-2 admin entity (see `test_fk_coverage.py` comments) — declare nothing unless the test demands; `item_id` has no FK. |
| Not now | manifest CSV by barcode (the paste box covers it), inbound stock intake (creating samples/plates from a delivery), automatic shipment creation from a lend, notifications. |

## 3. Domain — `domain/inventory/shipment.py`, `enums.py`
`ShipmentItemType` (`PLATE`, `SAMPLE`), `ShipmentDirection` (`OUTBOUND`, `INBOUND`). `ShipmentItem.__init__(shipment_id, item_type, item_id, amount_shipped=None)` with invariants (sample ⇒ amount present; plate ⇒ amount None → `ValidationError`). `Shipment.create(..., direction=OUTBOUND, loan_id=None)`; `Shipment.update(...)` accepts `loan_id` with the `...` sentinel (as PlateGroup does). Existing state machine, events unchanged. Unit tests: item invariants, direction default, loan_id set/clear, state machine untouched.

## 4. Persistence
`ShipmentItemModel`: `item_type`, `item_id`, nullable amount columns; `ShipmentModel`: `direction`, `loan_id`. Repo mapping both ways. Migration 071 per §2 with an integration test: a pre-071 sample row survives as `item_type='sample'` (insert with the old column names before running the migration's `upgrade()` is impractical — instead the integration test asserts round-trip of a mixed shipment and that `direction` defaults to outbound on a row inserted without it via raw SQL).

## 5. Application — `application/inventory/shipments.py` (+ `shipment_reads.py`)
- `ShipmentItemInput{item_type, item_id, amount_value?, amount_unit?}` replaces `{sample_id, amount_*}`. `CreateShipment`/`AddShipmentItem` resolve each item: plate → `plate_repo.find_by_id_in_workspace` + `can_view` (hidden == `NotFoundError("RegisteredPlate")`); sample → `sample_repo.find_by_id_in_workspace` (404). `CreateShipment` takes `direction`, `loan_id` (validated as in §2); `UpdateShipment` accepts `loan_id` (sentinel) with the same validation.
- `ResolveShipmentItems(workspace_id, barcodes)` → list of `ResolvedItem | UnresolvedItem` per §2 (editor, same workspace).
- `ListShipmentsForItem(item_type, item_id)` and `ListShipmentsForLoan(loan_id)` → `ShipmentLink(shipment_id, direction, status, destination_org_id, tracking_number, shipping_date, received_date, amount_value?, amount_unit?, created_at)` via a `ShipmentsReader` Protocol (SA impl joins `shipment_items` → `shipments`), newest first. Guards + visibility per §2.
- Enrichment helper `enrich_shipments(shipments, plate_repo, sample_repo)` → labels for items (one `find_by_ids` each).

## 6. API — `interface/routes/shipments.py` (+ `registered_plates.py`, `samples.py`, `plate_loans.py`)
| Route | Shape |
|---|---|
| `POST /shipments`, `POST /shipments/{id}/items` | items `{item_type, item_id, amount_value?, amount_unit?}`; create also `direction?`, `loan_id?` |
| `PATCH /shipments/{id}` | + `loan_id?` (null clears) |
| `POST /shipments/resolve-items` | `{barcodes: str[]}` → `list[ResolvedItemResponse{barcode, item_type?, item_id?, label?, error?}]` |
| `GET /shipments`, `GET /shipments/{id}` | + `direction`, `loan_id`; items + `item_type`, `item_id`, `barcode`, `label`; summary + `item_count` |
| `GET /plates/{id}/shipments`, `GET /samples/{id}/shipments`, `GET /plate-loans/{id}/shipments` | `list[ShipmentLinkResponse]` |
API tests: extend `tests/api/test_shipments.py` (existing cases updated to the new item shape) + new cases: plate item, mixed shipment, plate item without amount ok / sample item without amount 422, hidden plate → 404, resolve-items (plate by zero-padded barcode, sample by barcode, unknown, hidden plate reported as unresolved), inbound + loan link (unknown loan 404), the three link reads incl. hidden-plate 404 and loan visibility.

## 7. Frontend
- Regen. `features/inventory/hooks/use-shipments.ts`: `useResolveShipmentItems`, `useShipmentsForPlate`, `useShipmentsForSample`, `useShipmentsForLoan`.
- `create-shipment-dialog.tsx`: **Direction** toggle (Outbound / Inbound — relabels the org field "Destination" / "From"); **Loan** optional `SearchableSelect` over `useLoans({status: "open"})` labelled with `loanTitle` (+ member name); items: the existing compound → batch → sample rows stay, plus a **Barcodes** textarea ("plates or samples, one per line") with a Resolve button → resolved rows appear with a type badge (plate rows have no amount; sample rows get amount inputs), unresolved barcodes listed in red.
- `shipment-detail.tsx`: direction badge + "carries loan → …" link; items table columns Type · Barcode (link to the plate / sample page) · Label · Amount. `shipment-list.tsx`: Direction column + item count.
- `plate-detail.tsx` and `sample-detail.tsx`: **Shipments** card — `→ WuXi · In transit · FedEx 7489… · shipped Sep 1` (arrow by direction, status badge), row links to the shipment; empty "Never shipped."
- `loan-page.tsx`: **Logistics** card under Activity — the shipments carrying this loan, same row shape; empty "No shipment recorded for this loan."
- Tests: dialog (direction toggle relabels; barcode resolve renders plate row without amount and sample row with amount; submit payload shape), detail (type column + links), the three cards (rows/empty), list column.

## 8. Docs
`docs/domain-model/03-inventory.md` Shipment section: rewrite the property tables (items polymorphic, direction, loan_id), add the reads.

## 9. Out of scope
Everything in §2 "Not now"; changing loans/samples in response to shipments; a persistent container entity (that is `StorageLocation`).
