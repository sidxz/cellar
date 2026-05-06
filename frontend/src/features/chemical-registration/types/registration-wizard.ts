import type { Molecule, BatchInput } from "./index";

export type WizardMode = "single" | "bulk";

export type RegistrationAction =
  | "registered"
  | "deduplicated"
  | "disclosed"
  | "merge_candidate"
  | "conflict";

export interface ExternalIdentifierInput {
  identifier: string;
  identifier_type: string;
}

export interface SingleInput {
  name: string;
  smiles: string | null;
  moleculeType: string;
  originatingOrgId: string | null;
  externalIds: ExternalIdentifierInput[];
  customFields: Record<string, unknown>;
  disclosureMode: boolean;
  moleculeId: string | null;
  // Disclosure provenance fields
  scientistName: string;
  disclosingOrgId: string | null;
  notes: string;
}

export interface BulkRow {
  rowIndex: number;
  name: string | null;
  smiles: string | null;
  moleculeType: string;
  externalIds: { identifier: string; identifier_type: string }[];
  amountValue: number | null;
  amountUnit: string;
  saltCode: string | null;
  purity: number | null;
  batchSource: string;
  appearance: string | null;
  error: string | null;
}

export interface BulkInput {
  file: File | null;
  fileFormat: "csv" | "xlsx" | "sdf";
  parsedRows: BulkRow[];
  originatingOrgId: string | null;
}

// ─── Preview (parse-only) result returned by /preview ───────────────────────

export interface PreviewItem {
  row_index: number;
  name: string | null;
  smiles: string | null;
  molecule_type: string;
  external_ids: { identifier: string; identifier_type: string }[];
  amount_value: number | null;
  amount_unit: string;
  salt_code: string | null;
  salt_stoichiometry: number;
  purity: number | null;
  batch_source: string;
  appearance: string | null;
  error: string | null;
}

export interface PreviewBulkRegistrationResponse {
  total_count: number;
  error_count: number;
  items: PreviewItem[];
}

// ─── Per-row results returned by /{wf}/items ────────────────────────────────

export type BulkRegItemAction =
  | "registered"
  | "deduplicated"
  | "disclosed"
  | "merge_candidate"
  | "conflict"
  | "error";

export interface BulkRegItemRow {
  row_index: number;
  action: BulkRegItemAction;
  success: boolean;
  molecule_id: string | null;
  molecule_name: string | null;
  registration_number: string | null;
  batch_id: string | null;
  batch_number: string | null;
  error: string | null;
}

export interface ListBulkRegItemsResponse {
  rows: BulkRegItemRow[];
  total: number;
  limit: number;
  offset: number;
}

export type JobStatus = "pending" | "processing" | "completed" | "failed";

export interface BulkProgress {
  bulk_reg_id: string;
  status: JobStatus;
  total_count: number;
  registered_count: number;
  duplicate_count: number;
  error_count: number;
  disclosed_count: number;
  merge_candidate_count: number;
  conflict_count: number;
  chunks_processed: number;
  chunks_total: number;
  merge_candidates: MergeCandidateRef[];
}

export interface MergeCandidateRef {
  row_index: number;
  molecule_id: string;
  matched_molecule_id: string;
  disclosure_id: string;
}

export interface MergeDecision {
  disclosure_id: string;
  action: "confirm" | "reject";
  reason?: string;
}

export interface MergeDecisionResult {
  disclosure_id: string;
  action: string;
  success: boolean;
  error: string | null;
  merged_into_molecule_id: string | null;
}

export interface ConfirmMergesResponse {
  results: MergeDecisionResult[];
  confirmed_count: number;
  rejected_count: number;
  error_count: number;
}

// Re-export BatchInput so wizard code can import from this module
export type { Molecule, BatchInput };
