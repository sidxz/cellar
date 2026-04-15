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
  fileFormat: "csv" | "sdf";
  parsedRows: BulkRow[];
  originatingOrgId: string | null;
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
