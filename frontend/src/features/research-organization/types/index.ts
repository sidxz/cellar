// ─── Enums ───────────────────────────────────────────────────────────────────

export type ProjectStatus = "active" | "archived";

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  active: "Active",
  archived: "Archived",
};

export type SearchVisibility = "private" | "project";

export const SEARCH_VISIBILITY_LABELS: Record<SearchVisibility, string> = {
  private: "Private",
  project: "Project",
};

export type RefType =
  | "uuid"
  | "registration_number"
  | "external_id"
  | "smiles"
  | "inchi_key"
  | "name";

/** User-facing labels — excludes "uuid" which is only used internally */
export const REF_TYPE_LABELS: Record<Exclude<RefType, "uuid">, string> = {
  registration_number: "Registration Number",
  external_id: "External ID",
  smiles: "SMILES",
  inchi_key: "InChI Key",
  name: "Name",
};

// ─── Interfaces ──────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  created_by: string;
  version: number;
}

export interface Collection {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  project_id: string | null;
  owned_by_org_id: string | null;
  created_by: string;
  molecule_count: number;
  visibility: "private" | "shared";
  version: number;
}

export interface MoleculeReference {
  value: string;
  ref_type: RefType;
}

export interface UnresolvedMolecule {
  value: string;
  ref_type: RefType;
  reason: string;
}

export interface MembershipResult {
  added_count: number;
  already_present: number;
  unresolved: UnresolvedMolecule[];
}

export interface SavedSearch {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  project_id: string | null;
  query: Record<string, unknown>;
  columns: Record<string, unknown> | null;
  visibility: SearchVisibility;
  created_by: string;
  last_run_at: string | null;
  result_count: number | null;
  version: number;
}

// ─── Create / Update Input Types ─────────────────────────────────────────────

export interface CreateProjectInput {
  name: string;
  description?: string | null;
}

export interface UpdateProjectInput {
  name?: string;
  description?: string | null;
}

// ─── Project Membership ─────────────────────────────────────────────────────

export type ProjectRole = "viewer" | "editor" | "manager";

export const PROJECT_ROLE_LABELS: Record<ProjectRole, string> = {
  viewer: "Viewer",
  editor: "Editor",
  manager: "Manager",
};

export interface ProjectMember {
  project_id: string;
  user_id: string;
  role: ProjectRole;
}

export interface AddMemberInput {
  user_id: string;
  role: ProjectRole;
}

export interface UpdateMemberRoleInput {
  role: ProjectRole;
}

export interface CreateCollectionInput {
  name: string;
  description?: string | null;
  project_id?: string | null;
  owned_by_org_id?: string | null;
  visibility?: "private" | "shared";
}

export interface UpdateCollectionInput {
  name?: string;
  description?: string | null;
  project_id?: string | null;
  owned_by_org_id?: string | null;
  visibility?: "private" | "shared";
}

export interface CreateSavedSearchInput {
  name: string;
  description?: string | null;
  query: Record<string, unknown>;
  columns?: Record<string, unknown> | null;
  visibility?: SearchVisibility;
  project_id?: string | null;
}

export interface UpdateSavedSearchInput {
  name?: string;
  description?: string | null;
  query?: Record<string, unknown>;
  columns?: Record<string, unknown> | null;
  visibility?: SearchVisibility;
  project_id?: string | null;
}

// ─── Search types ───────────────────────────────────────────────────────────

export type CriterionType =
  | "text"
  | "property"
  | "structure"
  | "activity"
  | "collection"
  | "keyword_list"
  | "run_date"
  | "batch"
  | "project"
  | "selectivity"
  | "group"
  | "custom_field";
export type CustomFieldMode = "text" | "numeric";
export type TextOperator = "contains" | "equals" | "starts_with";
export type PropertyOperator = "eq" | "lt" | "lte" | "gt" | "gte" | "between";
export type StructureSearchType = "substructure" | "similarity" | "exact";

export interface TextCriterion {
  type: "text";
  field: string;
  operator: TextOperator;
  value: string;
}

export interface PropertyCriterion {
  type: "property";
  field: string;
  operator: PropertyOperator;
  value?: number;
  min?: number;
  max?: number;
}

export type SearchMode = "similar" | "scaffold_hop" | "fragment_in_target";

export interface StructureCriterion {
  type: "structure";
  // Two-way compat: keep search_type for legacy criteria, add `kind`
  search_type: StructureSearchType; // kept for compat — same values as kind
  kind?: StructureSearchType; // mirrors search_type going forward
  smarts?: string;
  smiles?: string;
  smiles_or_smarts?: string; // new substructure field
  threshold?: number;
  inchi_key?: string;
  // New similarity fields:
  mode?: SearchMode;
  // New substructure field:
  generalized?: boolean;
}

/** Per-protocol run scoping for ActivityCriterion. */
export type RunScope =
  | { mode: "any" }
  | { mode: "latest" }
  | { mode: "all" }
  | { mode: "specific"; run_id: string }
  | { mode: "date_range"; date_from?: string; date_to?: string }
  | { mode: "past_n_days"; days: number };

export type RunScopeMode = RunScope["mode"];

/** A single where-condition on an activity criterion. Multiple conditions
 *  on the same criterion are ANDed together. */
export interface ActivityWhereCondition {
  curve_type?: string;
  readout_definition_id?: string;
  /** Includes "between" — chemists routinely bracket potency. */
  operator: PropertyOperator;
  value?: number;
  min?: number;
  max?: number;
}

export interface ActivityCriterion {
  type: "activity";
  protocol_id: string;
  /** Multi-where list — preferred shape. Each row ANDed with the others. */
  where?: ActivityWhereCondition[];
  /** Run scope. Omit (or {mode:"any"}) for cross-run match — the default. */
  run_scope?: RunScope;
  /** @deprecated legacy single-where fields. Kept for saved-search compat;
   *  the composer normalizes them to a single-element where list. */
  readout_definition_id?: string;
  curve_type?: string;
  operator?: PropertyOperator;
  value?: number;
}

export interface CollectionCriterion {
  type: "collection";
  collection_id: string;
}

export interface KeywordListCriterion {
  type: "keyword_list";
  values: string[];
  ref_type: RefType;
}

export interface RunDateCriterion {
  type: "run_date";
  date_from?: string;
  date_to?: string;
}

export type BatchFieldType = "text" | "numeric" | "date";

export interface BatchCriterion {
  type: "batch";
  field_type: BatchFieldType;
  field?: string;
  operator?: TextOperator | PropertyOperator;
  value?: string | number;
  min?: number;
  max?: number;
  date_from?: string;
  date_to?: string;
}

export interface ProjectCriterion {
  type: "project";
  project_ids: string[];
}

export interface SelectivityCriterion {
  type: "selectivity";
  target_protocol_id: string;
  target_curve_type: string;
  counter_protocol_id: string;
  counter_curve_type: string;
  ratio_operator: PropertyOperator;
  ratio_value: number;
}

export interface GroupCriterion {
  type: "group";
  logic: "and" | "or";
  criteria: SearchCriterion[];
}

export interface CustomFieldCriterion {
  type: "custom_field";
  field: string;
  mode: CustomFieldMode;
  operator?: TextOperator | PropertyOperator;
  value?: string | number;
  min?: number;
  max?: number;
}

export type SearchCriterionBase =
  | TextCriterion
  | PropertyCriterion
  | StructureCriterion
  | ActivityCriterion
  | CollectionCriterion
  | KeywordListCriterion
  | RunDateCriterion
  | BatchCriterion
  | ProjectCriterion
  | SelectivityCriterion
  | GroupCriterion
  | CustomFieldCriterion;

export type SearchCriterion = SearchCriterionBase & { negate?: boolean };

export interface SearchQuery {
  criteria: SearchCriterion[];
  logic?: "and" | "or";
}

export type SortField =
  | "name"
  | "registration_number"
  | "molecular_weight"
  | "logp"
  | "tpsa"
  | "hbd"
  | "hba"
  | "created_at";
export type SortDir = "asc" | "desc";

export interface ExecuteSearchInput {
  query?: SearchQuery;
  saved_search_id?: string;
  protocol_columns?: string[];
}

export interface ActivityValue {
  value: number | null;
  qualifier: string | null;
  unit: string | null;
  source: "readout" | "dose_response";
  curve_type: string | null;
  r_squared: number | null;
  data_point_count: number;
  raw_data: Array<{ x: number; y: number }> | null;
  curve_params: CurveParams | null;
}

// ─── Report Configuration ───────────────────────────────────────────────────

export type DetailLevel = "summary" | "run_batch" | "details";
export type PlotScale = "protocol" | "min_max" | "per_molecule";
export type ImageSize = "small" | "medium" | "large";

export interface ReportConfig {
  detailLevel: DetailLevel;
  plotScale: PlotScale;
  showPlotLegend: boolean;
  imageSize: ImageSize;
  columnWidth: number;
  visibleFields: VisibleFields;
}

export interface VisibleFields {
  structure: string[];
  properties: string[];
  collections: boolean;
  molecule: string[];
  batch: string[];
  protocols: Record<string, string[]>;
  /** Per-protocol readout definition IDs to show as columns (protocol_id → rd def ids) */
  readoutColumns: Record<string, string[]>;
}

// ─── Curve Parameters ───────────────────────────────────────────────────────

export interface CurveParams {
  hill_slope: number;
  top: number;
  bottom: number;
  num_points: number;
  curve_class: string | null;
  confidence_interval_low: number | null;
  confidence_interval_high: number | null;
  /** Fit-quality warning codes (e.g. "ec50_at_bound") for compact renderers. */
  fit_quality_warnings?: string[] | null;
}

// ─── Molecule Activity Detail (side panel) ──────────────────────────────────

export interface CurveDetail {
  curve_id: string;
  run_id: string;
  batch_id: string;
  curve_type: string;
  fitted_value: number;
  fitted_unit: string;
  hill_slope: number;
  r_squared: number;
  curve_class: string | null;
  top: number;
  bottom: number;
  num_points: number;
  confidence_interval_low: number | null;
  confidence_interval_high: number | null;
  raw_data: Array<{ x: number; y: number }>;
}

export interface ProtocolCurveGroup {
  protocol_id: string;
  protocol_name: string;
  protocol_type: string;
  target_id: string | null;
  curves: CurveDetail[];
}

export interface MoleculeActivityDetail {
  molecule_id: string;
  protocols: ProtocolCurveGroup[];
}
