"use client";

import { Button } from "@/shared/components/ui/button";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import type { CurvePosition } from "../lib/curve-plot";
import { type SelectionState, applyClick } from "../lib/curve-selection";
import { type ApplicableRule, bandFor, limitsFor, notEvaluated } from "../lib/melt-hits";
import {
  type ResultFilter,
  type WindowSummary,
  knownFilter,
  matchesFilter,
  orderRows,
  resultRows,
  shiftRows,
  windowSummary,
} from "../lib/melt-results";
import { windowLabel } from "../lib/window-proposal";
import type { MeltingAnalysis } from "../types";
import { MeltResultsGrid } from "./melt-results-grid";
import { MeltSummaryStrip } from "./melt-summary-strip";
import { Segmented } from "./segmented";
import { ShiftPlot } from "./shift-plot";
import { StructuresToggle, useStructuresChoice } from "./structures-toggle";

const COMPARE = "__compare__";
const STRUCTURES_KEY = "cellar.traces.structures";

export interface MeltResultsPanelProps {
  analysis: MeltingAnalysis;
  positions: readonly CurvePosition[];
  /** The signal shown in the viewer. */
  channel: string | null;
  doseUnit: string;
  selection: SelectionState;
  onSelectionChange: (next: SelectionState) => void;
  /** Edit labeling. */
  headerAction?: ReactNode;
  /** The single chosen window (kept while comparing); null when the signal has none. */
  onLeadWindowChange?: (windowName: string | null) => void;
  /** The windows the results show: the lead, or all of them in Compare. */
  onShownWindowsChange?: (names: readonly string[]) => void;
  /** The positions the run's hit rule calls hits (empty without a rule). */
  hits: ReadonlySet<string>;
  /** The run's rules that apply to Tm/ΔTm; they draw the shift plot's band, and
   *  a value beside one of their limits is shown to two decimals. */
  applicable: readonly ApplicableRule[];
  /** The run's hit rule line, shown above the counts. */
  hitRule?: ReactNode;
  /** Opens the setting up of windows (naming the reference's peaks); given to
   *  editors. A button while there is something to set up, else a quiet Edit. */
  onNamePeaks?: () => void;
}

/** The run's results for the signal on screen: a window picker, the counts
 *  (each a filter) and one grid that is also the position picker. */
export function MeltResultsPanel({
  analysis,
  positions,
  channel,
  doseUnit,
  selection,
  onSelectionChange,
  headerAction,
  onLeadWindowChange,
  onShownWindowsChange,
  hits,
  applicable,
  hitRule,
  onNamePeaks,
}: MeltResultsPanelProps) {
  // The window last chosen by name; kept across signals and used where it exists.
  const [chosen, setChosen] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);
  const [filter, setFilter] = useState<ResultFilter>(null);
  const [view, setView] = useState<"table" | "plot">("table");
  const [showStructures, setShowStructures] = useStructuresChoice(STRUCTURES_KEY);

  const windows = useMemo(
    () => analysis.windows.filter((w) => w.channel_key === channel),
    [analysis.windows, channel],
  );
  const lead = windows.find((w) => w.window === chosen) ?? windows[0] ?? null;
  const comparing = compare && windows.length >= 2;
  const windowNames = useMemo(
    () => (comparing ? windows.map((w) => w.window) : lead ? [lead.window] : []),
    [comparing, windows, lead],
  );
  const leadName = lead?.window ?? null;
  const plotShown = view === "plot" && !comparing && !!lead;
  // Something to set up: the signal has no window, or a reference has a
  // counted peak on it that no window holds.
  const needsSetup = useMemo(() => {
    if (windows.length === 0) return true;
    const outside = new Set(analysis.outside_every_window);
    const references = new Set(
      positions.filter((p) => p.well_type === "reference").map((p) => p.well_id),
    );
    return analysis.steps.some(
      (s) => s.channel_key === channel && outside.has(s.id) && references.has(s.well_id),
    );
  }, [windows, analysis.outside_every_window, analysis.steps, positions, channel]);
  useEffect(() => {
    onLeadWindowChange?.(leadName);
  }, [leadName, onLeadWindowChange]);
  useEffect(() => {
    onShownWindowsChange?.(windowNames);
  }, [windowNames, onShownWindowsChange]);

  const rows = useMemo(
    () =>
      resultRows(
        windows,
        positions,
        analysis.steps,
        analysis.step_checks,
        analysis.outside_every_window,
      ),
    [windows, positions, analysis.steps, analysis.step_checks, analysis.outside_every_window],
  );
  // Of the run, not of the rows a filter leaves: the column does not come and go.
  const hasConcentration = useMemo(() => positions.some((p) => p.dose != null), [positions]);
  const activeFilter = windowNames.length ? knownFilter(filter) : null;
  // The samples missing a value the run's hit rule needs; empty without a rule.
  const unevaluated = useMemo(
    () => notEvaluated(analysis, positions, applicable),
    [analysis, positions, applicable],
  );
  const ordered = useMemo(() => {
    const { pinned, body } = orderRows(rows, windowNames);
    return {
      pinned,
      body: body.filter((r) => matchesFilter(r, windowNames, activeFilter, hits, unevaluated)),
    };
  }, [rows, windowNames, activeFilter, hits, unevaluated]);

  const sampleCount = useMemo(() => rows.filter((r) => r.isSample).length, [rows]);
  const each = useMemo<WindowSummary[]>(
    () =>
      (comparing ? windows : lead ? [lead] : []).map((w) =>
        windowSummary(w, rows, positions, analysis.step_checks, hits),
      ),
    [comparing, windows, lead, rows, positions, analysis.step_checks, hits],
  );
  const summary = useMemo<WindowSummary | null>(() => {
    if (each.length === 0) return null;
    // Counted per position across the shown windows (once each), as the filters match.
    const samples = rows.filter((r) => r.isSample);
    const n = (f: ResultFilter) =>
      samples.filter((r) => matchesFilter(r, windowNames, f, hits)).length;
    return {
      ...each[0],
      referenceLabels: each.flatMap((s) => s.referenceLabels),
      referencesDiffer: each.some((s) => s.referencesDiffer),
      referenceUnreviewed: each.some((s) => s.referenceUnreviewed),
      needsReview: n("needs_review"),
      // Not shown; kept for what will act on the peaks nobody has reviewed.
      provisional: samples.filter((r) =>
        windowNames.some((w) => r.cells[w]?.status === "provisional"),
      ).length,
      hits: n("hits"),
      up: n("up"),
      down: n("down"),
    };
  }, [each, rows, hits, windowNames]);

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <h3 className="text-sm font-semibold">Results</h3>
        {windows.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">Window</span>
            <Segmented
              label="Window"
              value={comparing ? COMPARE : (leadName ?? "")}
              options={[
                ...windows.map((w) => ({ value: w.window, label: windowLabel(w) })),
                ...(windows.length >= 2 ? [{ value: COMPARE, label: "Compare" }] : []),
              ]}
              onChange={(v) => {
                setCompare(v === COMPARE);
                if (v !== COMPARE) setChosen(v);
              }}
            />
            {onNamePeaks && !needsSetup && (
              <Button
                type="button"
                variant="link"
                aria-label="Set up windows"
                className="h-auto p-0 text-xs font-normal text-muted-foreground"
                onClick={onNamePeaks}
              >
                Edit
              </Button>
            )}
          </div>
        )}
        <div title={comparing ? "Shift plot shows one window" : undefined}>
          <Segmented
            label="View"
            value={view === "plot" && !comparing ? "plot" : "table"}
            options={[
              { value: "table", label: "Table" },
              { value: "plot", label: "Shift plot", disabled: comparing || !lead },
            ]}
            onChange={setView}
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StructuresToggle
            pressed={showStructures}
            onPressedChange={setShowStructures}
            // The shift plot draws no structures.
            disabled={plotShown}
          />
          {onNamePeaks && needsSetup && (
            <Button type="button" variant="outline" size="sm" onClick={onNamePeaks}>
              Set up windows
            </Button>
          )}
          {headerAction}
        </div>
      </div>
      {hitRule}
      {summary ? (
        <MeltSummaryStrip
          summary={summary}
          scope={comparing ? "All windows" : (leadName ?? "")}
          perWindow={comparing ? each : undefined}
          shown={
            activeFilter
              ? { count: ordered.body.filter((r) => r.isSample).length, total: sampleCount }
              : undefined
          }
          hasRule={applicable.length > 0}
          notEvaluated={unevaluated.size}
          filter={activeFilter}
          onFilterChange={setFilter}
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          No temperature window on this signal.
          {onNamePeaks && (
            <>
              {" "}
              <Button
                type="button"
                variant="link"
                className="h-auto p-0 font-normal"
                onClick={onNamePeaks}
              >
                Set up windows
              </Button>
              .
            </>
          )}
        </p>
      )}
      {plotShown ? (
        <ShiftPlot
          rows={shiftRows(
            rows.filter((r) => matchesFilter(r, windowNames, activeFilter, hits, unevaluated)),
            lead.window,
          )}
          hits={hits}
          band={bandFor(applicable, lead.window)}
          limits={limitsFor(applicable, lead.window, "delta_tm")}
          selected={selection.selected}
          onSelect={(id) =>
            onSelectionChange(applyClick(selection, [id], id, { shift: false, toggle: false }))
          }
        />
      ) : (
        <MeltResultsGrid
          rows={ordered}
          windowNames={windowNames}
          steps={analysis.steps}
          windows={windows}
          hits={hits}
          applicable={applicable}
          doseUnit={doseUnit}
          showConcentration={hasConcentration}
          showStructures={showStructures}
          selection={selection}
          onRowClick={(id, mods, order) =>
            onSelectionChange(applyClick(selection, order, id, mods))
          }
        />
      )}
    </section>
  );
}
