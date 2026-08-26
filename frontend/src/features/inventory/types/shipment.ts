import type {
  CellarInterfaceRoutesShipmentsImportPreviewResponse,
  CreateShipmentRequest,
  FieldCorrectionResponse,
  OriginalRowResponse,
  ResolvedItemResponse,
  ResolvedRowResponse,
  ShipmentItemRequest,
  ShipmentItemResponse,
  ShipmentLinkResponse,
  ShipmentResponse,
  ShipmentSummaryResponse,
} from "@/shared/lib/api/model";

// ---------------------------------------------------------------------------
// Aggregate / list DTOs — aliased to orval-generated types (source of truth).
// ---------------------------------------------------------------------------

export type ShipmentItem = ShipmentItemResponse;
export type Shipment = ShipmentResponse;
export type ShipmentSummary = ShipmentSummaryResponse;
/** A shipment as seen from a plate, a sample or a loan page (newest first). */
export type ShipmentLink = ShipmentLinkResponse;
/** One pasted barcode → plate / sample, or an error. */
export type ResolvedItem = ResolvedItemResponse;

// --- Create bodies (aliased) ---

export type ShipmentItemInput = ShipmentItemRequest;
export type CreateShipmentInput = CreateShipmentRequest;

// --- CSV Import preview DTOs (aliased) ---

export type ImportFieldCorrection = FieldCorrectionResponse;
export type ImportOriginalRow = OriginalRowResponse;
export type ImportResolvedRow = ResolvedRowResponse;
export type ImportPreviewResponse = CellarInterfaceRoutesShipmentsImportPreviewResponse;

// ---------------------------------------------------------------------------
// Client-only narrowed enum + display-label map (UI state, not a DTO mirror).
// The generated ShipmentResponse types `status` as plain `string`.
// ---------------------------------------------------------------------------

export type ShipmentStatus = "preparing" | "shipped" | "in_transit" | "delivered" | "returned";

export const SHIPMENT_STATUS_LABELS: Record<ShipmentStatus, string> = {
  preparing: "Preparing",
  shipped: "Shipped",
  in_transit: "In Transit",
  delivered: "Delivered",
  returned: "Returned",
};
