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
