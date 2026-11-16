"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { Alert } from "@/shared/components/ui/alert";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { ApiError } from "@/shared/lib/api/custom-instance";
import { AlertTriangle, ChartScatter, Database, Info, Rows3, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useRef, useState } from "react";
import { useDataset } from "../hooks/use-dataset";
import { useRunRowCounts } from "../hooks/use-run-row-counts";
import type { ViewConfig } from "../lib/config-schema";
import { resolveUserColumns } from "../lib/dataset";
import { defaultPanels } from "../lib/default-panels";
import { type Carry, carryConfig, switchNote } from "../lib/level-switch";
import { countsAtLevel } from "../lib/levels";
import { MAX_ROWS } from "../lib/limits";
import { resolveViewConfig } from "../lib/saved-view";
import { visualizeHref } from "../lib/source-url";
import { WorkbenchProvider } from "../store/workbench-context";
import { makePanel } from "../store/workbench-store";
import type { Dataset, DatasetSource, Level, SavedView } from "../types";
import { AddPlotMenu } from "./add-plot-menu";
import { CurvesDialog, type CurvesTarget, curvesTarget } from "./curves-dialog";
import { ExportMenu } from "./export-menu";
import { FilterRail, NoRowsMatch } from "./filter-rail";
import { PanelGrid } from "./panel-grid";
import type { EditField } from "./panels/panel-frame";
import { PlotSettingsSheet } from "./plot-settings-sheet";
import { RunPickerDialog } from "./run-picker-dialog";
import { SaveCollectionButton } from "./save-collection-dialog";
import { SelectionStrip } from "./selection-strip";
import { WorkbenchBody } from "./workbench-body";
import { LevelSwitcher, SourceBar, WorkbenchHeader, useSourceRuns } from "./workbench-header";
import { WorkbenchTable, type WorkbenchTableHandle } from "./workbench-table";

/** The server's own sentence when it sent one (`{message}`), else the error text. */
export function errorText(error: unknown): string {
  const body = error instanceof ApiError ? (error.body as { message?: unknown } | null) : null;
  if (typeof body?.message === "string") return body.message;
  return error instanceof Error ? error.message : "Something went wrong.";
}

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
  if (!source) {
    return (
      <EmptyState
        icon={ChartScatter}
        title="Nothing to visualize"
        description="Open the workbench with Visualize on a protocol or a run."
      />
    );
  }
  return <Workbench source={source} level={level} view={view} />;
}

/** The last level switch: the view it leads to and what it takes along. */
type Switch = { to: string; carry: Carry; dismissed?: boolean };

function Workbench({
  source,
  level,
  view,
}: {
  source: DatasetSource;
  level: Level;
  view?: OpenedView;
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

  const ds = useMemo(
    () => (query.data ? resolveUserColumns(query.data, nameOf) : undefined),
    [query.data, nameOf],
  );
  // A row above Runs pools the source runs that count at its level; its curves come from those.
  const countedRunIds = useMemo(
    () => runs.filter((r) => countsAtLevel(level, r.status)).map((r) => r.id),
    [runs, level],
  );
  const openCurves = useCallback(
    (key: string, i: number) => ds && setCurves(curvesTarget(ds, key, i, countedRunIds)),
    [ds, countedRunIds],
  );

  // A switch refetches at the new level (the URL carries it); the plots and filters follow
  // when its data arrives, fitted to that level's columns. Not an undo step.
  const shown = viewKey(source, level);
  const carry = switched?.to === shown ? switched.carry : null;
  const switchLevel = (next: Level, take: Carry | null) => {
    setSwitched(take && { to: viewKey(source, next), carry: take });
    router.replace(visualizeHref(source, next, view?.view.id), { scroll: false });
  };
  const carried = useMemo(() => (ds && carry ? carryConfig(carry, ds) : null), [ds, carry]);
  const note =
    carried && carry && !switched?.dismissed
      ? switchNote(level, carried.dropped, carry.selected)
      : null;

  // A saved view opens on its own plots and filters, less what today's data lacks; the note
  // lists that by saved label, after whatever the server could not resolve (removed runs…).
  const resolved = useMemo(
    () => (ds && view ? resolveViewConfig(view.config, ds) : null),
    [ds, view],
  );
  const viewLines = [
    ...(view?.view.unresolved ?? []),
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
  }

  return (
    <div className="flex h-[calc(100dvh-4.5rem)] min-h-[560px] flex-col gap-2">
      {/* Always mounted, so screen readers announce the switch note when it appears. */}
      <output className="sr-only">{note}</output>
      {body || !ds ? (
        <>
          <SourceBar source={source} level={level} />
          <LevelSwitcher level={level} onChange={(next) => switchLevel(next, carry)} />
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
          saved={view !== undefined}
        >
          <WorkbenchHeader
            source={source}
            ds={ds}
            level={level}
            onLevelChange={switchLevel}
            exportMenu={<ExportMenu ds={ds} table={tableRef} />}
            addPlotMenu={<AddPlotMenu ds={ds} />}
          />
          {viewNote}
          {note && (
            <div className="flex items-start gap-2 rounded-md border bg-card px-3 py-2 text-sm">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              {/* Read out by the status line above; hidden here so it is not heard twice. */}
              <p aria-hidden="true" className="min-w-0 flex-1">
                {note}
              </p>
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6 shrink-0"
                aria-label="Dismiss note"
                onClick={() => setSwitched((s) => s && { ...s, dismissed: true })}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
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
              <div className="flex h-full flex-col">
                <SelectionStrip ds={ds} />
                <WorkbenchTable
                  ref={tableRef}
                  ds={ds}
                  actions={<SaveCollectionButton ds={ds} />}
                  onOpenCurves={openCurves}
                />
              </div>
            }
            rail={<FilterRail ds={ds} />}
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
      {pickerOpen && protocolId && (
        <RunPickerDialog
          protocolId={protocolId}
          initialRunIds={source.kind === "protocol" ? source.runIds : undefined}
          level={level}
          open
          onOpenChange={setPickerOpen}
        />
      )}
    </div>
  );
}

const viewKey = (source: DatasetSource, level: Level) => JSON.stringify([source, level]);

// The provider reads this once (its store is created on mount), so the ids made here stick.
const initialPanels = (ds: Dataset) => defaultPanels(ds).map((p) => makePanel(p.type, p.defaults));

export function LoadingSkeleton() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-full" />
      <div className="flex min-h-0 flex-1 gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <Skeleton className="flex-[3]" />
          <Skeleton className="flex-[2]" />
        </div>
        <Skeleton className="hidden w-72 xl:block" />
      </div>
    </div>
  );
}
