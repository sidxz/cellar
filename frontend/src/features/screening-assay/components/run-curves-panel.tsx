"use client";

import { ExportToolbar } from "@/shared/components/export/export-toolbar";
import type { ExportFormat, ExportRequest } from "@/shared/components/export/types";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { cn, shortId } from "@/shared/lib/utils";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMeltingAnalysis, usePeakCandidates } from "../hooks/use-melting-analysis";
import { useProtocol } from "../hooks/use-protocols";
import { type CurveView, useRunCurves } from "../hooks/use-run-curves";
import {
  type PlotStep,
  currentChannel,
  curveSetFromRun,
  nearestPeak,
  orderedPositions,
  pickReach,
} from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState, applyClick } from "../lib/curve-selection";
import { bandFor, hitWells, splitRunRules } from "../lib/melt-hits";
import {
  batchDoseCount,
  batchSeries,
  batchSuffix,
  firstToSelect,
  resultRows,
  sampleTextOf,
  seriesCaption,
  seriesGaps,
} from "../lib/melt-results";
import { hintsFor, snapTarget } from "../lib/peak-candidates";
import { labellingEditRefusal } from "../lib/position-edits";
import { DOSE_UNIT_LABELS, type DoseUnit, type Run } from "../types";
import { AcceptAllPeaks } from "./accept-all-peaks";
import { ConcentrationChart } from "./concentration-chart";
import { CurveViewer } from "./curve-viewer";
import { EditLabellingDialog } from "./edit-labelling-dialog";
import { MeltHitRule } from "./melt-hit-rule";
import { MeltResultsPanel } from "./melt-results-panel";
import { MeltingStepsPanel, type StepRequest, canUseAsTm, stepInput } from "./melting-steps-panel";
import { NamePeaksDialog } from "./name-peaks-dialog";
import { type PeakPick, PeakPickBar } from "./peak-pick-bar";

const PLOT_HEIGHT = "h-[400px]";

/** The Traces tab: the results grid beside the trace viewer, one linked
 *  workspace. The grid picks the positions; the viewer overlays their traces
 *  for one signal with their melting steps as lines and the temperature
 *  windows as bands; a click on a trace picks a peak or a spot, which a line
 *  under the plot acts on through the step list's forms; under the plot, the
 *  steps are reviewed and the batch's ΔTm is charted by concentration. An
 *  editor names the reference's peaks from the results header, which adds the
 *  protocol's windows. Without an analysis (it failed to load) the viewer
 *  keeps its own position selector. */
const RUN_FORMATS: readonly ExportFormat[] = ["xlsx", "csv", "pdf"];

export function RunCurvesPanel({
  runId,
  run,
}: {
  runId: string;
  /** Given, Edit labelling is offered to editors and the run's hit rule calls hits. */
  run?: Pick<
    Run,
    | "id"
    | "protocol_id"
    | "run_date"
    | "operator"
    | "status"
    | "is_locked"
    | "hit_criteria"
    | "hit_criteria_set_by"
    | "hit_criteria_set_at"
  >;
}) {
  const canEdit = useCanEdit();
  const [editOpen, setEditOpen] = useState(false);
  const [namingOpen, setNamingOpen] = useState(false);
  const [channel, setChannel] = useState<string | undefined>();
  const [view, setView] = useState<CurveView>("measured");
  // The committed window; undefined lets the API choose.
  const [derivativeWindow, setDerivativeWindow] = useState<number | undefined>();
  // The smoothing in use: the one set in the Derivative view, else the API's default.
  const smoothing = view === "derivative" ? derivativeWindow : undefined;
  const {
    data: fetched,
    isLoading,
    isPlaceholderData,
    error,
    refetch,
  } = useRunCurves(runId, { channel, view, window: smoothing });
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
  // The run's recorded hit rule (never the protocol's recommendation by itself).
  const { data: protocol } = useProtocol(run?.protocol_id);
  const readouts = useMemo(() => protocol?.readout_definitions ?? [], [protocol]);
  const { applicable, other } = useMemo(
    () => splitRunRules(run?.hit_criteria ?? [], readouts),
    [run?.hit_criteria, readouts],
  );
  const hits = useMemo(
    () => (analysis && data ? hitWells(analysis, data.positions, applicable) : new Set<string>()),
    [analysis, data, applicable],
  );
  // The run's export: results, steps and traces, built from what this tab reads.
  // The names shown here (operator, step reviewers and assigners) ride along:
  // the export worker can't look people up without the person's sign-in.
  const { data: members } = useWorkspaceMembers();
  const buildExport = useCallback(
    (format: ExportFormat): ExportRequest | null => {
      if (!run) return null;
      const ids = [
        run.operator,
        ...(analysis?.steps ?? []).flatMap((s) => [s.changed_by, s.assigned_by]),
      ];
      const people: Record<string, string> = {};
      for (const id of ids) {
        const m = id ? members?.find((u) => u.user_id === id) : undefined;
        if (id && m) people[id] = m.name || m.email;
      }
      return {
        source: "run",
        format,
        filename_hint: `run-${protocol?.code ?? "report"}-${run.run_date}`,
        payload: { run_id: run.id, people },
      };
    },
    [run, analysis, members, protocol?.code],
  );
  // The value field of the open step form; a plot click fills it.
  const [stepValue, setStepValue] = useState("");
  // What the last click on a trace picked, and how far that click reached. It
  // selects only: every change is made through the step list, which this asks
  // for a form (or Accept).
  const [pick, setPick] = useState<(PeakPick & { reach: number }) | null>(null);
  const [moving, setMoving] = useState(false);
  const [request, setRequest] = useState<StepRequest | null>(null);
  // The peaks found in the traces of the position looked at (the one selected
  // last) and, when a spot or a peak is picked on another's trace, of that
  // one: never of every position. One read per position and smoothing serves
  // the snap and the hint alike.
  const lookedAt =
    analysis && selection.anchor !== null && selection.selected.has(selection.anchor)
      ? selection.anchor
      : undefined;
  const found = usePeakCandidates(runId, lookedAt, smoothing);
  const foundAtPick = usePeakCandidates(
    runId,
    pick && pick.wellId !== lookedAt ? pick.wellId : undefined,
    smoothing,
  );
  const clearPick = useCallback(() => {
    setPick(null);
    setMoving(false);
  }, []);
  useEffect(() => {
    if (!pick) return;
    const onKey = (e: KeyboardEvent) => {
      // An Escape that closed a menu or a dialog was meant for that.
      if (e.key === "Escape" && !e.defaultPrevented) clearPick();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [pick, clearPick]);
  const channelKey = set?.channel ?? null;
  const pickedId = pick?.stepId ?? null;
  const steps = useMemo(() => {
    if (!analysis) return undefined;
    const byWell = new Map<string, PlotStep[]>();
    for (const s of analysis.steps) {
      if (s.channel_key !== channelKey || s.status === "rejected") continue;
      byWell.set(s.well_id, [
        ...(byWell.get(s.well_id) ?? []),
        { value: s.value, reviewed: s.status === "accepted", picked: s.id === pickedId },
      ]);
    }
    return byWell;
  }, [analysis, channelKey, pickedId]);
  // Once per run: with nothing selected yet, start on the row most worth a look.
  const [leadWindow, setLeadWindow] = useState<string | null>(null);
  const [shown, setShown] = useState<readonly string[]>([]);
  const initialised = useRef<string | null>(null);
  useEffect(() => {
    if (!analysis || !data || initialised.current === runId) return;
    initialised.current = runId;
    if (selection.selected.size > 0) return;
    const onSignal = analysis.windows.filter((w) => w.channel_key === data.channel);
    const lead = onSignal.find((w) => w.window === leadWindow) ?? onSignal[0];
    const rows = resultRows(
      onSignal,
      data.positions,
      analysis.steps,
      analysis.step_checks,
      analysis.outside_every_window,
    );
    const id = firstToSelect(rows, lead ? [lead.window] : []);
    if (id) setSelection(applyClick(EMPTY_SELECTION, [id], id, { shift: false, toggle: false }));
  }, [analysis, data, runId, selection, leadWindow]);

  const windows = useMemo(
    () =>
      analysis?.windows
        .filter((w) => w.channel_key === channelKey)
        .map((w) => ({
          low: w.low,
          high: w.high,
          label: w.window,
          active: shown.includes(w.window),
        })),
    [analysis, channelKey, shown],
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
  const anchorBatch = anchor?.well_type === "sample" ? anchor.batch_id : null;
  const series =
    lead && analysis && anchorBatch
      ? batchSeries(lead, data.positions, anchorBatch, analysis.steps)
      : [];
  const oneDose = !!anchorBatch && batchDoseCount(data.positions, anchorBatch) === 1;
  // The batch's concentrations that have no ΔTm in the lead window.
  const gaps = lead && anchorBatch ? seriesGaps(lead, data.positions, anchorBatch) : null;
  const gapNote = gaps?.missing
    ? `No ΔTm at ${gaps.missing} of ${gaps.total} concentrations`
    : null;
  const selectedPositions = orderedPositions(set).filter((p) => selection.selected.has(p.well_id));
  const editRefusal = run ? labellingEditRefusal(run) : null;

  /** The peaks drawn for a position: counted, on the shown signal. */
  const drawnPeaks = (wellId: string) =>
    (analysis?.steps ?? []).filter(
      (s) => s.well_id === wellId && s.channel_key === set.channel && s.status !== "rejected",
    );
  // The pick shows while its position is drawn and, for a peak, while the peak is.
  const pickPosition = data.positions.find(
    (p) =>
      p.well_id === pick?.wellId &&
      (selection.selected.has(p.well_id) || (showReferences && p.well_type === "reference")),
  );
  const pickedStep = (pick && drawnPeaks(pick.wellId).find((s) => s.id === pick.stepId)) ?? null;
  const picked =
    pick && pickPosition && (pick.stepId === null || pickedStep)
      ? { ...pick, position: pickPosition, step: pickedStep }
      : null;
  /** What a form opened from a click at x on a position's trace offers: the
   *  found peak of the shown signal nearest within the click's reach, with the
   *  temperature clicked beside it; else (none there, or the found peaks are
   *  not loaded) the temperature clicked. */
  const offered = (wellId: string, x: number, reach: number) => {
    const read = wellId === lookedAt ? found : wellId === pick?.wellId ? foundAtPick : null;
    const onSignal = read?.data?.signals.find((s) => s.channel_key === set.channel);
    const clicked = stepInput(x);
    const peak = snapTarget(onSignal?.candidates ?? [], x, reach);
    const value = peak ? stepInput(peak.value) : clicked;
    return value === clicked ? { value } : { value, clicked };
  };
  // A click on a trace picks the nearest drawn peak of that position, else the
  // spot; an open Add or Correct form takes the temperature either way.
  // ponytail: with Markers off the peaks are not drawn yet can still be picked;
  // telling would need the viewer to report its switch.
  const onPlotPick = (at: { wellId: string; x: number; visibleSpan: number }) => {
    setStepValue(stepInput(at.x));
    if (!analysis) return;
    setMoving(false);
    // As far as a click reaches for a drawn peak, it reaches for a found one.
    const reach = pickReach(at.visibleSpan);
    if (moving && picked?.step && picked.wellId === at.wellId) {
      setRequest({
        kind: "correct",
        stepId: picked.step.id,
        ...offered(at.wellId, at.x, reach),
      });
      return;
    }
    const peak = nearestPeak(drawnPeaks(at.wellId), at.x, at.visibleSpan);
    setPick({ wellId: at.wellId, x: at.x, stepId: peak?.id ?? null, reach });
  };
  const ask = (next: StepRequest) => {
    setMoving(false);
    setRequest(next);
  };
  const showSignal = (key: string) => {
    setChannel(key);
    // The peaks, and so what a spot is, belong to the signal.
    clearPick();
  };

  // Where the position looked at reads "No peak" in the lead window, the other
  // signals that show a step inside that window's range.
  const lookedAtPosition = data.positions.find((p) => p.well_id === lookedAt);
  // As the results table reads it.
  const reading =
    analysis && lead && lookedAtPosition
      ? resultRows(
          [lead],
          [lookedAtPosition],
          analysis.steps,
          analysis.step_checks,
          analysis.outside_every_window,
        )[0]?.cells[lead.window]?.status
      : undefined;
  const foundSignals = found.data?.signals;
  const hints =
    lead && reading === "no_step" && foundSignals
      ? hintsFor(
          lead,
          new Map(
            set.channels
              .filter((c) => c.key !== set.channel)
              .map((c) => [
                c.key,
                foundSignals.find((s) => s.channel_key === c.key)?.candidates ?? [],
              ]),
          ),
        ).map((h) => ({
          ...h,
          // The signal's name as the signal switch shows it.
          label: set.channels.find((c) => c.key === h.signal)?.label ?? h.signal,
        }))
      : [];

  // The grid is the selector; without an analysis (it failed) the viewer's own stays.
  const fallback = !analysis && !melting.isLoading;
  const signalWindows = analysis?.windows.filter((w) => w.channel_key === set.channel) ?? [];
  const unit = currentChannel(set)?.x_unit ?? "";
  // A picked reference trace is drawn without being selected: its peaks are
  // listed while it is picked, so the forms have their position.
  const listed =
    picked && !selection.selected.has(picked.wellId)
      ? [...selectedPositions, picked.position]
      : selectedPositions;
  const underPlot = analysis && selectedPositions.length > 0 && (
    <>
      {picked && (
        <PeakPickBar
          pick={picked}
          position={picked.position}
          step={picked.step}
          windows={signalWindows}
          useAsTm={canUseAsTm(
            picked.step ?? { well_id: picked.wellId, value: picked.x },
            analysis,
            set.channel,
            signalWindows,
          )}
          unit={unit}
          refusal={
            analysis.edit_refusal ||
            (canEdit ? null : "Read-only access — peaks cannot be changed.")
          }
          moving={moving}
          onAssign={(window) => ask({ kind: "assign", stepId: picked.step?.id, window })}
          onAccept={() => ask({ kind: "accept", stepId: picked.step?.id })}
          onReject={() => ask({ kind: "reject", stepId: picked.step?.id })}
          onMove={() => setMoving((on) => !on)}
          onAdd={(window) =>
            ask({
              kind: "add",
              wellId: picked.wellId,
              window,
              ...offered(picked.wellId, picked.x, picked.reach),
            })
          }
          onClear={clearPick}
        />
      )}
      <MeltingStepsPanel
        runId={runId}
        analysis={analysis}
        positions={listed}
        channel={set.channel}
        windows={signalWindows}
        lookedAt={lookedAt}
        lead={lead}
        unit={unit}
        value={stepValue}
        onValueChange={setStepValue}
        request={request}
        onRequestHandled={() => setRequest(null)}
        pickedId={picked?.stepId ?? null}
        // A spot picked on the new peak's trace has become that peak: nothing more to add there.
        onAdded={(step) =>
          setPick((p) =>
            p && p.stepId === null && p.wellId === step.well_id
              ? { ...p, x: step.value, stepId: step.id }
              : p,
          )
        }
        underList={
          hints.length > 0 && (
            <ul aria-label="Steps on other signals" className="space-y-1 text-sm">
              {hints.map((h) => (
                <li key={h.signal} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  {/* Named, as the list names its peaks' positions, when it lists several. */}
                  {listed.length > 1 && (
                    <span className="font-medium">{lookedAtPosition?.position_label}</span>
                  )}
                  <span className="text-muted-foreground">
                    {`${h.label} shows a step near ${h.value.toFixed(1)} ${unit}.`}
                  </span>
                  <Button
                    type="button"
                    size="xs"
                    variant="outline"
                    onClick={() => showSignal(h.signal)}
                  >
                    {`Show ${h.label}`}
                  </Button>
                </li>
              ))}
            </ul>
          )
        }
        onReload={melting.refetch}
      />
      {lead && anchor && series.length > 0 ? (
        <ConcentrationChart
          title={`${[sampleTextOf(anchor), batchSuffix(anchor)].filter(Boolean).join(" · ")} — ΔTm (${lead.window}) by concentration`}
          caption={[anchorBatch && seriesCaption(lead, anchorBatch, doseUnit), gapNote]
            .filter(Boolean)
            .join(" · ")}
          points={series}
          doseUnit={doseUnit}
          hits={hits}
          band={bandFor(applicable, lead.window)}
          selected={selection.selected}
          onSelect={(id) =>
            setSelection(applyClick(selection, [id], id, { shift: false, toggle: false }))
          }
        />
      ) : oneDose ? (
        <p className="text-sm text-muted-foreground">
          Only one concentration of this batch in this run.
        </p>
      ) : (
        gapNote && <p className="text-sm text-muted-foreground">{`${gapNote}; nothing to chart`}</p>
      )}
    </>
  );
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
          {analysis && run && canEdit && (
            <NamePeaksDialog
              open={namingOpen}
              onOpenChange={setNamingOpen}
              runId={runId}
              protocolId={run.protocol_id}
              // Every position's trace on the shown signal, so also a reference that is not drawn.
              set={set}
              analysis={analysis}
              canRecalculate={run.status !== "approved" && !run.is_locked}
            />
          )}
          {analysis ? (
            <MeltResultsPanel
              analysis={analysis}
              positions={data.positions}
              channel={set.channel}
              doseUnit={doseUnit}
              selection={selection}
              onSelectionChange={setSelection}
              headerAction={
                <>
                  {run && <ExportToolbar formats={RUN_FORMATS} buildRequest={buildExport} />}
                  {editLabelling}
                </>
              }
              onLeadWindowChange={setLeadWindow}
              onShownWindowsChange={setShown}
              hits={hits}
              applicable={applicable}
              hitRule={
                run && (
                  <MeltHitRule
                    run={run}
                    readoutDefinitions={readouts}
                    recommendation={protocol?.recommended_hit_criteria ?? null}
                    applicable={applicable}
                    other={other}
                    canEdit={canEdit}
                  />
                )
              }
              // Naming changes the protocol, not the run: offered on any run status.
              onNamePeaks={run && canEdit ? () => setNamingOpen(true) : undefined}
              reviewAction={
                canEdit && (
                  <AcceptAllPeaks runId={runId} analysis={analysis} channel={set.channel} />
                )
              }
            />
          ) : melting.isLoading ? (
            <Skeleton data-testid="results-loading" className={cn("w-full", PLOT_HEIGHT)} />
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Could not load the analysis. Reload the page and try again.
            </p>
          )}
        </div>
        <div className="order-1 min-w-0 self-start @[1100px]:sticky @[1100px]:top-4 @[1100px]:order-2 @[1100px]:col-span-5">
          <CurveViewer
            set={set}
            steps={steps}
            windows={windows}
            onPlotPick={onPlotPick}
            showReferences={showReferences}
            onShowReferencesChange={setShowReferences}
            selection={selection}
            onSelectionChange={setSelection}
            channel={channel}
            onChannelChange={showSignal}
            onViewChange={setView}
            onWindowChange={setDerivativeWindow}
            pending={isPlaceholderData}
            failed={failed}
            exportName={`traces-run-${shortId(data.run_id)}`}
            hideSelector={!fallback}
            collapseReportedTable={!fallback}
            selectorAction={fallback && editLabelling}
            compactControls
            belowPlot={underPlot}
          />
        </div>
      </div>
    </div>
  );
}
