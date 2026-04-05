export type SampleRequestStatus =
  | "submitted"
  | "approved"
  | "preparing"
  | "fulfilled"
  | "rejected"
  | "cancelled";

export const SAMPLE_REQUEST_STATUS_LABELS: Record<SampleRequestStatus, string> = {
  submitted: "Submitted",
  approved: "Approved",
  preparing: "Preparing",
  fulfilled: "Fulfilled",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

export type RequestPriority = "routine" | "urgent" | "critical";

export const REQUEST_PRIORITY_LABELS: Record<RequestPriority, string> = {
  routine: "Routine",
  urgent: "Urgent",
  critical: "Critical",
};

export interface SampleRequest {
  id: string;
  workspace_id: string;
  requester_id: string;
  molecule_id: string;
  batch_id: string | null;
  amount_value: number;
  amount_unit: string;
  purpose: string;
  priority: RequestPriority;
  status: SampleRequestStatus;
  assigned_to: string | null;
  fulfilled_sample_id: string | null;
  rejection_reason: string | null;
  fulfilled_at: string | null;
}

export interface CreateSampleRequestInput {
  molecule_id: string;
  batch_id?: string | null;
  amount_value: number;
  amount_unit: string;
  purpose: string;
  priority?: string;
}
