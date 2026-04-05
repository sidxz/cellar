// ─── Enums ───────────────────────────────────────────────────────────────────

export type ProtocolType =
  | "biochemical"
  | "cell_based"
  | "admet"
  | "in_vivo"
  | "analytical"
  | "physicochemical";

export const PROTOCOL_TYPE_LABELS: Record<ProtocolType, string> = {
  biochemical: "Biochemical",
  cell_based: "Cell-Based",
  admet: "ADMET",
  in_vivo: "In Vivo",
  analytical: "Analytical",
  physicochemical: "Physicochemical",
};

export type ProtocolStatus = "draft" | "active" | "retired";

export const PROTOCOL_STATUS_LABELS: Record<ProtocolStatus, string> = {
  draft: "Draft",
  active: "Active",
  retired: "Retired",
};

export type ReadoutDataType = "numeric" | "text" | "pick_list" | "file" | "date";

export const READOUT_DATA_TYPE_LABELS: Record<ReadoutDataType, string> = {
  numeric: "Numeric",
  text: "Text",
  pick_list: "Pick List",
  file: "File",
  date: "Date",
};

export type ReadoutAggregation =
  | "none"
  | "mean"
  | "median"
  | "geometric_mean"
  | "min"
  | "max";

export const READOUT_AGGREGATION_LABELS: Record<ReadoutAggregation, string> = {
  none: "None",
  mean: "Mean",
  median: "Median",
  geometric_mean: "Geometric Mean",
  min: "Min",
  max: "Max",
};

export type ReadoutNormalization =
  | "none"
  | "percent_inhibition"
  | "percent_activation"
  | "percent_control"
  | "z_score";

export const READOUT_NORMALIZATION_LABELS: Record<ReadoutNormalization, string> = {
  none: "None",
  percent_inhibition: "% Inhibition",
  percent_activation: "% Activation",
  percent_control: "% Control",
  z_score: "Z-Score",
};

export type TargetType =
  | "single_protein"
  | "protein_complex"
  | "protein_family"
  | "nucleic_acid"
  | "organism"
  | "cell_line"
  | "tissue";

export const TARGET_TYPE_LABELS: Record<TargetType, string> = {
  single_protein: "Single Protein",
  protein_complex: "Protein Complex",
  protein_family: "Protein Family",
  nucleic_acid: "Nucleic Acid",
  organism: "Organism",
  cell_line: "Cell Line",
  tissue: "Tissue",
};

export type PlateFormat = "6" | "12" | "24" | "48" | "96" | "384" | "1536";

export const PLATE_FORMAT_LABELS: Record<PlateFormat, string> = {
  "6": "6-Well",
  "12": "12-Well",
  "24": "24-Well",
  "48": "48-Well",
  "96": "96-Well",
  "384": "384-Well",
  "1536": "1536-Well",
};

export type WellType =
  | "sample"
  | "positive_control"
  | "negative_control"
  | "blank"
  | "reference";

export const WELL_TYPE_LABELS: Record<WellType, string> = {
  sample: "Sample",
  positive_control: "Positive Control",
  negative_control: "Negative Control",
  blank: "Blank",
  reference: "Reference",
};

export type RunStatus =
  | "draft"
  | "in_progress"
  | "completed"
  | "approved"
  | "rejected";

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  draft: "Draft",
  in_progress: "In Progress",
  completed: "Completed",
  approved: "Approved",
  rejected: "Rejected",
};

export type RunRelationshipType =
  | "confirmation_of"
  | "repeat_of"
  | "follow_up_to";

export const RUN_RELATIONSHIP_TYPE_LABELS: Record<RunRelationshipType, string> = {
  confirmation_of: "Confirmation Of",
  repeat_of: "Repeat Of",
  follow_up_to: "Follow-Up To",
};

export type CurveType = "ic50" | "ec50" | "ki" | "kd" | "ld50" | "td50";

export const CURVE_TYPE_LABELS: Record<CurveType, string> = {
  ic50: "IC50",
  ec50: "EC50",
  ki: "Ki",
  kd: "Kd",
  ld50: "LD50",
  td50: "TD50",
};

export type CurveClass = "full" | "partial" | "bell_shaped" | "inactive";

export const CURVE_CLASS_LABELS: Record<CurveClass, string> = {
  full: "Full",
  partial: "Partial",
  bell_shaped: "Bell-Shaped",
  inactive: "Inactive",
};

// ─── Interfaces ───────────────────────────────────────────────────────────────

export interface ReadoutDefinition {
  id: string;
  name: string;
  data_type: ReadoutDataType;
  unit: string | null;
  aggregation: ReadoutAggregation;
  precision: number | null;
  normalization: ReadoutNormalization;
  is_calculated: boolean;
  calculation_formula: string | null;
  display_order: number;
}

export interface ConditionDefinition {
  id: string;
  name: string;
  data_type: string;
  unit: string | null;
  pick_list_values: string[] | null;
}

export interface Protocol {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  protocol_type: ProtocolType;
  target_id: string | null;
  category: string | null;
  protocol_version: number;
  parent_protocol_id: string | null;
  status: ProtocolStatus;
  created_by: string;
  readout_definitions: ReadoutDefinition[];
  condition_definitions: ConditionDefinition[];
}

export interface Target {
  id: string;
  workspace_id: string;
  name: string;
  target_type: TargetType;
  organism: string | null;
  gene_name: string | null;
  uniprot_id: string | null;
  ncbi_gene_id: string | null;
  description: string | null;
  target_class: string | null;
}

export interface Run {
  id: string;
  workspace_id: string;
  protocol_id: string;
  run_date: string;
  operator: string;
  status: RunStatus;
  is_locked: boolean;
  locked_by: string | null;
  lock_reason: string | null;
  qc_metrics: Record<string, unknown> | null;
  notes: string | null;
  plate_count: number;
  performed_at_org_id: string | null;
  parent_run_id: string | null;
  run_relationship_type: RunRelationshipType | null;
  plate_format: PlateFormat | null;
  conditions: Record<string, unknown> | null;
}

export interface ReadoutData {
  id: string;
  workspace_id: string;
  run_id: string;
  well_id: string | null;
  molecule_id: string;
  batch_id: string;
  readout_definition_id: string;
  value_numeric: number | null;
  value_qualifier: string | null;
  value_text: string | null;
  is_outlier: boolean;
}

export interface DoseResponseCurve {
  id: string;
  workspace_id: string;
  molecule_id: string;
  batch_id: string;
  protocol_id: string;
  run_id: string;
  curve_type: CurveType;
  fitted_value: number;
  fitted_unit: string;
  hill_slope: number;
  top: number;
  bottom: number;
  r_squared: number;
  confidence_interval_low: number | null;
  confidence_interval_high: number | null;
  num_points: number;
  curve_class: CurveClass | null;
  raw_data: Array<Record<string, unknown>> | null;
  excluded_points: Array<Record<string, unknown>> | null;
}

// ─── Create Input Types ───────────────────────────────────────────────────────

export interface CreateReadoutDefinitionInput {
  name: string;
  data_type: ReadoutDataType;
  unit?: string | null;
  aggregation?: ReadoutAggregation;
  precision?: number | null;
  normalization?: ReadoutNormalization;
  is_calculated?: boolean;
  calculation_formula?: string | null;
  display_order?: number;
}

export interface CreateConditionDefinitionInput {
  name: string;
  data_type: string;
  unit?: string | null;
  pick_list_values?: string[] | null;
}

export interface CreateProtocolInput {
  name: string;
  protocol_type: ProtocolType;
  description?: string | null;
  target_id?: string | null;
  category?: string | null;
  readout_definitions?: CreateReadoutDefinitionInput[];
  condition_definitions?: CreateConditionDefinitionInput[];
}

export interface CreateTargetInput {
  name: string;
  target_type: TargetType;
  organism?: string | null;
  gene_name?: string | null;
  uniprot_id?: string | null;
  ncbi_gene_id?: string | null;
  description?: string | null;
  target_class?: string | null;
}

export interface CreateRunInput {
  protocol_id: string;
  run_date: string;
  plate_format?: PlateFormat | null;
  performed_at_org_id?: string | null;
  parent_run_id?: string | null;
  run_relationship_type?: RunRelationshipType | null;
  notes?: string | null;
  conditions?: Record<string, unknown> | null;
}

export interface CreateReadoutDataInput {
  run_id: string;
  molecule_id?: string;
  batch_id?: string;
  readout_definition_id?: string;
  // Human-readable alternatives (resolved server-side)
  registration_number?: string;
  batch_number?: string;
  readout_definition_name?: string;
  well_id?: string | null;
  value_numeric?: number | null;
  value_qualifier?: string | null;
  value_text?: string | null;
  is_outlier?: boolean;
}

export interface CreateDoseResponseCurveInput {
  molecule_id: string;
  batch_id: string;
  protocol_id: string;
  run_id: string;
  curve_type: CurveType;
  fitted_value: number;
  fitted_unit: string;
  hill_slope: number;
  top: number;
  bottom: number;
  r_squared: number;
  num_points: number;
  confidence_interval_low?: number | null;
  confidence_interval_high?: number | null;
  curve_class?: CurveClass | null;
  raw_data?: Array<Record<string, unknown>> | null;
  excluded_points?: Array<Record<string, unknown>> | null;
}
