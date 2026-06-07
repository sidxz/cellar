import type {
  ActivityItemResponse,
  BatchListItemResponse,
  BatchResponse,
  InventorySummaryResponse,
  SampleListItemResponse,
  SampleResponse,
  StorageLocationResponse,
  StorageLocationWithCountResponse,
} from "@/shared/lib/api/model";
import type { BatchIdentifierResponse } from "@/shared/lib/api/model/batchIdentifierResponse";
export type { BatchIdentifierResponse };

export type {
  BulkAddBatchIdentifiersRequest,
  BulkAddBatchIdentifiersResponse,
  BulkIdentifierRowBody,
  RowOutcomeResponse,
} from "@/shared/lib/api/model";

// ---------------------------------------------------------------------------
// Aggregate / list DTOs — aliased to orval-generated types (source of truth).
// ---------------------------------------------------------------------------

export type Batch = BatchResponse;
export type Sample = SampleResponse;
export type StorageLocation = StorageLocationResponse;
export type StorageLocationWithCount = StorageLocationWithCountResponse;
export type BatchListItem = BatchListItemResponse;
export type SampleListItem = SampleListItemResponse;
export type ActivityItem = ActivityItemResponse;
export type InventorySummary = InventorySummaryResponse;

// ---------------------------------------------------------------------------
// Client-only narrowed enums + display-label maps (UI state, not DTO mirrors).
// The generated DTOs type these fields as plain `string`; these unions drive
// the controlled-vocabulary label lookups and form selects in the UI.
// ---------------------------------------------------------------------------

export type BatchSource = "synthesized" | "purchased" | "donated" | "natural_extract";

export const BATCH_SOURCE_LABELS: Record<BatchSource, string> = {
  synthesized: "Synthesized",
  purchased: "Purchased",
  donated: "Donated",
  natural_extract: "Natural Extract",
};

export type ContainerType = "vial" | "tube" | "plate_well" | "ampule" | "bag";

export const CONTAINER_TYPE_LABELS: Record<ContainerType, string> = {
  vial: "Vial",
  tube: "Tube",
  plate_well: "Plate Well",
  ampule: "Ampule",
  bag: "Bag",
};

export type SampleStatus = "available" | "depleted" | "expired" | "quarantined" | "disposed";

export const SAMPLE_STATUS_LABELS: Record<SampleStatus, string> = {
  available: "Available",
  depleted: "Depleted",
  expired: "Expired",
  quarantined: "Quarantined",
  disposed: "Disposed",
};

export type StorageLocationType =
  | "site"
  | "building"
  | "room"
  | "freezer"
  | "refrigerator"
  | "shelf"
  | "rack"
  | "box"
  | "drawer";

// ---------------------------------------------------------------------------
// Client-only form-input shapes for create/update mutations.
// ---------------------------------------------------------------------------

export interface CreateBatchInput {
  molecule_id: string;
  source: string;
  amount_value: number;
  amount_unit: string;
  salt_entry_id?: string | null;
  salt_name?: string | null;
  salt_smiles?: string | null;
  salt_stoichiometry?: number;
  formula_weight?: number | null;
  purity?: number | null;
  supplier_org_id?: string | null;
  appearance?: string | null;
}

export interface UpdateBatchInput {
  salt_entry_id?: string | null;
  salt_name?: string | null;
  salt_smiles?: string | null;
  salt_stoichiometry?: number | null;
  formula_weight?: number | null;
  purity?: number | null;
  amount_value?: number | null;
  amount_unit?: string | null;
  appearance?: string | null;
  expiry_date?: string | null;
  notebook_reference?: string | null;
  storage_conditions_notes?: string | null;
}

export interface CreateSampleInput {
  batch_id: string;
  barcode: string;
  container_type: string;
  amount_value: number;
  amount_unit: string;
  solvent?: string | null;
  location_id?: string | null;
  low_stock_threshold?: number | null;
}

export interface CreateStorageLocationInput {
  name: string;
  type: string;
  parent_id?: string | null;
  barcode?: string | null;
  temperature?: string | null;
  rows?: number | null;
  columns?: number | null;
  capacity?: number | null;
}

export interface UpdateStorageLocationInput {
  name?: string | null;
  barcode?: string | null;
  temperature?: string | null;
  rows?: number | null;
  columns?: number | null;
  capacity?: number | null;
}

export type { PaginatedResponse } from "@/shared/types/pagination";
