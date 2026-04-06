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

export const REF_TYPE_LABELS: Record<RefType, string> = {
  uuid: "UUID",
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
  project_id: string | null;
  query: Record<string, unknown>;
  columns: Record<string, unknown> | null;
  visibility: SearchVisibility;
  created_by: string;
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

export interface CreateCollectionInput {
  name: string;
  description?: string | null;
  project_id?: string | null;
  owned_by_org_id?: string | null;
}

export interface UpdateCollectionInput {
  name?: string;
  description?: string | null;
  project_id?: string | null;
  owned_by_org_id?: string | null;
}

export interface CreateSavedSearchInput {
  name: string;
  query: Record<string, unknown>;
  columns?: Record<string, unknown> | null;
  visibility?: SearchVisibility;
  project_id?: string | null;
}

export interface UpdateSavedSearchInput {
  name?: string;
  query?: Record<string, unknown>;
  columns?: Record<string, unknown> | null;
  visibility?: SearchVisibility;
  project_id?: string | null;
}

// ─── Search types ───────────────────────────────────────────────────────────

export type CriterionType = "text" | "property" | "structure" | "activity" | "collection" | "keyword_list" | "run_date";
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

export interface StructureCriterion {
  type: "structure";
  search_type: StructureSearchType;
  smarts?: string;
  smiles?: string;
  threshold?: number;
  inchi_key?: string;
}

export interface ActivityCriterion {
  type: "activity";
  protocol_id: string;
  readout_definition_id?: string;
  curve_type?: string;
  operator: PropertyOperator;
  value: number;
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

export type SearchCriterion =
  | TextCriterion
  | PropertyCriterion
  | StructureCriterion
  | ActivityCriterion
  | CollectionCriterion
  | KeywordListCriterion
  | RunDateCriterion;

export interface SearchQuery {
  criteria: SearchCriterion[];
  logic: "and" | "or";
}

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
}
