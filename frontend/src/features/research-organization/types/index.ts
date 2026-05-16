import type {
  AdditionalCurve,
  AggregateMarker,
} from "@/features/screening-assay/components/dose-response-figure";
import type { SelectionRule } from "@/shared/lib/api/model";

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
  /** @deprecated read-only legacy field; new criteria use smiles_or_smarts. */
  smarts?: string;
  smiles?: string;
  smiles_or_smarts?: string; // new substructure field
  threshold?: number;
  inchi_key?: string;
  // New similarity fields:
  mode?: SearchMode;
  // New substructure field:
  generalized?: boolean;
  /** Disambiguates how the BE/cartridge interprets ``smiles_or_smarts``.
   *  - "smiles" → cartridge's mol_from_smiles (aromaticity perception
   *    handled cartridge-side; works for plain drawn structures)
   *  - "smarts" → qmol_from_smarts (preserves atom lists / R-groups /
   *    "any bond" semantics — used when Ketcher SMILES export fails)
   *  Omitted ⇒ legacy defensive path (BE aromatizes the SMARTS). */
  query_kind?: "smiles" | "smarts";
}

/** Per-protocol run scoping for ActivityCriterion. */
export type RunScope =
  | { mode: "any" }
  | { mode: "latest" }
  | { mode: "all" }
  | {
      mode: "specific";
      /** Preferred multi-select shape: compound matches if it appears in any
       *  of the listed runs (OR semantics). */
      run_ids?: string[];
      /** Legacy single-run shape kept for saved-search round-trip; new UI
       *  emits `run_ids`. */
      run_id?: string;
    }
  | { mode: "date_range"; date_from?: string; date_to?: string }
  | { mode: "past_n_days"; days: number };

export type RunScopeMode = RunScope["mode"];

/** Bare `InterceptKey` mirror — see ``CurveInterceptSpec`` below for the
 *  full spec. The where-condition only needs (kind, level) to disambiguate
 *  which intercept on a multi-intercept DR readout it's filtering on. */
export interface InterceptKey {
  kind: "ic" | "ec";
  level: number;
}

/** Which data table the condition reads from.
 *  - "dr_curve": the readout-def is a dose-response readout; the value
 *    is a fitted IC50/EC50/etc. from dose_response_curves.
 *  - "readout_data": the readout-def is a raw numeric readout; the value
 *    is an aggregated reading from readout_data.
 *  - "curve_class": filters dose_response_curves.curve_class against a
 *    list of allowed classes. Used by the "Curve Class" picker entry. */
export type ActivityWhereSource = "dr_curve" | "readout_data" | "curve_class";

/** A single where-condition on an activity criterion. Multiple conditions
 *  on the same criterion are ANDed together. */
export interface ActivityWhereCondition {
  source: ActivityWhereSource;
  /** Identifies the readout-def to filter on. Required for ``dr_curve`` /
   *  ``readout_data``; ignored for ``curve_class`` (which spans all DR
   *  curves in scope). */
  readout_definition_id: string;
  /** Includes "between" — chemists routinely bracket potency. Ignored when
   *  source is ``curve_class``. */
  operator: PropertyOperator;
  value?: number;
  min?: number;
  max?: number;
  /** For ``dr_curve`` sources: picks which intercept on a multi-intercept
   *  fit (EC50, EC90, IC10, …) the operator/value applies to. ``null`` or
   *  omitted = the readout-def's primary intercept (fast path:
   *  ``fitted_value`` column). */
  intercept_key?: InterceptKey | null;
  /** For ``curve_class`` source: the allowed curve classes (multi-select).
   *  E.g. ``["full", "partial"]`` to match well-fitted curves only. */
  curve_classes?: string[];
}

export interface ActivityCriterion {
  type: "activity";
  protocol_id: string;
  /** Multi-where list — preferred shape. Each row ANDed with the others. */
  where?: ActivityWhereCondition[];
  /** Run scope. Omit (or {mode:"any"}) for cross-run match — the default. */
  run_scope?: RunScope;
  /** Single-where shape. The composer normalizes it to a single-element
   *  where list — useful for saved searches stored from the old UI. */
  source?: ActivityWhereSource;
  readout_definition_id?: string;
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
  /** Target DR readout-def (the "wanted" potency column). The readout-def
   *  identifies the column on multi-DR protocols (target IC50 vs counter
   *  IC50 are different readout-defs even when both are curve_type=ic50). */
  target_readout_definition_id: string;
  /** Counter-screen DR readout-def (the "unwanted" potency column —
   *  cytotoxicity, off-target, etc.). */
  counter_readout_definition_id: string;
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
  /** Multi-run aggregation rule. Omitted -> BE default
   *  (`latest_approved_run`). Drives how `_intercept_scalar` collapses
   *  per-(compound, intercept) rows across all in-scope runs. */
  aggregation?: SelectionRule;
}

// ─── Multi-run aggregation context (BE shape — see Tasks 5-7) ──────────────

export interface AggregateStats {
  geometric_mean: number | null;
  fold_range: number | null;
  log_value_mean: number | null;
  log_value_sd: number | null;
}

export interface RunSummary {
  run_id: string;
  run_date: string;
  curve_id: string;
  curve_class: string | null;
  r_squared: number | null;
  intercept_values: Array<{
    spec: { kind: string; level: number };
    value: number | null;
    at_bound?: boolean;
  }>;
}

export interface InterceptAggregate {
  /** {kind: "primary"} for the channel's primary intercept; otherwise
   *  matches an `InterceptSpec` shape from screening-assay. */
  spec: { kind: string; level?: number };
  selected_value: number | null;
  /** "=" | "<" | ">" | "nd" | "excluded" — same shape as `ActivityValue.qualifier`. */
  selected_qualifier: string;
  aggregate_stats: AggregateStats | null;
  disagreement_flag: boolean;
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
  /** Per-spec intercepts (EC50, EC90, IC10, ...) derived from the same Hill
   *  fit. Source: `MoleculeActivityService.enrich_molecules` flattens
   *  `DoseResponseCurve.intercept_values` so the results grid can render one
   *  sub-column per protocol intercept and look cells up via
   *  `findInterceptValue(av.intercept_values, spec)`. Null on readout-sourced
   *  ActivityValues; may be null on legacy DR curves fitted before
   *  intercepts were persisted. */
  intercept_values?: CurveInterceptValue[] | null;
  // ─── Multi-run aggregation context (BE Tasks 5-7 wire shape) ──────────
  /** Number of runs collapsed into this cell. Absent / 1 -> single-run. */
  run_count?: number;
  /** Wire `SelectionRule` string echoed back so the cell can render the
   *  rule chip without re-reading URL state. */
  selection_rule?: string | null;
  /** Per-run breakdown for "runs" tooltip / detail drawer. */
  runs?: RunSummary[] | null;
  /** Per-intercept aggregate breakdown (selected_value, fold_range, ...) */
  intercept_aggregates?: InterceptAggregate[] | null;
  /** True when collapsed runs disagree by >threshold fold (BE-driven). */
  disagreement_flag?: boolean;
  /** Non-representative contributing curves in aggregate modes
   *  (MEAN_ACROSS_RUNS / GEOMETRIC_MEAN). The cell's chart overlays them
   *  muted underneath the representative curve. Absent on
   *  LATEST_APPROVED_RUN / BEST_R_SQUARED. Mirrors CurveSnapshot's field. */
  additional_curves?: AdditionalCurve[] | null;
  /** Aggregate marker — present only on MEAN_ACROSS_RUNS / GEOMETRIC_MEAN
   *  cells. The chart draws a single vertical line at marker_x and
   *  suppresses the per-curve intercept dashed lines (per-run fitted_values
   *  don't equal the cell value in aggregate modes). Mirrors CurveSnapshot. */
  aggregate?: AggregateMarker | null;
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

/** Mirrors `screening-assay`'s InterceptValue/InterceptSpec wire shape — kept
 *  inline here to avoid a feature-cross-import for plain DTO fields. */
export interface CurveInterceptSpec {
  kind: "ic" | "ec";
  level: number;
  basis: "relative_percent" | "absolute";
  label?: string | null;
}
export interface CurveInterceptValue {
  spec: CurveInterceptSpec;
  value: number;
  confidence_interval_low: number | null;
  confidence_interval_high: number | null;
  at_bound: boolean;
}

export interface CurveDetail {
  curve_id: string;
  run_id: string;
  batch_id: string;
  /** The DR readout-def this curve was fitted from. Identity on multi-DR
   *  protocols where two DRs may share a curve_type. */
  readout_definition_id: string;
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
  /** Read-only on the search-detail panel; the run-page's curator UI is
   *  where points get excluded. Included so the shared chart can show
   *  excluded points consistently in viewer mode. */
  excluded_points?: Array<{
    x?: number;
    y?: number;
    concentration?: number;
    response?: number;
    reason?: string | null;
  }> | null;
  /** Machine-readable fit-quality codes the chemist needs to see during
   *  triage (e.g. "ec50_at_bound" — the IC50 is unreliable). */
  fit_quality_warnings?: string[];
  /** Per-spec intercepts (IC50/IC90/...) derived from the same Hill fit. */
  intercept_values?: CurveInterceptValue[];
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
