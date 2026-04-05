export type ShipmentStatus =
  | "preparing"
  | "shipped"
  | "in_transit"
  | "delivered"
  | "returned";

export const SHIPMENT_STATUS_LABELS: Record<ShipmentStatus, string> = {
  preparing: "Preparing",
  shipped: "Shipped",
  in_transit: "In Transit",
  delivered: "Delivered",
  returned: "Returned",
};

export interface ShipmentItem {
  id: string;
  sample_id: string;
  amount_value: number;
  amount_unit: string;
}

export interface Shipment {
  id: string;
  workspace_id: string;
  destination_org_id: string;
  sender_id: string;
  tracking_number: string | null;
  carrier: string | null;
  shipping_date: string | null;
  expected_arrival_date: string | null;
  received_date: string | null;
  shipping_conditions: string | null;
  status: ShipmentStatus;
  notes: string | null;
  items: ShipmentItem[];
}

export interface ShipmentSummary {
  id: string;
  workspace_id: string;
  destination_org_id: string;
  tracking_number: string | null;
  carrier: string | null;
  status: ShipmentStatus;
  item_count: number;
}

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

// --- CSV Import preview types ---

export interface ImportFieldCorrection {
  field: string;
  original: string;
  corrected: string;
  reason: string;
}

export interface ImportOriginalRow {
  compound: string;
  batch: string;
  sample: string;
  amount: string;
}

export interface ImportResolvedRow {
  row_number: number;
  status: "valid" | "corrected" | "error";
  original: ImportOriginalRow;
  compound_id: string | null;
  compound_display: string | null;
  batch_id: string | null;
  batch_display: string | null;
  sample_id: string | null;
  sample_display: string | null;
  amount_value: number | null;
  amount_unit: string | null;
  corrections: ImportFieldCorrection[];
  errors: string[];
}

export interface ImportPreviewResponse {
  rows: ImportResolvedRow[];
  total: number;
  valid_count: number;
  corrected_count: number;
  error_count: number;
}
