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

export type ReadoutDataType =
  | "numeric"
  | "text"
  | "pick_list"
  | "file"
  | "date"
  | "dose_response"
  | "batch_link";

export const READOUT_DATA_TYPE_LABELS: Record<ReadoutDataType, string> = {
  numeric: "Numeric",
  text: "Text",
  pick_list: "Pick List",
  file: "File",
  date: "Date",
  dose_response: "Dose-Response (Plot)",
  batch_link: "Batch Link",
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

export type HillSlopeConstraint =
  | "unconstrained"
  | "fixed_at_one"
  | "positive_only"
  | "negative_only";

export const HILL_SLOPE_CONSTRAINT_LABELS: Record<HillSlopeConstraint, string> = {
  unconstrained: "Unconstrained",
  fixed_at_one: "Fixed at 1",
  positive_only: "Positive Only",
  negative_only: "Negative Only",
};

export type NormalizationScope = "per_plate" | "per_run" | "none";

export const NORMALIZATION_SCOPE_LABELS: Record<NormalizationScope, string> = {
  per_plate: "Per Plate",
  per_run: "Per Run",
  none: "None",
};

export type InterceptKind = "ic" | "ec";
export type InterceptBasis = "relative_percent" | "absolute";

export interface InterceptSpec {
  kind: InterceptKind;
  level: number;
  basis: InterceptBasis;
  label?: string | null;
}

export interface InterceptValue {
  spec: InterceptSpec;
  value: number;
  confidence_interval_low: number | null;
  confidence_interval_high: number | null;
  at_bound: boolean;
}

export interface DoseResponseConfig {
  curve_type: CurveType;
  /** null means "use the well's concentration as the X-axis" (default). */
  x_readout_name: string | null;
  y_readout_name: string;
  /** Picks which formula's output feeds the fit when the Y readout def emits
   *  multiple normalized columns (e.g. raw + %inh + z-score). null selects
   *  the raw layer. Must be in the Y readout's `normalizations` set. */
  y_normalization?: ReadoutNormalization | null;
  /** Per-spec intercepts derived from the same Hill fit. Empty / undefined
   *  defaults server-side to a single 50% intercept based on `curve_type`. */
  intercepts?: InterceptSpec[];
  hill_slope_constraint: HillSlopeConstraint;
  activity_threshold: number | null;
  normalization_scope: NormalizationScope;
  /** Hard lock on the upper plateau (vary=False on top). Mutually exclusive
   *  with `top_constraint_min`/`top_constraint_max`. */
  top_constraint: number | null;
  bottom_constraint: number | null;
  /** Range bounds on the upper plateau — the optimizer picks the best
   *  `top` inside `[top_constraint_min, top_constraint_max]`. Typical
   *  default is [85, 110] for percent-normalized readouts. */
  top_constraint_min: number | null;
  top_constraint_max: number | null;
  bottom_constraint_min: number | null;
  bottom_constraint_max: number | null;
  /** Explicit Hill range; overrides the implicit bounds set by
   *  `hill_slope_constraint`. Typical default is [0.9, 1.1]. */
  hill_slope_min: number | null;
  hill_slope_max: number | null;
  /** Auto-outlier removal threshold (residual > σ × SD). Default 3.0;
   *  null disables. */
  outlier_sigma: number | null;
  /** Curve-classification thresholds. Defaults are calibrated for normalized
   *  (% inhibition / % activation / % control) Y axes; override per-protocol
   *  for raw-signal assays (fluorescence, luminescence, HTRF, etc.). All
   *  optional with `?:` for back-compat with old protocol rows. */
  inactive_threshold?: number;
  full_r2_min?: number;
  full_top_min?: number;
  full_bottom_max?: number;
  partial_r2_min?: number;
}

// ─── Interfaces ───────────────────────────────────────────────────────────────

export interface ReadoutDefinition {
  id: string;
  name: string;
  /** Optional documentation surfaced in the readout-data table header
   *  tooltip, the import wizard column hint, and the viewer dialog.
   *  Pure cosmetic — editable on unlocked ACTIVE. */
  description: string | null;
  data_type: ReadoutDataType;
  unit: string | null;
  aggregation: ReadoutAggregation;
  precision: number | null;
  /** List of formulas this def emits. Empty = raw / no normalization. */
  normalizations: ReadoutNormalization[];
  is_calculated: boolean;
  calculation_formula: string | null;
  display_order: number;
  /** Pick-list values for PICK_LIST data_type. Each item is
   *  `{label, color?}` where color is a 7-char hex (#rrggbb) or null
   *  for "auto" (FE derives a stable color from the label hash). The
   *  shape diverges from ConditionDefinition (which stays string[]) —
   *  colors are only meaningful for measurement classifications, not
   *  condition variables. */
  pick_list_values: PickListValue[] | null;
  dose_response_config: DoseResponseConfig | null;
}

export interface PickListValue {
  label: string;
  color?: string | null;
}

export interface ConditionDefinition {
  id: string;
  name: string;
  data_type: string;
  unit: string | null;
  pick_list_values: string[] | null;
}

export interface OntologyAnnotationTerm {
  term_id: string;
  label: string;
  ontology_source: string;
  uri: string | null;
}

export interface OntologyAnnotation {
  slot_name: string;
  terms: OntologyAnnotationTerm[];
}

export type DoseUnit = "uM" | "nM" | "mM" | "mg/mL";

export const DOSE_UNIT_LABELS: Record<DoseUnit, string> = {
  uM: "µM",
  nM: "nM",
  mM: "mM",
  "mg/mL": "mg/mL",
};

/** What raw signal POS control wells produce. Drives % Inhibition,
 *  % Activation, % Control, and Z-score formula dispatch. */
export type PosControlSignal = "high" | "low";

export const POS_CONTROL_SIGNAL_LABELS: Record<PosControlSignal, string> = {
  high: "High (POS = uninhibited / DMSO)",
  low: "Low (POS = known inhibitor / blank)",
};

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
  /** Canonical dose unit for all wells + IC50 fits of this protocol's runs. */
  dose_unit: DoseUnit;
  pos_control_signal: PosControlSignal;
  readout_definitions: ReadoutDefinition[];
  condition_definitions: ConditionDefinition[];
  control_layouts: Record<string, string> | null;
  ontology_annotations: Record<string, OntologyAnnotationTerm[]> | null;
  project_ids: string[];
  recommended_hit_criteria: HitCriterion[] | null;
  /** Workflow-state freeze gate, orthogonal to status. While locked,
   *  every mutation API returns 409 until ``unlock`` is called. */
  is_locked: boolean;
  locked_by: string | null;
  lock_reason: string | null;
  locked_at: string | null;
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
  /** ISO datetime — wall-clock creation time, used for same-day disambiguation. */
  created_at: string;
  operator: string;
  status: RunStatus;
  is_locked: boolean;
  locked_by: string | null;
  lock_reason: string | null;
  qc_metrics: Record<string, unknown> | null;
  notes: string | null;
  plate_count: number;
  /** Plate barcodes attached to the run, in plate_number order. */
  plate_barcodes: string[];
  molecule_count: number;
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
  molecule_id: string | null;
  registration_number: string | null;
  /** Molecule.name (free-text label). May equal registration_number for
   * compounds registered without a meaningful name. */
  molecule_name: string | null;
  /** Custom-type identifiers (synonyms / common names) for the molecule. */
  synonyms: string[];
  batch_id: string | null;
  batch_number: string | null;
  readout_definition_id: string;
  value_numeric: number | null;
  value_qualifier: string | null;
  value_text: string | null;
  is_outlier: boolean;
  is_computed: boolean;
}

export interface DoseResponseCurve {
  id: string;
  workspace_id: string;
  molecule_id: string;
  /** Canonical reg ID (e.g. "CV-00602") — primary label in DR table. */
  registration_number: string | null;
  molecule_name: string | null;
  /** Vendor / external aliases — shown next to the reg id. */
  synonyms: string[];
  smiles: string | null;
  batch_id: string;
  batch_number: string | null;
  protocol_id: string;
  run_id: string;
  /** The DR readout-def the curve was fitted from — identity-bearing on
   *  multi-DR protocols where two DRs may share a curve_type. */
  readout_definition_id: string;
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
  /** Machine-readable fit-quality codes; rendered as amber badges.
   *  Known values: "ec50_at_bound", "ec50_outside_dose_range", "low_r_squared". */
  fit_quality_warnings?: string[];
  /** Per-spec intercepts derived from the same Hill fit (e.g. IC50, IC90).
   *  Legacy single-intercept curves omit this; consumers fall back to
   *  `fitted_value` for the headline number. */
  intercept_values?: InterceptValue[];
  /** Non-representative contributing curves on aggregate-mode cells
   *  (MEAN_ACROSS_RUNS / GEOMETRIC_MEAN). The chart overlays them muted
   *  underneath the primary. Absent on LATEST / BEST_R_SQUARED.
   *  Loose record shape because the chart re-types via AdditionalCurve at
   *  the binding edge. */
  additional_curves?: Array<Record<string, unknown>> | null;
  /** Aggregate marker — present only on aggregate-mode cells. Carries
   *  marker_x / marker_label / unit so the chart can draw a single
   *  vertical line at the cell value and suppress the per-curve
   *  intercept dashed lines (rep's intercept ≠ aggregate value). */
  aggregate?: { marker_x: number; marker_label: string; unit: string } | null;
}

// ─── Plate Template ─────────────────────────────────────────────────────────

export type WellDesignation =
  | "compound"
  | "positive_control"
  | "negative_control"
  | "empty";

export const WELL_DESIGNATION_LABELS: Record<WellDesignation, string> = {
  compound: "Compound",
  positive_control: "Positive Control",
  negative_control: "Negative Control",
  empty: "Empty",
};

export interface PlateTemplate {
  id: string;
  workspace_id: string;
  name: string;
  format: PlateFormat;
  template_map: Record<string, WellDesignation>;
  description: string | null;
  created_by: string;
}

export interface CreatePlateTemplateInput {
  name: string;
  format: PlateFormat;
  template_map: Record<string, WellDesignation>;
  description?: string | null;
}

export interface UpdatePlateTemplateInput {
  name?: string;
  format?: PlateFormat;
  template_map?: Record<string, WellDesignation>;
  description?: string | null;
}

// ─── Create Input Types ───────────────────────────────────────────────────────

export interface CreateReadoutDefinitionInput {
  name: string;
  data_type: ReadoutDataType;
  unit?: string | null;
  aggregation?: ReadoutAggregation;
  precision?: number | null;
  /** Preferred: list of formulas this def emits. Empty = no normalization. */
  normalizations?: ReadoutNormalization[];
  /** Legacy single-value field. Lifted server-side when normalizations is omitted. */
  normalization?: ReadoutNormalization;
  description?: string | null;
  is_calculated?: boolean;
  calculation_formula?: string | null;
  display_order?: number;
  /** Pick-list values: each item is `{label, color?}` or a bare string
   *  (legacy). The backend's _normalize_pick_list_values lifts strings
   *  to dicts. Color is optional — null means "auto" (hash-derived). */
  pick_list_values?: Array<PickListValue | string> | null;
  dose_response_config?: DoseResponseConfig | null;
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
  dose_unit?: DoseUnit;
  pos_control_signal?: PosControlSignal;
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

export interface UpdateTargetInput {
  name?: string | null;
  target_type?: string | null;
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
  plate_template_id?: string | null;
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

// ─── Condition Grouping ──────────────────────────────────────────────────────

export interface AggregatedReadoutResponse {
  readout_definition_id: string;
  name: string;
  value: number;
  unit: string | null;
  aggregation: string;
  count: number;
}

export interface ConditionGroupResponse {
  condition_value: string;
  run_count: number;
  aggregated_readouts: AggregatedReadoutResponse[];
}

export interface ConditionGroupsResponse {
  condition_name: string;
  groups: ConditionGroupResponse[];
}

// ─── Refit / Classify Input Types ────────────────────────────────────────────

export interface RefitDoseResponseInput {
  excluded_point_indices: number[];
  hill_slope_constraint?: string | null;
  top_constraint?: number | null;
  bottom_constraint?: number | null;
  /** Phase B per-curve overrides. Set `override_<param>` true when the client
   *  controls that param's mode end-to-end (Free/Range/Lock); false inherits
   *  from the protocol's config. */
  override_top?: boolean;
  top_constraint_min?: number | null;
  top_constraint_max?: number | null;
  override_bottom?: boolean;
  bottom_constraint_min?: number | null;
  bottom_constraint_max?: number | null;
  override_hill?: boolean;
  hill_slope_min?: number | null;
  hill_slope_max?: number | null;
}

export interface ClassifyDoseResponseInput {
  curve_class: string;
}

// ─── Plate Setup ─────────────────────────────────────────────────────────────

export interface PlateMapWell {
  well_id: string;
  position: string;
  row: string;
  column: number;
  well_type: string;
  molecule_id: string | null;
  molecule_name: string | null;
  synonyms: string[];
  smiles: string | null;
  batch_id: string | null;
  batch_number: string | null;
  /** Dose value in the protocol's dose_unit (carried at the response root). */
  dose: number | null;
}

export interface PlateMapSummary {
  total_wells: number;
  sample_wells: number;
  control_wells: number;
  compounds: number;
  concentrations_per_compound: number;
  replicates: number;
}

export interface PlateData {
  plate_id: string;
  plate_number: number;
  format: string;
  wells: PlateMapWell[];
  summary: PlateMapSummary;
}

export interface PlateMapResponse {
  run_id: string;
  /** Protocol's dose_unit. All `wells[].dose` values are in this unit. */
  dose_unit: DoseUnit;
  plates: PlateData[];
}

// ─── Hit Criteria + Protocol Stats + Activity ───────────────────────────────

export interface InterceptKey {
  kind: "ec" | "ic";
  level: number;
}

export interface HitCriterion {
  readout_name: string;
  operator: "gt" | "lt" | "gte" | "lte" | "in";
  value: number | string[];
  intercept_key?: InterceptKey | null;
}

export interface RunCountsResponse {
  total: number;
  draft: number;
  in_progress: number;
  completed: number;
  approved: number;
  rejected: number;
}

export interface LatestRunResponse {
  id: string;
  run_date: string;
  status: RunStatus;
  plate_format: PlateFormat | null;
  plate_count: number;
  compound_count: number;
  z_prime: number | null;
}

export interface ProtocolStats {
  run_counts: RunCountsResponse;
  compound_count: number;
  hit_count: number | null;
  hit_criteria_applied: boolean;
  latest_run: LatestRunResponse | null;
}

export interface CurveParams {
  hill_slope: number;
  top: number;
  bottom: number;
  fitted_value: number;
  r_squared: number;
  /** Per-spec intercepts (EC50, EC90, IC10, ...). Empty list on legacy
   *  curves; the FE activity grid renders one column per intercept and
   *  reads values via `findInterceptValue`. */
  intercept_values?: InterceptValue[];
}

export interface ReadoutValue {
  best: number | null;
  mean: number | null;
  curve_class?: CurveClass | null;
  curve_params?: CurveParams | null;
  data_points?: Array<{ x: number; y: number }> | null;
  n?: number | null;
  sd?: number | null;
}

export interface ReadoutDefInfo {
  name: string;
  data_type: string;
  unit: string | null;
  best_direction: "high" | "low";
  /** For ``dose_response`` readouts: the protocol's declared intercept
   *  specs, drives the per-readout dynamic column set on the activity
   *  grid (EC50, EC90, IC10, ...). Empty for numeric readouts. */
  intercepts?: InterceptSpec[];
}

export interface CompoundActivity {
  molecule_id: string;
  molecule_name: string;
  registration_number: string;
  run_count: number;
  last_tested: string | null;
  smiles: string | null;
  batch_number: string | null;
  synonyms: string[];
  readouts: Record<string, ReadoutValue>;
}

export interface ActivitySummaryV2 {
  items: CompoundActivity[];
  readout_definitions: ReadoutDefInfo[];
  total_compounds: number;
}

// ─── Compound Flags ─────────────────────────────────────────────────────────

export type FlagType = "star" | "outlier" | "follow_up";

export const FLAG_TYPE_LABELS: Record<FlagType, string> = {
  star: "Star",
  outlier: "Outlier",
  follow_up: "Follow-Up",
};

export interface CompoundFlag {
  id: string;
  workspace_id: string;
  molecule_id: string;
  protocol_id: string;
  flagged_by: string;
  flag_type: FlagType;
  note: string | null;
  created_at: string;
}
