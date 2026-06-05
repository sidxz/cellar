export type SynthesisRequestStatus =
  | "draft"
  | "submitted"
  | "approved"
  | "assigned"
  | "in_progress"
  | "synthesis_complete"
  | "fulfilled"
  | "rejected"
  | "cancelled"
  | "failed";

export const SYNTHESIS_REQUEST_STATUS_LABELS: Record<SynthesisRequestStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  assigned: "Assigned",
  in_progress: "In Progress",
  synthesis_complete: "Synthesis Complete",
  fulfilled: "Fulfilled",
  rejected: "Rejected",
  cancelled: "Cancelled",
  failed: "Failed",
};

export type FeasibilityStatus = "feasible" | "challenging" | "infeasible" | "alternative_proposed";

export const FEASIBILITY_STATUS_LABELS: Record<FeasibilityStatus, string> = {
  feasible: "Feasible",
  challenging: "Challenging",
  infeasible: "Infeasible",
  alternative_proposed: "Alternative Proposed",
};

export interface SynthesisRequest {
  id: string;
  workspace_id: string;
  requester_id: string;
  molecule_id: string;
  amount_value: number;
  amount_unit: string;
  purpose: string;
  priority: string;
  status: SynthesisRequestStatus;
  target_purity: number | null;
  project_id: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  assignment_type: string | null;
  assigned_to: string | null;
  assigned_org_id: string | null;
  proposed_route_id: string | null;
  feasibility_status: FeasibilityStatus | null;
  feasibility_notes: string | null;
  estimated_cost_value: number | null;
  estimated_cost_unit: string | null;
  actual_cost_value: number | null;
  actual_cost_unit: string | null;
  estimated_completion_date: string | null;
  actual_completion_date: string | null;
  fulfilled_batch_id: string | null;
  failure_reason: string | null;
  parent_request_id: string | null;
}

export interface SynthesisRequestSummary {
  id: string;
  workspace_id: string;
  requester_id: string;
  molecule_id: string;
  amount_value: number;
  amount_unit: string;
  purpose: string;
  priority: string;
  status: SynthesisRequestStatus;
  target_purity: number | null;
}

export interface CreateSynthesisRequestInput {
  molecule_id: string;
  amount_value: number;
  amount_unit: string;
  purpose: string;
  priority?: string;
  target_purity?: number | null;
  project_id?: string | null;
  parent_request_id?: string | null;
}
