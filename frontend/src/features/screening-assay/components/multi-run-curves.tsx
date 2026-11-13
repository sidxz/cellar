"use client";

import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useCurvePositions } from "../hooks/use-curve-positions";
import { useCurvesForPositions } from "../hooks/use-curves-for-positions";
import { apiReason } from "../hooks/use-instrument-import-wizard";
import type { CurveView } from "../hooks/use-run-curves";
import {
  type ColourMode,
  type CurveSeriesData,
  type GroupBy,
  curveSetFromPositions,
} from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState, drawnPositionIds } from "../lib/curve-selection";
import { CurveViewer } from "./curve-viewer";

const NO_CURVES: ReadonlyMap<string, CurveSeriesData> = new Map();

/** The curve viewer over positions of several runs of one protocol: finds the
 *  positions, then fetches curves for the drawn ones only. */
export function MultiRunCurves({
  protocolId,
  filter,
  hideStatuses,
  initial,
  exportName,
  empty,
}: {
  protocolId: string;
  filter: { runIds?: readonly string[]; moleculeIds?: readonly string[] };
  /** Runs in these statuses are left out. */
  hideStatuses?: readonly string[];
  initial?: {
    /** "compounds": once the positions arrive, select those of filter.moleculeIds. */
    select?: "none" | "compounds";
    showReferences?: boolean;
    colour?: { mode: ColourMode; groupBy?: GroupBy };
  };
  exportName: string;
  /** Shown when there is no position to offer. */
  empty: ReactNode;
}) {
  const { data: found, isLoading, error } = useCurvePositions(protocolId, filter);
  const [channel, setChannel] = useState<string | undefined>();
  const [view, setView] = useState<CurveView>("measured");
  // The committed window; undefined lets the API choose.
  const [derivativeWindow, setDerivativeWindow] = useState<number | undefined>();
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  const [showReferences, setShowReferences] = useState(initial?.showReferences ?? false);

  // A list rebuilt by the host each render must not rebuild the set.
  const hiddenKey = hideStatuses?.join("\n") ?? "";
  const base = useMemo(
    () =>
      found
        ? curveSetFromPositions(found, {
            channel,
            view,
            window: null,
            curves: NO_CURVES,
            hideStatuses: hiddenKey ? hiddenKey.split("\n") : [],
          })
        : null,
    [found, channel, view, hiddenKey],
  );

  // Once, when the positions first arrive.
  const initialised = useRef(false);
  const selectCompounds = initial?.select === "compounds";
  const moleculeKey = filter.moleculeIds?.join("\n") ?? "";
  useEffect(() => {
    if (initialised.current || !base) return;
    initialised.current = true;
    if (!selectCompounds) return;
    const molecules = new Set(moleculeKey.split("\n"));
    const ids = base.groups.flatMap((g) =>
      g.positions
        .filter((p) => p.molecule_id && molecules.has(p.molecule_id))
        .map((p) => p.well_id),
    );
    setSelection({ selected: new Set(ids), anchor: null });
  }, [base, selectCompounds, moleculeKey]);

  const drawnIds = useMemo(
    () => (base ? drawnPositionIds(base.groups, selection.selected, showReferences) : []),
    [base, selection.selected, showReferences],
  );
  const fetched = useCurvesForPositions(drawnIds, {
    channel: base?.channel ?? undefined,
    view,
    window: view === "derivative" ? derivativeWindow : undefined,
  });
  const set = useMemo(
    () => base && { ...base, window: fetched.window, curves: fetched.curves },
    [base, fetched.window, fetched.curves],
  );

  if (error && !found) {
    return <p className="py-8 text-center text-sm text-muted-foreground">{apiReason(error)}</p>;
  }
  if (isLoading || !set) return <Skeleton className="h-[400px] w-full" />;
  if (set.groups.length === 0) return <>{empty}</>;

  return (
    <div className="space-y-3">
      {fetched.failed && (
        <div className="flex items-center gap-2 text-sm text-destructive">
          Could not load some of the curves.
          <Button type="button" variant="outline" size="sm" onClick={fetched.retry}>
            Retry
          </Button>
        </div>
      )}
      <CurveViewer
        set={set}
        showReferences={showReferences}
        onShowReferencesChange={setShowReferences}
        selection={selection}
        onSelectionChange={setSelection}
        onChannelChange={setChannel}
        onViewChange={setView}
        onWindowChange={setDerivativeWindow}
        // After a failure the curves already drawn stay, dimmed, and nothing
        // missing is listed as having no curve.
        pending={fetched.pending || fetched.failed}
        failed={fetched.failed && fetched.curves.size === 0}
        exportName={exportName}
        initialColour={initial?.colour}
      />
    </div>
  );
}
