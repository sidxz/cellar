import type {
  SynthesisRequestResponse,
  SynthesisRequestSummaryResponse,
} from "@/shared/lib/api/model";

// ---------------------------------------------------------------------------
// Aggregate / summary DTOs — aliased to orval-generated types (source of truth).
// ---------------------------------------------------------------------------

export type SynthesisRequest = SynthesisRequestResponse;
export type SynthesisRequestSummary = SynthesisRequestSummaryResponse;

// ---------------------------------------------------------------------------
// Client-only narrowed enums + display-label maps (UI state, not DTO mirrors).
// The generated SynthesisRequestResponse types these fields as plain `string`.
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Client-only form-input shape for create mutations.
// ---------------------------------------------------------------------------

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
