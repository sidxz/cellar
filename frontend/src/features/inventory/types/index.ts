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

export type SampleStatus =
  | "available"
  | "depleted"
  | "expired"
  | "quarantined"
  | "disposed";

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

export interface Batch {
  id: string;
  workspace_id: string;
  molecule_id: string;
  batch_number: string;
  salt_entry_id: string | null;
  salt_name: string | null;
  salt_smiles: string | null;
  salt_stoichiometry: number;
  formula_weight: number | null;
  purity: number | null;
  amount_value: number;
  amount_unit: string;
  source: BatchSource;
  chemist: string;
  supplier_org_id: string | null;
  vendor_catalog_number: string | null;
  vendor_lot_number: string | null;
  synthesis_date: string | null;
  expiry_date: string | null;
  appearance: string | null;
}

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

export interface Sample {
  id: string;
  workspace_id: string;
  batch_id: string;
  barcode: string;
  container_type: ContainerType;
  amount_value: number;
  amount_unit: string;
  solvent: string | null;
  status: SampleStatus;
  location_id: string | null;
  freeze_thaw_count: number;
  low_stock_threshold: number | null;
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

export interface StorageLocation {
  id: string;
  workspace_id: string;
  name: string;
  type: StorageLocationType;
  parent_id: string | null;
  barcode: string | null;
  temperature: string | null;
  rows: number | null;
  columns: number | null;
  capacity: number | null;
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
