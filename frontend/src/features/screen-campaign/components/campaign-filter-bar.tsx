"use client";

/**
 * CampaignFilterBar — chip-driven filter row above the results grid (B5).
 *
 * Two chip groups:
 * - Decision: selected / deferred / rejected (toggle each)
 * - Audit: "Overridden only" boolean toggle
 *
 * The filter state lives in <CampaignBuilder> and is consumed by both this bar
 * and the AG Grid via its `isExternalFilterPresent` + `doesExternalFilterPass`.
 */

import type { CampaignResponse, CampaignResultResponse } from "../types";

export type CampaignDecisionFilter = "selected" | "deferred" | "rejected";

export interface CampaignFilters {
  decisions: Set<CampaignDecisionFilter>;
  overriddenOnly: boolean;
}

export function emptyFilters(): CampaignFilters {
  return {
    decisions: new Set(),
    overriddenOnly: false,
  };
}

/** Default filter state for the read-only closed-campaign view: only the
 *  Selected molecules. Closed campaigns are decision-frozen — the chemist
 *  almost always wants to see "what made the cut" first; rejected/deferred
 *  rows are still one chip-toggle away. */
export function closedCampaignFilters(): CampaignFilters {
  return {
    decisions: new Set(["selected"]),
    overriddenOnly: false,
  };
}

export function filtersActive(f: CampaignFilters): boolean {
  return f.decisions.size > 0 || f.overriddenOnly;
}

export function rowPassesFilters(
  result: CampaignResultResponse,
  filters: CampaignFilters,
): boolean {
  if (
    filters.decisions.size > 0 &&
    !filters.decisions.has(result.decision as CampaignDecisionFilter)
  ) {
    return false;
  }
  if (filters.overriddenOnly) {
    if (!result.measurements.some((m) => m.is_manual_override)) return false;
  }
  return true;
}

// ── UI ────────────────────────────────────────────────────────────────────────

interface CampaignFilterBarProps {
  campaign: CampaignResponse;
  filters: CampaignFilters;
  onChange: (next: CampaignFilters) => void;
  /** Optional result count rendered right-aligned. When supplied, replaces
   *  the standalone "N results" line that used to live in CampaignToolbar
   *  — saves a full row of vertical space above the grid. */
  resultCount?: number;
}

interface CountByDecision {
  selected: number;
  deferred: number;
  rejected: number;
}

function tallyCounts(results: CampaignResultResponse[]): {
  byDecision: CountByDecision;
  overridden: number;
} {
  const byDecision: CountByDecision = { selected: 0, deferred: 0, rejected: 0 };
  let overridden = 0;
  for (const r of results) {
    if (r.decision in byDecision) {
      byDecision[r.decision as keyof CountByDecision]++;
    }
    if (r.measurements.some((m) => m.is_manual_override)) overridden++;
  }
  return { byDecision, overridden };
}

const DECISION_CHIP_STYLE: Record<CampaignDecisionFilter, string> = {
  selected: "bg-green-50 text-green-800 border-green-200 hover:bg-green-100",
  deferred: "bg-yellow-50 text-yellow-800 border-yellow-200 hover:bg-yellow-100",
  rejected: "bg-red-50 text-red-800 border-red-200 hover:bg-red-100",
};

const DECISION_ACTIVE_STYLE: Record<CampaignDecisionFilter, string> = {
  selected: "bg-green-600 text-white border-green-700",
  deferred: "bg-yellow-600 text-white border-yellow-700",
  rejected: "bg-red-600 text-white border-red-700",
};

export function CampaignFilterBar({
  campaign,
  filters,
  onChange,
  resultCount,
}: CampaignFilterBarProps) {
  const { byDecision, overridden } = tallyCounts(campaign.results);

  function toggleDecision(d: CampaignDecisionFilter) {
    const next = new Set(filters.decisions);
    next.has(d) ? next.delete(d) : next.add(d);
    onChange({ ...filters, decisions: next });
  }

  function toggleOverridden() {
    onChange({ ...filters, overriddenOnly: !filters.overriddenOnly });
  }

  function clearAll() {
    onChange(emptyFilters());
  }

  const active = filtersActive(filters);

  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-3 py-2 text-xs">
      <span className="text-muted-foreground font-medium">Filter:</span>

      {(["selected", "deferred", "rejected"] as CampaignDecisionFilter[]).map((d) => {
        const isActive = filters.decisions.has(d);
        return (
          <button
            key={d}
            type="button"
            onClick={() => toggleDecision(d)}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border transition-colors ${
              isActive ? DECISION_ACTIVE_STYLE[d] : DECISION_CHIP_STYLE[d]
            }`}
          >
            <span className="capitalize">{d}</span>
            <span className="font-semibold tabular-nums">{byDecision[d]}</span>
          </button>
        );
      })}

      <span className="text-muted-foreground/50 mx-1">·</span>

      <button
        type="button"
        onClick={toggleOverridden}
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border transition-colors ${
          filters.overriddenOnly
            ? "bg-purple-600 text-white border-purple-700"
            : "bg-purple-50 text-purple-800 border-purple-200 hover:bg-purple-100"
        }`}
      >
        <span>Overridden</span>
        <span className="font-semibold tabular-nums">{overridden}</span>
      </button>

      {active && (
        <button
          type="button"
          onClick={clearAll}
          className="text-muted-foreground hover:text-foreground underline underline-offset-2"
        >
          clear all
        </button>
      )}
      {resultCount != null && (
        <span className="ml-auto text-muted-foreground tabular-nums">
          {resultCount} {resultCount === 1 ? "result" : "results"}
        </span>
      )}
    </div>
  );
}
