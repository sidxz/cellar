"use client";

import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import Link from "next/link";
import { type ReactNode, useEffect, useId, useMemo, useState } from "react";
import type { CurvePosition } from "../lib/curve-plot";
import { type SelectionState, applyClick } from "../lib/curve-selection";
import {
  type ResultFilter,
  type WindowSummary,
  matchesFilter,
  orderRows,
  resultRows,
  windowSummary,
} from "../lib/melt-results";
import { useShiftThreshold } from "../lib/use-shift-threshold";
import type { MeltingAnalysis } from "../types";
import { Segmented } from "./curve-viewer";
import { MeltResultsGrid } from "./melt-results-grid";
import { MeltSummaryStrip } from "./melt-summary-strip";

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
  showReferences: boolean;
  onShowReferencesChange: (next: boolean) => void;
  /** Edit labeling. */
  headerAction?: ReactNode;
  /** The single chosen window (kept while comparing); null when the signal has none. */
  onLeadWindowChange?: (windowName: string | null) => void;
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
  showReferences,
  onShowReferencesChange,
  headerAction,
  onLeadWindowChange,
  designHref,
}: MeltResultsPanelProps) {
  const [threshold, setThreshold] = useShiftThreshold();
  // The window last chosen by name; kept across signals and used where it exists.
  const [chosen, setChosen] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);
  const [filter, setFilter] = useState<ResultFilter>(null);
  const switchId = useId();

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

  const rows = useMemo(
    () => resultRows(windows, positions, analysis.steps, analysis.step_checks),
    [windows, positions, analysis.steps, analysis.step_checks],
  );
  const activeFilter = windowNames.length ? filter : null;
  const ordered = useMemo(() => {
    const { pinned, body } = orderRows(rows, windowNames);
    return {
      pinned,
      body: body.filter((r) => matchesFilter(r, windowNames, activeFilter, threshold)),
    };
  }, [rows, windowNames, activeFilter, threshold]);

  const summary = useMemo<WindowSummary | null>(() => {
    if (!lead) return null;
    const shown = comparing ? windows : [lead];
    const each = shown.map((w) =>
      windowSummary(w, rows, positions, analysis.steps, analysis.step_checks, threshold),
    );
    // Counted per position across the shown windows (once each), as the filters match.
    const samples = rows.filter((r) => r.isSample);
    const n = (f: ResultFilter) =>
      samples.filter((r) => matchesFilter(r, windowNames, f, threshold)).length;
    return {
      ...each[0],
      referenceUnreviewed: each.some((s) => s.referenceUnreviewed),
      needsReview: n("needs_review"),
      provisional: n("provisional"),
      up: n("up"),
      down: n("down"),
    };
  }, [lead, comparing, windows, rows, positions, analysis, threshold, windowNames]);

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
        <div className="flex items-center gap-2">
          <Switch id={switchId} checked={showReferences} onCheckedChange={onShowReferencesChange} />
          <Label htmlFor={switchId} className="text-sm font-normal">
            Reference traces
          </Label>
        </div>
        {headerAction && <div className="ml-auto flex items-center gap-2">{headerAction}</div>}
      </div>
      {summary ? (
        <MeltSummaryStrip
          summary={summary}
          threshold={threshold}
          onThresholdChange={setThreshold}
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
      <MeltResultsGrid
        rows={ordered}
        windowNames={windowNames}
        threshold={threshold}
        doseUnit={doseUnit}
        selection={selection}
        onRowClick={(id, mods, order) => onSelectionChange(applyClick(selection, order, id, mods))}
      />
    </section>
  );
}
