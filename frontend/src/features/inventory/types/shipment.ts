import type {
  CellarInterfaceRoutesShipmentsImportPreviewResponse,
  FieldCorrectionResponse,
  OriginalRowResponse,
  ResolvedRowResponse,
  ShipmentItemResponse,
  ShipmentResponse,
  ShipmentSummaryResponse,
} from "@/shared/lib/api/model";

// ---------------------------------------------------------------------------
// Aggregate / list DTOs — aliased to orval-generated types (source of truth).
// ---------------------------------------------------------------------------

export type ShipmentItem = ShipmentItemResponse;
export type Shipment = ShipmentResponse;
export type ShipmentSummary = ShipmentSummaryResponse;

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

// ---------------------------------------------------------------------------
// Client-only form-input shapes for create mutations.
// ---------------------------------------------------------------------------

export interface ShipmentItemInput {
  sample_id: string;
  amount_value: number;
  amount_unit: string;
}

export interface CreateShipmentInput {
  destination_org_id: string;
  carrier?: string | null;
  expected_arrival_date?: string | null;
  shipping_conditions?: string | null;
  notes?: string | null;
  items: ShipmentItemInput[];
}
