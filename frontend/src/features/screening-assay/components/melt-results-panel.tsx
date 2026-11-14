"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import type { CurvePosition } from "../lib/curve-plot";
import { type SelectionState, applyClick } from "../lib/curve-selection";
import { type ApplicableRule, bandFor } from "../lib/melt-hits";
import {
  type ResultFilter,
  type WindowSummary,
  matchesFilter,
  orderRows,
  resultRows,
  shiftRows,
  windowSummary,
} from "../lib/melt-results";
import type { MeltingAnalysis } from "../types";
import { MeltResultsGrid } from "./melt-results-grid";
import { MeltSummaryStrip } from "./melt-summary-strip";
import { Segmented } from "./segmented";
import { ShiftPlot } from "./shift-plot";

const COMPARE = "__compare__";
const NO_WINDOW = "No temperature window on this signal — add one on the protocol's Design tab";

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
  /** The run's rules that apply to Tm/ΔTm; they draw the shift plot's band. */
  applicable: readonly ApplicableRule[];
  /** The run's hit rule line, shown above the counts. */
  hitRule?: ReactNode;
  /** The protocol's Design tab, where windows are added; links the no-window note. */
  designHref?: string;
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
  designHref,
}: MeltResultsPanelProps) {
  // The window last chosen by name; kept across signals and used where it exists.
  const [chosen, setChosen] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);
  const [filter, setFilter] = useState<ResultFilter>(null);
  const [view, setView] = useState<"table" | "plot">("table");

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
  useEffect(() => {
    onLeadWindowChange?.(leadName);
  }, [leadName, onLeadWindowChange]);
  useEffect(() => {
    onShownWindowsChange?.(windowNames);
  }, [windowNames, onShownWindowsChange]);

  const rows = useMemo(
    () => resultRows(windows, positions, analysis.steps, analysis.step_checks),
    [windows, positions, analysis.steps, analysis.step_checks],
  );
  const activeFilter = windowNames.length ? filter : null;
  const ordered = useMemo(() => {
    const { pinned, body } = orderRows(rows, windowNames);
    return {
      pinned,
      body: body.filter((r) => matchesFilter(r, windowNames, activeFilter, hits)),
    };
  }, [rows, windowNames, activeFilter, hits]);

  const sampleCount = useMemo(() => rows.filter((r) => r.isSample).length, [rows]);
  const each = useMemo<WindowSummary[]>(
    () =>
      (comparing ? windows : lead ? [lead] : []).map((w) =>
        windowSummary(w, rows, positions, analysis.steps, analysis.step_checks, hits),
      ),
    [comparing, windows, lead, rows, positions, analysis, hits],
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
      provisional: n("provisional"),
      hits: n("hits"),
      up: n("up"),
      down: n("down"),
    };
  }, [each, rows, hits, windowNames]);
  // The references with a value in the shown windows (all of them if none has).
  const selectReferences = () => {
    const inShown = ordered.pinned.filter((r) => windowNames.some((n) => r.cells[n]));
    const ids = (inShown.length ? inShown : ordered.pinned).map((r) => r.wellId);
    if (ids.length) onSelectionChange({ selected: new Set(ids), anchor: ids[0] });
  };

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
                ...windows.map((w) => ({ value: w.window, label: w.window })),
                ...(windows.length >= 2 ? [{ value: COMPARE, label: "Compare" }] : []),
              ]}
              onChange={(v) => {
                setCompare(v === COMPARE);
                if (v !== COMPARE) setChosen(v);
              }}
            />
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
        {headerAction && <div className="ml-auto flex items-center gap-2">{headerAction}</div>}
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
          onSelectReferences={ordered.pinned.length ? selectReferences : undefined}
          hasRule={applicable.length > 0}
          filter={activeFilter}
          onFilterChange={setFilter}
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          {designHref ? (
            <Link href={designHref} className="underline-offset-4 hover:underline">
              {NO_WINDOW}
            </Link>
          ) : (
            NO_WINDOW
          )}
        </p>
      )}
      {view === "plot" && !comparing && lead ? (
        <ShiftPlot
          rows={shiftRows(
            rows.filter((r) => matchesFilter(r, windowNames, activeFilter, hits)),
            lead.window,
          )}
          hits={hits}
          band={bandFor(applicable, lead.window)}
          selected={selection.selected}
          onSelect={(id) =>
            onSelectionChange(applyClick(selection, [id], id, { shift: false, toggle: false }))
          }
        />
      ) : (
        <MeltResultsGrid
          rows={ordered}
          windowNames={windowNames}
          hits={hits}
          doseUnit={doseUnit}
          selection={selection}
          onRowClick={(id, mods, order) =>
            onSelectionChange(applyClick(selection, order, id, mods))
          }
        />
      )}
    </section>
  );
}
