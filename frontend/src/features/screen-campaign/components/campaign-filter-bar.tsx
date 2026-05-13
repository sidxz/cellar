"use client";

/**
 * CampaignFilterBar — chip-driven filter row above the results grid (B5).
 *
 * Three chip groups:
 * - Decision: selected / deferred / rejected (toggle each)
 * - Hit status: hits / non_hits / nd  (derived from hit_call across cells, any-hit semantics)
 * - Audit: "Overridden only" boolean toggle
 *
 * The filter state lives in <CampaignBuilder> and is consumed by both this bar
 * and the AG Grid via its `isExternalFilterPresent` + `doesExternalFilterPass`.
 */

import type { CampaignResponse, CampaignResultResponse } from "../types";

export type CampaignDecisionFilter = "selected" | "deferred" | "rejected";
export type CampaignHitStatusFilter = "hit" | "non_hit" | "nd";

export interface CampaignFilters {
  decisions: Set<CampaignDecisionFilter>;
  hitStatus: Set<CampaignHitStatusFilter>;
  overriddenOnly: boolean;
}

export function emptyFilters(): CampaignFilters {
  return {
    decisions: new Set(),
    hitStatus: new Set(),
    overriddenOnly: false,
  };
}

export function filtersActive(f: CampaignFilters): boolean {
  return f.decisions.size > 0 || f.hitStatus.size > 0 || f.overriddenOnly;
}

/** Any-hit semantics: hit if any measurement is a hit; non_hit if all are miss; nd otherwise. */
export function computeRowHitStatus(
  result: CampaignResultResponse,
): CampaignHitStatusFilter {
  let hasHit = false;
  let hasMiss = false;
  for (const m of result.measurements) {
    if (m.hit_call === "hit") hasHit = true;
    else if (m.hit_call === "miss") hasMiss = true;
  }
  if (hasHit) return "hit";
  if (hasMiss) return "non_hit";
  return "nd";
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
  if (filters.hitStatus.size > 0) {
    const hitStatus = computeRowHitStatus(result);
    if (!filters.hitStatus.has(hitStatus)) return false;
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

interface CountByHit {
  hit: number;
  non_hit: number;
  nd: number;
}

function tallyCounts(results: CampaignResultResponse[]): {
  byDecision: CountByDecision;
  byHit: CountByHit;
  overridden: number;
} {
  const byDecision: CountByDecision = { selected: 0, deferred: 0, rejected: 0 };
  const byHit: CountByHit = { hit: 0, non_hit: 0, nd: 0 };
  let overridden = 0;
  for (const r of results) {
    if (r.decision in byDecision) {
      byDecision[r.decision as keyof CountByDecision]++;
    }
    byHit[computeRowHitStatus(r)]++;
    if (r.measurements.some((m) => m.is_manual_override)) overridden++;
  }
  return { byDecision, byHit, overridden };
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

const HIT_CHIP_STYLE: Record<CampaignHitStatusFilter, string> = {
  hit: "bg-orange-50 text-orange-800 border-orange-200 hover:bg-orange-100",
  non_hit: "bg-blue-50 text-blue-800 border-blue-200 hover:bg-blue-100",
  nd: "bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100",
};

const HIT_ACTIVE_STYLE: Record<CampaignHitStatusFilter, string> = {
  hit: "bg-orange-600 text-white border-orange-700",
  non_hit: "bg-blue-600 text-white border-blue-700",
  nd: "bg-gray-600 text-white border-gray-700",
};

export function CampaignFilterBar({
  campaign,
  filters,
  onChange,
  resultCount,
}: CampaignFilterBarProps) {
  const { byDecision, byHit, overridden } = tallyCounts(campaign.results);

  function toggleDecision(d: CampaignDecisionFilter) {
    const next = new Set(filters.decisions);
    next.has(d) ? next.delete(d) : next.add(d);
    onChange({ ...filters, decisions: next });
  }

  function toggleHit(h: CampaignHitStatusFilter) {
    const next = new Set(filters.hitStatus);
    next.has(h) ? next.delete(h) : next.add(h);
    onChange({ ...filters, hitStatus: next });
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

      {(["selected", "deferred", "rejected"] as CampaignDecisionFilter[]).map(
        (d) => {
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
        },
      )}

      <span className="text-muted-foreground/50 mx-1">·</span>

      {(["hit", "non_hit", "nd"] as CampaignHitStatusFilter[]).map((h) => {
        const isActive = filters.hitStatus.has(h);
        const label = h === "non_hit" ? "Non-hit" : h === "nd" ? "ND" : "Hit";
        return (
          <button
            key={h}
            type="button"
            onClick={() => toggleHit(h)}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border transition-colors ${
              isActive ? HIT_ACTIVE_STYLE[h] : HIT_CHIP_STYLE[h]
            }`}
          >
            <span>{label}</span>
            <span className="font-semibold tabular-nums">{byHit[h]}</span>
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
