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
// Mirror of backend/src/cellar/domain/research_organization/enums.py.
// Backend uses StrEnum; values match the wire format exactly. If you touch
// any of these, change the corresponding StrEnum first and regenerate orval.

export type CampaignStatus = "draft" | "closed" | "superseded";

export type CampaignDecision = "selected" | "deferred" | "rejected";

export type HitCall = "hit" | "miss" | "inconclusive";

export type SelectionRule =
  | "latest_approved_run"
  | "mean_across_runs"
  | "geometric_mean"
  | "manual_pick";

export type ChannelSourceKind = "readout_data" | "dose_response_curve";

export type ValueQualifier = "=" | "<" | ">" | "nd" | "excluded";

export type QualifierHandling = "include_qualified" | "exclude_qualified" | "treat_as_limit";

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
};
