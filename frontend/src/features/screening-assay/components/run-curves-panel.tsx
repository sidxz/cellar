"use client";

import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { cn, shortId } from "@/shared/lib/utils";
import { useMemo, useRef, useState } from "react";
import { useMeltingAnalysis } from "../hooks/use-melting-analysis";
import { type CurveView, useRunCurves } from "../hooks/use-run-curves";
import {
  type PlotStep,
  currentChannel,
  curveSetFromRun,
  orderedPositions,
} from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState } from "../lib/curve-selection";
import { labellingEditRefusal } from "../lib/position-edits";
import { DOSE_UNIT_LABELS, type DoseUnit, type Run } from "../types";
import { CurveViewer } from "./curve-viewer";
import { EditLabellingDialog } from "./edit-labelling-dialog";
import { MeltResultsPanel } from "./melt-results-panel";
import { MeltingStepsPanel, stepInput } from "./melting-steps-panel";

const PLOT_HEIGHT = "h-[400px]";

/** The Traces tab: pick positions, overlay their traces for one signal with
 *  their melting steps as lines and the temperature windows as bands, read a
 *  table of them, review the steps, export the figure. */
export function RunCurvesPanel({
  runId,
  run,
}: {
  runId: string;
  /** Given, Edit labelling is offered to editors. */
  run?: Pick<Run, "id" | "status" | "is_locked">;
}) {
  const canEdit = useCanEdit();
  const [editOpen, setEditOpen] = useState(false);
  const [channel, setChannel] = useState<string | undefined>();
  const [view, setView] = useState<CurveView>("measured");
  // The committed window; undefined lets the API choose.
  const [derivativeWindow, setDerivativeWindow] = useState<number | undefined>();
  const {
    data: fetched,
    isLoading,
    isPlaceholderData,
    error,
    refetch,
  } = useRunCurves(runId, {
    channel,
    view,
    window: view === "derivative" ? derivativeWindow : undefined,
  });
  // A failed request keeps the last curves' toolbar on screen, so the user can
  // change the window or the view instead of being left with only an error.
  const lastGood = useRef(fetched);
  if (fetched) lastGood.current = fetched;
  const data = fetched ?? lastGood.current;
  const failed = !!error && !fetched;

  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  const [showReferences, setShowReferences] = useState(false);
  const set = useMemo(() => (data ? curveSetFromRun(data) : null), [data]);

  const melting = useMeltingAnalysis(runId);
  const analysis = melting.data;
  // The value field of the open step form; a plot click fills it.
  const [stepValue, setStepValue] = useState("");
  const channelKey = set?.channel ?? null;
  const steps = useMemo(() => {
    if (!analysis) return undefined;
    const byWell = new Map<string, PlotStep[]>();
    for (const s of analysis.steps) {
      if (s.channel_key !== channelKey || s.status === "rejected") continue;
      byWell.set(s.well_id, [
        ...(byWell.get(s.well_id) ?? []),
        { value: s.value, reviewed: s.status === "accepted" },
      ]);
    }
    return byWell;
  }, [analysis, channelKey]);
  const windows = useMemo(
    () =>
      analysis?.windows
        .filter((w) => w.channel_key === channelKey)
        .map((w) => ({ low: w.low, high: w.high, label: w.window })),
    [analysis, channelKey],
  );

  if (isLoading && !data) return <Skeleton className={cn("w-full", PLOT_HEIGHT)} />;
  if (!data || !set) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Could not load the traces. Reload the page and try again.
      </p>
    );
  }

  const doseUnit = DOSE_UNIT_LABELS[data.dose_unit as DoseUnit] ?? data.dose_unit;
  const editRefusal = run ? labellingEditRefusal(run) : null;

  return (
    <div className="space-y-6">
      <CurveViewer
        set={set}
        steps={steps}
        windows={windows}
        onPlotClick={(x) => setStepValue(stepInput(x))}
        showReferences={showReferences}
        onShowReferencesChange={setShowReferences}
        selection={selection}
        onSelectionChange={setSelection}
        onChannelChange={setChannel}
        onViewChange={setView}
        onWindowChange={setDerivativeWindow}
        pending={isPlaceholderData}
        failed={failed}
        exportName={`traces-run-${shortId(data.run_id)}`}
        selectorAction={
          run &&
          canEdit && (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!!editRefusal}
                title={editRefusal ?? undefined}
                onClick={() => setEditOpen(true)}
              >
                Edit labeling
              </Button>
              <EditLabellingDialog
                run={run}
                positions={data.positions}
                doseUnit={doseUnit}
                open={editOpen}
                onOpenChange={setEditOpen}
                onReload={refetch}
              />
            </>
          )
        }
      />
      {analysis && (
        <MeltingStepsPanel
          runId={runId}
          analysis={analysis}
          positions={orderedPositions(set).filter((p) => selection.selected.has(p.well_id))}
          channel={set.channel}
          unit={currentChannel(set)?.x_unit ?? ""}
          value={stepValue}
          onValueChange={setStepValue}
          onReload={melting.refetch}
        />
      )}
      {analysis && (
        <MeltResultsPanel
          analysis={analysis}
          positions={data.positions}
          channel={set.channel}
          doseUnit={doseUnit}
          selection={selection}
          onSelectionChange={setSelection}
          showReferences={showReferences}
          onShowReferencesChange={setShowReferences}
        />
      )}
    </div>
  );
}
