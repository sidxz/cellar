export type DisclosureStatus =
  | "pending"
  | "processing"
  | "disclosed"
  | "merged"
  | "conflict"
  | "rejected"
  | "pending_confirmation";

export const DISCLOSURE_STATUS_LABELS: Record<DisclosureStatus, string> = {
  pending: "Pending",
  processing: "Processing",
  disclosed: "Disclosed",
  merged: "Merged",
  conflict: "Conflict",
  rejected: "Rejected",
  pending_confirmation: "Awaiting Confirmation",
};

export interface DisclosureRequest {
  id: string;
  bulk_disclosure_id: string | null;
  molecule_id: string;
  disclosed_smiles: string;
  canonical_smiles: string | null;
  inchi_key: string | null;
  status: DisclosureStatus;
  resolution_type: string | null;
  resolved_to_molecule_id: string | null;
  matched_molecule_id: string | null;
  disclosing_org_id: string | null;
  scientist_name: string | null;
  requested_by: string;
  requested_at: string;
  resolved_at: string | null;
  conflict_reason: string | null;
  notes: string | null;
  version: number;
}

export interface DisclosureOutcome {
  disclosure_request: DisclosureRequest;
  was_merged: boolean;
  merged_into_molecule_id: string | null;
  needs_confirmation: boolean;
  matched_molecule_id: string | null;
}

export interface SubmitDisclosureInput {
  molecule_id: string;
  disclosed_smiles: string;
  disclosing_org_id?: string | null;
  scientist_name?: string | null;
  auto_approve?: boolean;
  notes?: string | null;
}

// ---------------------------------------------------------------------------
// Merge impact preview
// ---------------------------------------------------------------------------

export interface MoleculeSummary {
  id: string;
  registration_number: string;
  name: string;
  structure_status: string;
}

export interface MergeImpactCategory {
  name: string;
  label: string;
  count: number;
  items: Record<string, unknown>[];
  is_blocker: boolean;
}

export interface MergeImpact {
  source: MoleculeSummary;
  target: MoleculeSummary;
  categories: MergeImpactCategory[];
  blockers: string[];
}

export interface MergeInput {
  target_molecule_id: string;
  reason?: string;
  notes?: string | null;
}

// Backend DTO — aliased from the orval-generated model (source of truth).
export type MergeEventResponse = import("@/shared/lib/api/model").MergeEventResponse;
