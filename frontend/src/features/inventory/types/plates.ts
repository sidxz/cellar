import type {
  PlateStatus as GeneratedPlateStatus,
  PlateType as GeneratedPlateType,
  PlateResponse,
} from "@/shared/lib/api/model";

/** Generated from the backend OpenAPI — do not redefine shapes here (CLAUDE.md). */
export type RegisteredPlate = PlateResponse;
export type PlateType = GeneratedPlateType;
export type PlateStatus = GeneratedPlateStatus;

export const plateTypeLabels: Record<PlateType, string> = {
  compound_storage: "Compound Storage",
  mother: "Mother",
  daughter: "Daughter",
  archive: "Archive",
  assay: "Assay",
  dose_response: "Dose Response",
  replicate: "Replicate",
  control: "Control",
  cherry_pick: "Cherry Pick",
  dilution: "Dilution",
  reformatted: "Reformatted",
  pooled: "Pooled",
};

export const plateStatusLabels: Record<PlateStatus, string> = {
  registered: "Registered",
  in_use: "In Use",
  stored: "Stored",
  depleted: "Depleted",
  disposed: "Disposed",
};

/**
 * One well's assignment. Field optionality mirrors the generated
 * `WellEntryModel` so `PlateResponse.well_map` assigns without casts —
 * `batch_id` is genuinely null/absent for unresolved batch refs (CDD imports).
 */
export interface WellMapping {
  batch_id?: string | null;
  concentration_value?: number | null;
  concentration_unit?: string | null;
  /** Role of the well — sample / positive_control / negative_control / blank / reference. */
  well_type?: string;
}

export interface RegisterPlateInput {
  barcode: string;
  plate_label: string;
  format: string;
  plate_type: string;
  well_map?: Record<string, WellMapping> | null;
  storage_location_id?: string | null;
  project_id?: string | null;
  template_id?: string | null;
  parent_plate_id?: string | null;
  notes?: string | null;
}

export interface UpdatePlateInput {
  plate_label?: string;
  plate_type?: string;
  notes?: string | null;
  project_id?: string | null;
  storage_location_id?: string | null;
}

export interface DerivePlateInput {
  barcode: string;
  plate_label: string;
  plate_type?: string;
  storage_location_id?: string | null;
  project_id?: string | null;
  notes?: string | null;
}

export interface MoleculePlateEntry {
  plate_id: string;
  barcode: string;
  plate_label: string;
  well_position: string;
  concentration_value: number | null;
  concentration_unit: string | null;
  plate_type: string;
  status: string;
  storage_location_name: string | null;
}
