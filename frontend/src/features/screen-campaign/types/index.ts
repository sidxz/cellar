// ─── Re-exports from orval-generated model ──────────────────────────────────
// Orval emits campaign status and enums as `string` / `string | null` types
// (the backend's OpenAPI schema uses anyOf with string literals but without
// explicit enum markers, so orval resolves them as plain strings). We define
// the domain-specific string-literal union types here so the feature layer
// has a stable, named vocabulary without a runtime dep on generated code.

import type { CampaignChannelResponse } from "@/shared/lib/api/model";

export type {
  CampaignResponse,
  CampaignChannelResponse,
  CampaignResultResponse,
  CampaignMeasurementResponse,
  CreateCampaignRequest,
  UpdateCampaignRequest,
  AddChannelRequest,
  UpdateChannelRequest,
  CloseCampaignRequest,
  SupersedeRequest,
  SetResultDecisionRequest,
  OverrideCellRequest,
  AddFromCollectionRequest,
  AddFromCampaignRequest,
  AddFromRunRequest,
  AddResultsOutcomeResponse,
} from "@/shared/lib/api/model";

// ─── Domain enums ────────────────────────────────────────────────────────────
// The backend emits these as plain strings; we narrow the type here for safety.

export type CampaignStatus = "draft" | "closed" | "superseded";

export type CampaignDecision = "selected" | "deferred" | "rejected" | "pending";

export type HitCall = "hit" | "confirmed_hit" | "inactive" | "inconclusive";

export type SelectionRule = "best" | "all" | "most_recent";

export type ChannelSourceKind = "readout" | "curve";

export type ValueQualifier = "<" | ">" | "~" | "=";

export type QualifierHandling = "numeric" | "threshold" | "exclude";

// ─── View models ─────────────────────────────────────────────────────────────

export type { CampaignChannelResponse as ChannelBase } from "@/shared/lib/api/model";

/** Transient draft used in the Phase 8 channel-editor UI before committing to
 * the API. `isNew` distinguishes an unsaved row from an existing channel. */
export type ChannelEditDraft = Partial<CampaignChannelResponse> & {
  isNew?: boolean;
};

// ─── Label maps ──────────────────────────────────────────────────────────────

export const CAMPAIGN_STATUS_LABELS: Record<CampaignStatus, string> = {
  draft: "Draft",
  closed: "Closed",
  superseded: "Superseded",
};

export const CAMPAIGN_DECISION_LABELS: Record<CampaignDecision, string> = {
  selected: "Selected",
  deferred: "Deferred",
  rejected: "Rejected",
  pending: "Pending",
};

