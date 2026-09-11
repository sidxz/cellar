"use client";

/**
 * CampaignFilterBar — chip-driven filter row above the results grid (B5).
 *
 * Three chip groups:
 * - Decision: selected / deferred / rejected (toggle each)
 * - Stage outcome (only when a hit stage is selected): hit / miss / untested /
 *   not in stage, tallied from `stage_outcomes` for that stage
 * - Audit: "Overridden" boolean toggle — a cell override, or an override on
 *   the selected stage
 *
 * The filter state lives in <CampaignBuilderV2> / <CampaignView> next to
 * `selectedStageId` and is consumed by this bar and the
 * AG Grid via its `isExternalFilterPresent` + `doesExternalFilterPass`.
 */

import { outcomeFor, tallyStage } from "../lib/stage-outcomes";
import type { CampaignResponse, CampaignResultResponse, StageOutcome } from "../types";

export type CampaignDecisionFilter = "selected" | "deferred" | "rejected";

export interface CampaignFilters {
  decisions: Set<CampaignDecisionFilter>;
  /** Only applied when a stage is selected — see `rowPassesFilters`. */
  stageOutcomes: Set<StageOutcome>;
  overriddenOnly: boolean;
}

export function emptyFilters(): CampaignFilters {
  return {
    decisions: new Set(),
    stageOutcomes: new Set(),
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
    stageOutcomes: new Set(),
    overriddenOnly: false,
  };
}

export function filtersActive(f: CampaignFilters, selectedStageId: string | null): boolean {
  return (
    f.decisions.size > 0 ||
    f.overriddenOnly ||
    (selectedStageId != null && f.stageOutcomes.size > 0)
  );
}

/** A row counts as overridden when any of its cells was manually overridden,
 *  or — with a stage selected — when its outcome for that stage was forced. */
function rowIsOverridden(result: CampaignResultResponse, selectedStageId: string | null): boolean {
  if (result.measurements.some((m) => m.is_manual_override)) return true;
  return selectedStageId != null && (outcomeFor(result, selectedStageId)?.overridden ?? false);
}

export function rowPassesFilters(
  result: CampaignResultResponse,
  filters: CampaignFilters,
  selectedStageId: string | null,
): boolean {
  if (
    filters.decisions.size > 0 &&
    !filters.decisions.has(result.decision as CampaignDecisionFilter)
  ) {
    return false;
  }
  if (selectedStageId != null && filters.stageOutcomes.size > 0) {
    // A result carrying no entry for the stage was never evaluated against
    // it — same practical meaning as being gated out of its population.
    const outcome = (outcomeFor(result, selectedStageId)?.outcome ??
      "not_in_stage") as StageOutcome;
    if (!filters.stageOutcomes.has(outcome)) return false;
  }
  if (filters.overriddenOnly && !rowIsOverridden(result, selectedStageId)) return false;
  return true;
}

// ── UI ────────────────────────────────────────────────────────────────────────

interface CampaignFilterBarProps {
  campaign: CampaignResponse;
  filters: CampaignFilters;
  onChange: (next: CampaignFilters) => void;
  /** Selected hit stage, or null for "All" — gates the outcome chips. */
  selectedStageId: string | null;
  /** Optional result count rendered right-aligned. */
  resultCount?: number;
}

interface CountByDecision {
  selected: number;
  deferred: number;
  rejected: number;
}

function tallyCounts(
  results: CampaignResultResponse[],
  selectedStageId: string | null,
): { byDecision: CountByDecision; overridden: number } {
  const byDecision: CountByDecision = { selected: 0, deferred: 0, rejected: 0 };
  let overridden = 0;
  for (const r of results) {
    if (r.decision in byDecision) {
      byDecision[r.decision as keyof CountByDecision]++;
    }
    if (rowIsOverridden(r, selectedStageId)) overridden++;
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

const OUTCOME_ORDER: StageOutcome[] = ["hit", "miss", "untested", "not_in_stage"];

const OUTCOME_LABELS: Record<StageOutcome, string> = {
  hit: "Hit",
  miss: "Miss",
  untested: "Untested",
  not_in_stage: "Not in stage",
};

const OUTCOME_CHIP_STYLE: Record<StageOutcome, string> = {
  hit: "bg-green-50 text-green-800 border-green-200 hover:bg-green-100",
  miss: "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100",
  untested: "bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100",
  not_in_stage: "bg-muted text-muted-foreground border-transparent hover:bg-muted/70",
};

const OUTCOME_ACTIVE_STYLE: Record<StageOutcome, string> = {
  hit: "bg-green-600 text-white border-green-700",
  miss: "bg-slate-600 text-white border-slate-700",
  untested: "bg-amber-600 text-white border-amber-700",
  not_in_stage: "bg-foreground/70 text-background border-transparent",
};

const CHIP_BASE =
  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full border transition-colors";

export function CampaignFilterBar({
  campaign,
  filters,
  onChange,
  selectedStageId,
  resultCount,
}: CampaignFilterBarProps) {
  const { byDecision, overridden } = tallyCounts(campaign.results, selectedStageId);
  const stageTally = selectedStageId ? tallyStage(campaign.results, selectedStageId) : null;

  function toggleDecision(d: CampaignDecisionFilter) {
    const next = new Set(filters.decisions);
    next.has(d) ? next.delete(d) : next.add(d);
    onChange({ ...filters, decisions: next });
  }

  function toggleOutcome(o: StageOutcome) {
    const next = new Set(filters.stageOutcomes);
    next.has(o) ? next.delete(o) : next.add(o);
    onChange({ ...filters, stageOutcomes: next });
  }

  function toggleOverridden() {
    onChange({ ...filters, overriddenOnly: !filters.overriddenOnly });
  }

  function clearAll() {
    onChange(emptyFilters());
  }

  const active = filtersActive(filters, selectedStageId);

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
            className={`${CHIP_BASE} ${isActive ? DECISION_ACTIVE_STYLE[d] : DECISION_CHIP_STYLE[d]}`}
          >
            <span className="capitalize">{d}</span>
            <span className="font-semibold tabular-nums">{byDecision[d]}</span>
          </button>
        );
      })}

      {stageTally && (
        <>
          <span className="text-muted-foreground/50 mx-1">·</span>
          {OUTCOME_ORDER.map((o) => {
            const isActive = filters.stageOutcomes.has(o);
            return (
              <button
                key={o}
                type="button"
                onClick={() => toggleOutcome(o)}
                className={`${CHIP_BASE} ${isActive ? OUTCOME_ACTIVE_STYLE[o] : OUTCOME_CHIP_STYLE[o]}`}
              >
                <span>{OUTCOME_LABELS[o]}</span>
                <span className="font-semibold tabular-nums">{stageTally[o]}</span>
              </button>
            );
          })}
        </>
      )}

      <span className="text-muted-foreground/50 mx-1">·</span>

      <button
        type="button"
        onClick={toggleOverridden}
        className={`${CHIP_BASE} ${
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
