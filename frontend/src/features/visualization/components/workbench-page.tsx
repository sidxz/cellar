"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { Alert } from "@/shared/components/ui/alert";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { AlertTriangle, ChartScatter, Database, Info, Loader2, Rows3, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { type Dispatch, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDataset } from "../hooks/use-dataset";
import {
  type DerivedAction,
  type DerivedEntry,
  derivedReducer,
  runnable,
  setsOf,
  useDerived,
} from "../hooks/use-derived";
import { useRunRowCounts } from "../hooks/use-run-row-counts";
import { errorText } from "../lib/api-errors";
import type { ViewConfig } from "../lib/config-schema";
import { resolveUserColumns } from "../lib/dataset";
import { defaultPanels, panelDefaults } from "../lib/default-panels";
import {
  type DerivedSpec,
  jobMoleculeIds,
  rgroupPositions,
  rgroupSetOf,
  withDerived,
} from "../lib/derived";
import { type Filter, substructureSummary } from "../lib/filters";
import { type Carry, carryConfig, switchNote } from "../lib/level-switch";
import { countsAtLevel } from "../lib/levels";
import { MAX_ROWS } from "../lib/limits";
import { resolveViewConfig } from "../lib/saved-view";
import { visualizeHref } from "../lib/source-url";
import { withSeenLabels } from "../lib/traces/common";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import {
  MAX_PANELS,
  type PanelConfig,
  type PanelPatch,
  type Snapshot,
  makePanel,
} from "../store/workbench-store";
import type { Dataset, DatasetSource, Level, SavedView } from "../types";
import { AddColumnsMenu } from "./add-columns-menu";
import { AddPlotMenu } from "./add-plot-menu";
import { CurvesDialog, type CurvesTarget, curvesTarget } from "./curves-dialog";
import { DerivedColumnsBar, derivedTitle } from "./derived-columns-bar";
import { DerivedRunner, type Rematch, SubstructureRematch } from "./derived-runner";
import { ClustersDialog } from "./derived/clusters-dialog";
import { RGroupsDialog } from "./derived/rgroups-dialog";
import { SeriesDialog } from "./derived/series-dialog";
import { ExportMenu } from "./export-menu";
import { FilterRail, NoRowsMatch } from "./filter-rail";
import { PanelGrid } from "./panel-grid";
import type { EditField } from "./panels/panel-frame";
import { PlotSettingsSheet } from "./plot-settings-sheet";
import { RunPickerDialog } from "./run-picker-dialog";
import { SaveCollectionButton } from "./save-collection-dialog";
import { SelectionStrip } from "./selection-strip";
import { ViewControls } from "./view-controls";
import { WorkbenchBody } from "./workbench-body";
import {
  LevelSwitcher,
  SourceBar,
  type View,
  WorkbenchHeader,
  useSourceRuns,
} from "./workbench-header";
import { WorkbenchTable, type WorkbenchTableHandle } from "./workbench-table";

/** A saved view the workbench opens: its plots and filters, fitted to today's data. */
type OpenedView = { view: SavedView; config: ViewConfig };

/** The full-page workbench for a protocol (some or all runs) or one run, at one row level;
 * with ``view``, opened on that saved view's plots and filters. */
export function WorkbenchPage({
  source,
  level,
  view,
}: {
  source: DatasetSource | null;
  level: Level;
  view?: OpenedView;
}) {
  // A run's workbench changing runs moves to its protocol (another key) yet stays the same
  // workbench: ``moved`` keeps the key it had for the one it moved to.
  const [moved, setMoved] = useState<{ to: string; as: string } | null>(null);
  if (!source) {
    return (
      <EmptyState
        icon={ChartScatter}
        title="Nothing to visualize"
        description="Open the workbench with Visualize on a protocol or a run."
      />
    );
  }
  // Chemistry columns belong to the protocol or run; they survive level and run changes.
  const key = sourceKey(source);
  const as = moved?.to === key ? moved.as : key;
  const onMove = (next: DatasetSource) => {
    const to = sourceKey(next);
    if (to !== key) setMoved({ to, as });
  };
  return <Workbench key={as} source={source} level={level} view={view} onMove={onMove} />;
}

const sourceKey = (source: DatasetSource) =>
  source.kind === "protocol" ? source.protocolId : source.runId;

/** The last view change: the view it leads to, the level it left and what it takes along. */
type Switch = { to: string; from: Level; carry: Carry; dismissed?: boolean };

function Workbench({
  source,
  level,
  view,
  onMove,
}: {
  source: DatasetSource;
  level: Level;
  view?: OpenedView;
  /** Told of each change of source this workbench makes itself. */
  onMove: (next: DatasetSource) => void;
}) {
  const query = useDataset(source, level);
  const nameOf = useMemberNames();
  const router = useRouter();
  const protocolId = source.kind === "protocol" ? source.protocolId : null;
  const { data: rowCounts } = useRunRowCounts(protocolId);
  const { runs } = useSourceRuns(source);
  const [switched, setSwitched] = useState<Switch | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [editing, setEditing] = useState<{ panelId: string; focusField?: EditField } | null>(null);
  const closeEditor = useCallback(() => setEditing(null), []);
  const tableRef = useRef<WorkbenchTableHandle>(null);
  const [curves, setCurves] = useState<CurvesTarget | null>(null);
  const [viewNoteOpen, setViewNoteOpen] = useState(true);
  const [removedNote, setRemovedNote] = useState<string | null>(null);
  const { entries, readySets, dispatch, newRGroups } = useDerived();
  const [adding, setAdding] = useState<DerivedSpec["kind"] | null>(null);
  // The saved view as last saved here, outliving each store (one per source and level), so a
  // store opened on carried edits still tells them from what is saved.
  const [lastSaved, setLastSaved] = useState<Snapshot | null>(null);

  const base = useMemo(
    () => (query.data ? resolveUserColumns(query.data, nameOf) : undefined),
    [query.data, nameOf],
  );
  // Every column label shown here, so a filter or plot that undo brings back onto a removed
  // chemistry column still reads by name.
  const seenLabels = useRef(new Map<string, string>()).current;
  // Chemistry columns, computed per compound, joined onto whatever level is loaded.
  const ds = useMemo(
    () => base && withSeenLabels(withDerived(base, readySets), seenLabels),
    [base, readySets, seenLabels],
  );
  // The compounds a new chemistry job runs over: every one with a structure.
  const moleculeIds = useMemo(() => (base ? jobMoleculeIds(base) : []), [base]);
  // How the chemistry columns were made: what a saved view keeps of them.
  const specs = useMemo(() => entries.map((e) => e.spec), [entries]);
  const addSet = (spec: DerivedSpec) => dispatch({ type: "add", spec, moleculeIds });
  const specOf = <K extends DerivedSpec["kind"]>(kind: K) =>
    entries.find((e) => e.spec.kind === kind)?.spec as
      | Extract<DerivedSpec, { kind: K }>
      | undefined;
  for (const c of ds?.columns ?? []) seenLabels.set(c.key, c.label);
  // A row above Runs pools the source runs that count at its level; its curves come from those.
  const countedRunIds = useMemo(
    () => runs.filter((r) => countsAtLevel(level, r.status)).map((r) => r.id),
    [runs, level],
  );
  const openCurves = useCallback(
    (key: string, i: number) => ds && setCurves(curvesTarget(ds, key, i, countedRunIds)),
    [ds, countedRunIds],
  );

  // A change of level, runs or compared protocols refetches (the URL carries it); the plots
  // and filters follow when its data arrives, fitted to its columns. Within one level rows
  // keep their ids, so the selected rows still there stay selected. Not an undo step.
  const shown = viewKey(source, level);
  const carry = switched?.to === shown ? switched.carry : null;
  // Each level's plots and filters as last left: a level visited before reopens on them
  // (fitted to its columns then), so Wells → Runs → Wells gets the Wells plots back.
  const left = useRef(new Map<Level, Carry>()).current;
  const changeView = (next: View, take: Carry | null) => {
    // A change before the last one's data arrived keeps the level that one left.
    const from = switched && take === switched.carry ? switched.from : level;
    if (take) left.set(level, take);
    const back = next.level !== level ? left.get(next.level) : undefined;
    // The selection is the one left behind: it is what the note says was cleared.
    const brought = back && take ? { ...back, selectedIds: take.selectedIds } : take;
    setSwitched(brought && { to: viewKey(next.source, next.level), from, carry: brought });
    onMove(next.source);
    router.replace(visualizeHref(next.source, next.level, view?.view.id), { scroll: false });
  };
  const switchLevel = (next: Level, take: Carry | null) =>
    changeView({ source, level: next }, take);
  const sameLevel = switched?.from === level;
  const carried = useMemo(() => {
    if (!ds || !carry) return null;
    const rows = new Set(ds.row_ids);
    return { ...carryConfig(carry, ds), selection: carry.selectedIds.filter((id) => rows.has(id)) };
  }, [ds, carry]);
  let note: string | null = null;
  if (carried && carry && !switched?.dismissed) {
    note = !sameLevel
      ? switchNote(level, carried.dropped, carry.selectedIds.length)
      : carried.dropped.length > 0
        ? `Not available now: ${carried.dropped.join(", ")}.`
        : null;
  }

  // A saved view's chemistry columns are computed again for today's data, and its
  // substructure queries matched again, before its plots and filters open on them.
  const toRegenerate = useRef(view?.config.derived ?? []);
  useEffect(() => {
    if (!base || toRegenerate.current.length === 0) return;
    for (const spec of toRegenerate.current) dispatch({ type: "add", spec, moleculeIds });
    toRegenerate.current = [];
  }, [base, moleculeIds, dispatch]);
  const [rematched, setRematched] = useState<Record<string, Rematch>>({});
  const onRematched = useCallback(
    (id: string, outcome: Rematch) => setRematched((m) => ({ ...m, [id]: outcome })),
    [],
  );
  // The saved view as opened, fixed once (later changes have notes of their own).
  const opened = useRef<Opened | null>(null);
  const toMatch = view && !opened.current ? view.config.filters.filter(unmatched(rematched)) : [];
  const regenerating =
    view !== undefined &&
    !opened.current &&
    (toRegenerate.current.length > 0 ||
      entries.some((e) => e.status === "running") ||
      toMatch.length > 0);
  if (view && ds && !regenerating && !opened.current) {
    opened.current = openSaved(view.config, ds, entries, rematched);
  }
  // A saved view opens on its own plots and filters, less what today's data lacks; the note
  // lists that by saved label, after whatever the server could not resolve (removed runs…)
  // and the chemistry that couldn't be made again.
  const resolved = opened.current;
  const viewLines = [
    ...(view?.view.unresolved ?? []),
    ...(resolved?.lines ?? []),
    ...(!carry && resolved?.missing.length
      ? [`Not available any more: ${resolved.missing.join(", ")}.`]
      : []),
  ];
  const viewNote = viewNoteOpen && viewLines.length > 0 && (
    <Alert className="flex items-start gap-2 py-2">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1 space-y-0.5">
        {viewLines.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
      <Button
        size="icon"
        variant="ghost"
        className="h-6 w-6 shrink-0"
        aria-label="Dismiss view note"
        onClick={() => setViewNoteOpen(false)}
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </Alert>
  );

  // Known before the dataset arrives (the server refuses it with a bare 422), so the
  // chemist sees the actual count and goes straight back to the picker. Wells only: the
  // run counts are well counts.
  const requested = useMemo(() => {
    if (level !== "wells" || source.kind !== "protocol" || !rowCounts) return null;
    const ids = source.runIds ?? Object.keys(rowCounts.counts);
    return ids.reduce((n, id) => n + (rowCounts.counts[id] ?? 0), 0);
  }, [level, source, rowCounts]);

  let body: React.ReactNode;
  if (requested !== null && requested > MAX_ROWS) {
    body = (
      <EmptyState
        icon={Rows3}
        title="Too many wells to load at once"
        description={`These runs have ${requested.toLocaleString()} wells; the limit is ${MAX_ROWS.toLocaleString()}.`}
        action={{ label: "Choose fewer runs", onClick: () => setPickerOpen(true) }}
      />
    );
  } else if (query.isPending) {
    body = <LoadingSkeleton />;
  } else if (query.isError && !ds) {
    // A failed refetch keeps the data already on screen; only a first load fails here.
    body = (
      <EmptyState
        icon={AlertTriangle}
        title="Couldn't load the data"
        description={errorText(query.error)}
        action={{ label: "Retry", onClick: () => void query.refetch() }}
      />
    );
  } else if (
    (!ds || ds.row_count === 0) &&
    runs.length > 0 &&
    !runs.some((r) => countsAtLevel(level, r.status))
  ) {
    body = (
      <EmptyState
        icon={Database}
        title="No completed or approved runs here"
        description="Batches and Compounds count only completed or approved runs."
        action={{ label: "Show Runs", onClick: () => switchLevel("runs", carry) }}
      />
    );
  } else if (!ds || ds.row_count === 0) {
    body = (
      <EmptyState
        icon={Database}
        title="These runs have no readout data yet"
        description="Import readouts on the run page, then open the workbench again."
      />
    );
  } else if (regenerating) {
    body = (
      <Regenerating
        entries={entries}
        ds={ds}
        dispatch={dispatch}
        moleculeIds={moleculeIds}
        matching={toMatch.length}
      />
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Always mounted, so screen readers announce the notes when they appear. */}
      <output className="sr-only">{[note, removedNote].filter(Boolean).join(" ")}</output>
      {runnable(entries).map((e) => (
        <DerivedRunner
          key={`${e.spec.id}:${e.attempt}`}
          entry={e}
          ds={base}
          readySets={readySets}
          dispatch={dispatch}
        />
      ))}
      {base &&
        toMatch.map((f) => (
          <SubstructureRematch key={f.id} filter={f} ds={base} onDone={onRematched} />
        ))}
      {body || !ds ? (
        <>
          <SourceBar
            source={source}
            level={level}
            onChange={(next) => changeView({ source: next, level }, carry)}
          />
          <LevelSwitcher
            level={level}
            source={source}
            onChange={(next) => switchLevel(next, carry)}
          />
          {viewNote}
          {body}
        </>
      ) : (
        // Keyed by the source and level (and saved view), not the data revision: new data
        // for the same view never resets the chemist's plots, filters, selection or history.
        <WorkbenchProvider
          key={view ? `${view.view.id}:${shown}` : shown}
          initialPanels={carried?.panels ?? resolved?.panels ?? initialPanels(ds)}
          initialFilters={carried?.filters ?? resolved?.filters}
          initialSelection={sameLevel ? carried?.selection : undefined}
          saved={lastSaved ?? resolved ?? undefined}
          onSaved={setLastSaved}
        >
          <WorkbenchHeader
            source={source}
            ds={ds}
            level={level}
            onViewChange={changeView}
            exportMenu={<ExportMenu ds={ds} table={tableRef} />}
            addPlotMenu={<AddPlotMenu ds={ds} />}
            addColumnsMenu={
              <AddColumnsMenu
                onPick={setAdding}
                disabledReason={
                  moleculeIds.length ? undefined : "No compound in this dataset has a structure"
                }
              />
            }
            viewControls={<ViewControls source={source} level={level} ds={ds} derived={specs} />}
          />
          {entries.length > 0 && base && (
            <DerivedStrip
              entries={entries}
              base={base}
              ds={ds}
              dispatch={dispatch}
              onRemoved={setRemovedNote}
            />
          )}
          {viewNote}
          {note && (
            <Note
              text={note}
              onDismiss={() => setSwitched((s) => s && { ...s, dismissed: true })}
            />
          )}
          {removedNote && <Note text={removedNote} onDismiss={() => setRemovedNote(null)} />}
          <WorkbenchBody
            plots={
              <NoRowsMatch ds={ds}>
                <PanelGrid
                  ds={ds}
                  onEdit={(panelId, focusField) => setEditing({ panelId, focusField })}
                />
              </NoRowsMatch>
            }
            table={
              <>
                <SelectionStrip ds={ds} />
                <WorkbenchTable
                  ref={tableRef}
                  ds={ds}
                  actions={<SaveCollectionButton ds={ds} />}
                  onOpenCurves={openCurves}
                />
              </>
            }
            rail={<FilterRail ds={ds} labels={seenLabels} />}
            editor={
              editing && (
                <PlotSettingsSheet
                  ds={ds}
                  panelId={editing.panelId}
                  focusField={editing.focusField}
                  onClose={closeEditor}
                />
              )
            }
          />
        </WorkbenchProvider>
      )}
      {curves && <CurvesDialog {...curves} open onOpenChange={() => setCurves(null)} />}
      {adding === "rgroups" && (
        <RGroupsDialog
          open
          onOpenChange={() => setAdding(null)}
          moleculeIds={moleculeIds}
          onApply={(core) => addSet(newRGroups(core))}
        />
      )}
      {adding === "clusters" && (
        <ClustersDialog
          open
          onOpenChange={() => setAdding(null)}
          compoundCount={moleculeIds.length}
          initialThreshold={specOf("clusters")?.threshold}
          onApply={(threshold) => addSet({ id: "clusters", kind: "clusters", threshold })}
        />
      )}
      {adding === "series" && base && (
        <SeriesDialog
          open
          onOpenChange={() => setAdding(null)}
          ds={base}
          moleculeIds={moleculeIds}
          rgroupSets={readySets.filter((s) => s.spec.kind === "rgroups")}
          initial={specOf("series")?.members}
          onApply={(members) => addSet({ id: "series", kind: "series", members })}
        />
      )}
      {pickerOpen && source.kind === "protocol" && (
        <RunPickerDialog
          protocolId={source.protocolId}
          initialRunIds={source.runIds}
          level={level}
          open
          onOpenChange={setPickerOpen}
          onConfirm={(runIds) => changeView({ source: { ...source, runIds }, level }, carry)}
        />
      )}
    </div>
  );
}

type SavedQuery = Extract<ViewConfig["filters"][number], { kind: "substructure" }>;

/** A saved substructure query not matched again yet. */
const unmatched =
  (rematched: Record<string, Rematch>) =>
  (f: ViewConfig["filters"][number]): f is SavedQuery =>
    f.kind === "substructure" && !rematched[f.id];

/** A saved view as opened: its plots and filters fitted to today's data (substructure
 * filters with today's matches), what is missing, and what couldn't be made again. */
type Opened = { panels: PanelConfig[]; filters: Filter[]; missing: string[]; lines: string[] };

function openSaved(
  cfg: ViewConfig,
  ds: Dataset,
  entries: DerivedEntry[],
  rematched: Record<string, Rematch>,
): Opened {
  const { panels, filters, missing } = resolveViewConfig(cfg, ds);
  const lines = entries.flatMap((e) => {
    const title = derivedTitle(e.spec);
    if (e.status === "failed") return [`${title} couldn't be regenerated: ${e.error}`];
    if (e.status === "cancelled") return [`${title} was cancelled; its columns weren't made.`];
    return [];
  });
  const matched = filters.map((f): Filter => {
    const outcome = f.kind === "substructure" ? rematched[f.id] : undefined;
    if (!outcome || f.kind !== "substructure") return f;
    if ("error" in outcome) {
      lines.push(`The filter “${substructureSummary(f)}” couldn't be re-run: ${outcome.error}`);
      return f;
    }
    return { ...f, ...outcome };
  });
  return { panels, filters: matched, missing, lines };
}

/** A saved view's chemistry being made again for today's data: each job's progress with
 * Cancel. The view opens once every one has finished, failed or been cancelled. */
function Regenerating({
  entries,
  ds,
  dispatch,
  moleculeIds,
  matching,
}: {
  entries: DerivedEntry[];
  ds: Dataset;
  dispatch: Dispatch<DerivedAction>;
  moleculeIds: string[];
  matching: number;
}) {
  return (
    <div className="flex flex-col gap-2">
      <output className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Regenerating chemistry columns…
      </output>
      {entries.length > 0 && (
        <DerivedColumnsBar
          entries={entries}
          ds={ds}
          plotsFull={false}
          onCancel={(id) => dispatch({ type: "cancel", id })}
          onRetry={(id) => dispatch({ type: "retry", id })}
          onRemove={(id) => dispatch({ type: "remove", id })}
          onRecompute={(id) => dispatch({ type: "recompute", id, moleculeIds })}
        />
      )}
      {matching > 0 && (
        <p className="text-sm text-muted-foreground">
          {matching === 1
            ? "Matching 1 substructure filter…"
            : `Matching ${matching} substructure filters…`}
        </p>
      )}
    </div>
  );
}

/** A dismissable note under the header (read out by the page's status line). */
function Note({ text, onDismiss }: { text: string; onDismiss: () => void }) {
  return (
    <div className="flex items-start gap-2 rounded-md border bg-card px-3 py-2 text-sm">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      {/* Read out by the status line; hidden here so it is not heard twice. */}
      <p aria-hidden="true" className="min-w-0 flex-1">
        {text}
      </p>
      <Button
        size="icon"
        variant="ghost"
        className="h-6 w-6 shrink-0"
        aria-label="Dismiss note"
        onClick={onDismiss}
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

/** The chemistry columns bar, wired to the workbench: removing a set drops the filters and
 * plot fields on its columns as one undo step and says what went; its plot button adds the
 * cluster map or an R-group matrix. */
function DerivedStrip({
  entries,
  base,
  ds,
  dispatch,
  onRemoved,
}: {
  entries: DerivedEntry[];
  base: Dataset;
  ds: Dataset;
  dispatch: Dispatch<DerivedAction>;
  onRemoved: (note: string | null) => void;
}) {
  const panels = useWorkbench((s) => s.panels);
  const filters = useWorkbench((s) => s.filters);
  const setConfig = useWorkbench((s) => s.setConfig);
  const addPanel = useWorkbench((s) => s.addPanel);
  const setMaximized = useWorkbench((s) => s.setMaximized);
  const specOf = (id: string) => entries.find((e) => e.spec.id === id)?.spec;

  const remove = (id: string) => {
    const spec = specOf(id);
    const after = withDerived(base, setsOf(derivedReducer(entries, { type: "remove", id })));
    // Rows keep their ids, so a selection filter stays.
    const fitted = carryConfig(
      {
        panels,
        filters: filters.filter((f) => f.kind !== "rows"),
        selectedIds: [],
        columns: ds.columns,
      },
      after,
    );
    dispatch({ type: "remove", id });
    if (!spec || fitted.dropped.length === 0) return onRemoved(null);
    setConfig(
      fitted.panels,
      filters.filter((f) => f.kind === "rows" || fitted.filters.includes(f)),
    );
    onRemoved(`${derivedTitle(spec)} removed. Not available now: ${fitted.dropped.join(", ")}.`);
  };

  const plot = (id: string) => {
    const added =
      specOf(id)?.kind === "clusters"
        ? addPanel("scatter", {
            x: "chem:clusters:x",
            y: "chem:clusters:y",
            appearance: { colorBy: "chem:clusters:id" },
          })
        : addPanel("rgroup-matrix", matrixOf(ds, id));
    // A maximized plot would hide the new one.
    if (added) setMaximized(null);
  };

  return (
    <DerivedColumnsBar
      entries={entries}
      ds={ds}
      plotsFull={panels.length >= MAX_PANELS}
      onCancel={(id) => dispatch({ type: "cancel", id })}
      onRetry={(id) => dispatch({ type: "retry", id })}
      onRemove={remove}
      onRecompute={(id) => dispatch({ type: "recompute", id, moleculeIds: jobMoleculeIds(base) })}
      onPlot={plot}
    />
  );
}

/** An R-group matrix of set ``id``: its R1 rows × R2 columns (else R1). */
function matrixOf(ds: Dataset, id: string): PanelPatch {
  const positions = rgroupPositions(ds).filter((k) => rgroupSetOf(k) === `chem:${id}`);
  return {
    ...panelDefaults(ds, "rgroup-matrix"),
    category: positions[0],
    x: positions[1] ?? positions[0],
  };
}

// The URL: one spelling per view, whatever order the source's fields were set in.
const viewKey = (source: DatasetSource, level: Level) => visualizeHref(source, level);

// The provider reads this once (its store is created on mount), so the ids made here stick.
const initialPanels = (ds: Dataset) => defaultPanels(ds).map((p) => makePanel(p.type, p.defaults));

export function LoadingSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-full" />
      <div className="flex gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <Skeleton className="h-[max(320px,45dvh)]" />
          <Skeleton className="h-64" />
        </div>
        <Skeleton className="hidden h-96 w-72 xl:block" />
      </div>
    </div>
  );
}
