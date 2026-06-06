import type { SampleRequestResponse } from "@/shared/lib/api/model";

// ---------------------------------------------------------------------------
// Aggregate DTO — aliased to the orval-generated type (source of truth).
// ---------------------------------------------------------------------------

export type SampleRequest = SampleRequestResponse;

// ---------------------------------------------------------------------------
// Client-only narrowed enums + display-label maps (UI state, not DTO mirrors).
// The generated SampleRequestResponse types `status`/`priority` as `string`.
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Client-only form-input shape for create mutations.
// ---------------------------------------------------------------------------

export interface CreateSampleRequestInput {
  molecule_id: string;
  batch_id?: string | null;
  amount_value: number;
  amount_unit: string;
  purpose: string;
  priority?: string;
}
