import type {
  BulkRegItemRowResponse,
  ConfirmMergesResponse as GeneratedConfirmMergesResponse,
  ListBulkRegItemsResponse as GeneratedListBulkRegItemsResponse,
  MergeDecisionResult as GeneratedMergeDecisionResult,
  PreviewBulkRegistrationResponse as GeneratedPreviewBulkRegistrationResponse,
  PreviewItem as GeneratedPreviewItem,
} from "@/shared/lib/api/model";
import type { BatchInput, Molecule } from "./index";

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
  createBatchOnDuplicate: boolean;
}

// ─── Preview (parse-only) result returned by /preview ───────────────────────
// Backend DTOs — aliased from the orval-generated model (source of truth).

export type PreviewItem = GeneratedPreviewItem;

export type PreviewBulkRegistrationResponse = GeneratedPreviewBulkRegistrationResponse;

// ─── Per-row results returned by /{wf}/items ────────────────────────────────

export type BulkRegItemAction =
  | "registered"
  | "deduplicated"
  | "disclosed"
  | "merge_candidate"
  | "conflict"
  | "error";

// Backend DTOs — aliased from the orval-generated model (source of truth).
// `action` is typed `string` on the wire; the BulkRegItemAction union above is
// the client-side narrowing used for the results filter tabs.
export type BulkRegItemRow = BulkRegItemRowResponse;

export type ListBulkRegItemsResponse = GeneratedListBulkRegItemsResponse;

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

// Backend DTOs — aliased from the orval-generated model (source of truth).
export type MergeDecisionResult = GeneratedMergeDecisionResult;

export type ConfirmMergesResponse = GeneratedConfirmMergesResponse;

// Re-export BatchInput so wizard code can import from this module
export type { Molecule, BatchInput };
