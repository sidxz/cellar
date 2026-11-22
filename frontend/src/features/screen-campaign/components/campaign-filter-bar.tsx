"use client";

/**
 * CampaignFilterBar — chip-driven filter row above the results grid (B5).
 *
 * Two chip groups:
 * - Stage outcome (only when a hit stage is selected): hit / miss / untested /
 *   pending / not in stage, tallied from `stage_outcomes` for that stage.
 *   The "pending" chip only appears where pending can occur — a manual
 *   stage, or any stage the server still reports pending rows for.
 * - Audit: "Overridden" boolean toggle — a cell override, or an override on
 *   the selected stage
 *
 * The grid's toolbar adds a compound search and readout conditions (min/max, QC) to the same
 * state, so every gesture that acts on "the visible rows" sees what the grid shows.
 *
 * The filter state lives in <CampaignBuilderV2> / <CampaignView> next to
 * `selectedStageId` and is consumed by this bar, the bulk menus and the
 * AG Grid via its `isExternalFilterPresent` + `doesExternalFilterPass`.
 */

import { sameUnit } from "@/features/research-organization/lib/assay-evidence";
import type { MoleculeResponse } from "@/shared/lib/api/model";
import { useCampaignMolecules } from "../hooks/use-campaign-molecules";
import { outcomeFor, tallyStage } from "../lib/stage-outcomes";
import type {
  CampaignMeasurementResponse,
  CampaignResponse,
  CampaignResultResponse,
  StageOutcome,
} from "../types";

/** One readout condition: a range (inclusive) and/or a QC state. */
export interface MeasurementFilter {
  channelId: string;
  minimum: number | null;
  maximum: number | null;
  /** The unit the bounds are in. A value stored in another unit never falls in the range. */
  unit: string;
  qc: "any" | "verified" | "failed" | "not_tested";
}

export interface CampaignFilters {
  /** Only applied when a stage is selected — see `rowPassesFilters`. */
  stageOutcomes: Set<StageOutcome>;
  overriddenOnly: boolean;
  /** Registration number, name or any identifier; case-insensitive. "" = no search. */
  search: string;
  /** All must hold. */
  measurements: MeasurementFilter[];
}

export function emptyFilters(): CampaignFilters {
  return {
    stageOutcomes: new Set(),
    overriddenOnly: false,
    search: "",
    measurements: [],
  };
}

export function filtersActive(f: CampaignFilters, selectedStageId: string | null): boolean {
  return (
    f.overriddenOnly ||
    (selectedStageId != null && f.stageOutcomes.size > 0) ||
    f.search !== "" ||
    f.measurements.length > 0
  );
}

/** What a search can find a compound by. */
export type SearchableMolecule = Pick<
  MoleculeResponse,
  "registration_number" | "name" | "identifiers"
>;

function moleculeMatches(m: SearchableMolecule | undefined, search: string): boolean {
  if (!m) return false;
  const q = search.toLocaleLowerCase();
  return [m.registration_number, m.name, ...(m.identifiers ?? []).map((i) => i.identifier)].some(
    (text) => !!text && text.toLocaleLowerCase().includes(q),
  );
}

/** "-" is the server's "unit unknown", which it treats as matching any unit. */
const unitMatches = (a: string, b: string) => a === "-" || b === "-" || sameUnit(a, b) || a === b;

/** A range holds only exact values ("=" with a number): never a limit, ND or an excluded value. */
export function measurementPasses(
  m: CampaignMeasurementResponse | undefined,
  f: MeasurementFilter,
): boolean {
  if (!m) return false;
  if (f.minimum != null || f.maximum != null) {
    if (m.value_qualifier !== "=" || m.value == null || !Number.isFinite(m.value)) return false;
    if (!unitMatches(m.unit ?? "", f.unit)) return false;
    if (f.minimum != null && m.value < f.minimum) return false;
    if (f.maximum != null && m.value > f.maximum) return false;
  }
  if (f.qc === "verified" || f.qc === "failed") return m.qc_verdict === f.qc;
  // Not tested: a value with a result nobody has checked yet.
  if (f.qc === "not_tested") return !!m.holds_result && m.qc_verdict === "not_tested";
  return true;
}

/** A row counts as overridden when any of its cells was manually overridden,
 *  or — with a stage selected — when its outcome for that stage was forced. */
function rowIsOverridden(result: CampaignResultResponse, selectedStageId: string | null): boolean {
  if (result.measurements.some((m) => m.is_manual_override)) return true;
  return selectedStageId != null && (outcomeFor(result, selectedStageId)?.overridden ?? false);
}

/** ``molecules`` resolves a search: while they are unknown, a search matches nothing, so no
 *  bulk gesture reaches a row the grid would hide. */
export function rowPassesFilters(
  result: CampaignResultResponse,
  filters: CampaignFilters,
  selectedStageId: string | null,
  molecules?: ReadonlyMap<string, SearchableMolecule>,
): boolean {
  if (selectedStageId != null && filters.stageOutcomes.size > 0) {
    // A result carrying no entry for the stage was never evaluated against
    // it — same practical meaning as being gated out of its population.
    const outcome = (outcomeFor(result, selectedStageId)?.outcome ??
      "not_in_stage") as StageOutcome;
    if (!filters.stageOutcomes.has(outcome)) return false;
  }
  if (filters.overriddenOnly && !rowIsOverridden(result, selectedStageId)) return false;
  if (filters.search && !moleculeMatches(molecules?.get(result.molecule_id), filters.search)) {
    return false;
  }
  return filters.measurements.every((f) =>
    measurementPasses(
      result.measurements?.find((m) => m.channel_id === f.channelId),
      f,
    ),
  );
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

function tallyOverridden(
  results: CampaignResultResponse[],
  selectedStageId: string | null,
): number {
  return results.filter((r) => rowIsOverridden(r, selectedStageId)).length;
}

const OUTCOME_ORDER: StageOutcome[] = ["hit", "miss", "untested", "pending", "not_in_stage"];

const OUTCOME_LABELS: Record<StageOutcome, string> = {
  hit: "Hit",
  miss: "Miss",
  untested: "Untested",
  pending: "Pending",
  not_in_stage: "Not in stage",
};

const OUTCOME_CHIP_STYLE: Record<StageOutcome, string> = {
  hit: "bg-green-50 text-green-800 border-green-200 hover:bg-green-100",
  miss: "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100",
  untested: "bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100",
  pending: "bg-blue-50 text-blue-800 border-blue-200 hover:bg-blue-100",
  not_in_stage: "bg-muted text-muted-foreground border-transparent hover:bg-muted/70",
};

const OUTCOME_ACTIVE_STYLE: Record<StageOutcome, string> = {
  hit: "bg-green-600 text-white border-green-700",
  miss: "bg-slate-600 text-white border-slate-700",
  untested: "bg-amber-600 text-white border-amber-700",
  pending: "bg-blue-600 text-white border-blue-700",
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
  const molecules = useCampaignMolecules(campaign);
  const overridden = tallyOverridden(campaign.results, selectedStageId);
  const stageTally = selectedStageId ? tallyStage(campaign.results, selectedStageId) : null;
  const selectedStage = selectedStageId
    ? (campaign.stages ?? []).find((s) => s.id === selectedStageId)
    : undefined;
  // "Pending" is dead weight on an ordinary criteria stage that can never
  // produce one — show it only where the outcome is reachable.
  const showPending = selectedStage?.kind === "manual" || (selectedStage?.counts?.pending ?? 0) > 0;

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
  // The rows the grid shows and the bulk gestures act on: the same check.
  const shown = active
    ? campaign.results.filter((r) => rowPassesFilters(r, filters, selectedStageId, molecules))
        .length
    : resultCount;

  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-3 py-2 text-xs">
      <span className="text-muted-foreground font-medium">Filter:</span>

      {stageTally &&
        OUTCOME_ORDER.filter((o) => o !== "pending" || showPending).map((o) => {
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

      {stageTally && <span className="text-muted-foreground/50 mx-1">·</span>}

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
          {active && shown !== resultCount ? `${shown} of ` : ""}
          {resultCount} {resultCount === 1 ? "result" : "results"}
        </span>
      )}
    </div>
  );
}
