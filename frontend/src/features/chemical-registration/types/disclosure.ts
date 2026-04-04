export type DisclosureStatus =
  | "pending"
  | "processing"
  | "disclosed"
  | "merged"
  | "conflict"
  | "rejected";

export const DISCLOSURE_STATUS_LABELS: Record<DisclosureStatus, string> = {
  pending: "Pending",
  processing: "Processing",
  disclosed: "Disclosed",
  merged: "Merged",
  conflict: "Conflict",
  rejected: "Rejected",
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
  disclosing_org_id: string | null;
  requested_by: string;
  requested_at: string;
  resolved_at: string | null;
  conflict_reason: string | null;
  notes: string | null;
}

export interface DisclosureOutcome {
  disclosure_request: DisclosureRequest;
  was_merged: boolean;
  merged_into_molecule_id: string | null;
}

export interface SubmitDisclosureInput {
  molecule_id: string;
  disclosed_smiles: string;
  disclosing_org_id?: string | null;
  notes?: string | null;
}

export interface MergeInput {
  target_molecule_id: string;
  reason?: string;
  notes?: string | null;
}

export interface MergeEventResponse {
  id: string;
  source_molecule_id: string;
  target_molecule_id: string;
  reason: string;
  merged_by: string;
  merged_at: string;
  snapshot: Record<string, unknown>;
  notes: string | null;
}
