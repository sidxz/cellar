"use client";

import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { cn, shortId } from "@/shared/lib/utils";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMeltingAnalysis } from "../hooks/use-melting-analysis";
import { type CurveView, useRunCurves } from "../hooks/use-run-curves";
import {
  type PlotStep,
  currentChannel,
  curveSetFromRun,
  orderedPositions,
} from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState, applyClick } from "../lib/curve-selection";
import { batchSeries, firstToSelect, resultRows } from "../lib/melt-results";
import { labellingEditRefusal } from "../lib/position-edits";
import { DOSE_UNIT_LABELS, type DoseUnit, type Run } from "../types";
import { ConcentrationChart } from "./concentration-chart";
import { CurveViewer } from "./curve-viewer";
import { EditLabellingDialog } from "./edit-labelling-dialog";
import { MeltResultsPanel } from "./melt-results-panel";
import { MeltingStepsPanel, stepInput } from "./melting-steps-panel";

const PLOT_HEIGHT = "h-[400px]";

/** The Traces tab: the results grid beside the trace viewer, one linked
 *  workspace. The grid picks the positions; the viewer overlays their traces
 *  for one signal with their melting steps as lines and the temperature
 *  windows as bands; the steps under it are reviewed there. Without an
 *  analysis (it failed to load) the viewer keeps its own position selector. */
export function RunCurvesPanel({
  runId,
  run,
}: {
  runId: string;
  /** Given, Edit labelling is offered to editors. */
  run?: Pick<Run, "id" | "protocol_id" | "status" | "is_locked">;
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
  const [showReferences, setShowReferences] = useState(true);
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
  // Once per run: with nothing selected yet, start on the row most worth a look.
  const [leadWindow, setLeadWindow] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(2);
  const initialised = useRef<string | null>(null);
  useEffect(() => {
    if (!analysis || !data || initialised.current === runId) return;
    initialised.current = runId;
    if (selection.selected.size > 0) return;
    const onSignal = analysis.windows.filter((w) => w.channel_key === data.channel);
    const lead = onSignal.find((w) => w.window === leadWindow) ?? onSignal[0];
    const rows = resultRows(onSignal, data.positions, analysis.steps, analysis.step_checks);
    const id = firstToSelect(rows, lead ? [lead.window] : []);
    if (id) setSelection(applyClick(EMPTY_SELECTION, [id], id, { shift: false, toggle: false }));
  }, [analysis, data, runId, selection, leadWindow]);

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
  const anchor = data.positions.find((p) => p.well_id === selection.anchor);
  const lead = analysis?.windows.find(
    (w) => w.window === leadWindow && w.channel_key === set.channel,
  );
  const series =
    lead && anchor?.well_type === "sample" && anchor.batch_id
      ? batchSeries(lead, data.positions, anchor.batch_id)
      : [];
  const batchSuffix =
    anchor?.batch_number && anchor.registration_number
      ? anchor.batch_number.startsWith(anchor.registration_number)
        ? anchor.batch_number.slice(anchor.registration_number.length).replace(/^[\s\-·]+/, "")
        : anchor.batch_number
      : anchor?.batch_number;
  const editRefusal = run ? labellingEditRefusal(run) : null;

  // The grid is the selector; without an analysis (it failed) the viewer's own stays.
  const fallback = !analysis && !melting.isLoading;
  const editLabelling = run && canEdit && (
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
  );

  return (
    <div className="@container">
      <div className="grid gap-6 @[1100px]:grid-cols-12">
        <div className="order-2 min-w-0 @[1100px]:order-1 @[1100px]:col-span-7">
          {analysis ? (
            <MeltResultsPanel
              analysis={analysis}
              positions={data.positions}
              channel={set.channel}
              doseUnit={doseUnit}
              selection={selection}
              onSelectionChange={setSelection}
              showReferences={showReferences}
              onShowReferencesChange={setShowReferences}
              headerAction={editLabelling}
              onLeadWindowChange={setLeadWindow}
              onThresholdChange={setThreshold}
              designHref={run && `/assays/protocols/${run.protocol_id}#design`}
            />
          ) : (
            melting.isLoading && (
              <Skeleton data-testid="results-loading" className={cn("w-full", PLOT_HEIGHT)} />
            )
          )}
        </div>
        <div className="order-1 min-w-0 space-y-6 self-start @[1100px]:sticky @[1100px]:top-4 @[1100px]:order-2 @[1100px]:col-span-5">
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
            hideSelector={!fallback}
            collapseReportedTable={!fallback}
            selectorAction={fallback && editLabelling}
          />
          {analysis && selection.selected.size === 0 && (
            <p className="text-sm text-muted-foreground">
              Select a sample in the results to see its trace and steps.
            </p>
          )}
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
          {lead && anchor && series.length > 0 && (
            <ConcentrationChart
              title={`${anchor.registration_number} · ${batchSuffix} — ΔTm (${lead.window}) by concentration`}
              points={series}
              doseUnit={doseUnit}
              threshold={threshold}
              selected={selection.selected}
              onSelect={(id) =>
                setSelection(applyClick(selection, [id], id, { shift: false, toggle: false }))
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}
