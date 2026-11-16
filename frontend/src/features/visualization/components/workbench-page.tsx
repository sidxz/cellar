"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { ApiError } from "@/shared/lib/api/custom-instance";
import { cn } from "@/shared/lib/utils";
import { AlertTriangle, ChartScatter, Database, Rows3 } from "lucide-react";
import { useMemo, useState } from "react";
import { useDataset } from "../hooks/use-dataset";
import { useRunRowCounts } from "../hooks/use-run-row-counts";
import { resolveUserColumns } from "../lib/dataset";
import { defaultPanels, numericValueColumn } from "../lib/default-panels";
import { MAX_ROWS } from "../lib/limits";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import { makePanel } from "../store/workbench-store";
import type { Dataset, DatasetSource, Level } from "../types";
import { type OnEditPanel, PanelFrame } from "./panels/panel-frame";
import { ScatterPanel } from "./panels/scatter-panel";
import { RunPickerDialog } from "./run-picker-dialog";
import { SelectionStrip } from "./selection-strip";
import { WorkbenchBody } from "./workbench-body";
import { SourceBar, WorkbenchHeader } from "./workbench-header";
import { WorkbenchTable } from "./workbench-table";

const LEVEL: Level = "wells";

/** The server's own sentence when it sent one (`{message}`), else the error text. */
function errorText(error: unknown): string {
  const body = error instanceof ApiError ? (error.body as { message?: unknown } | null) : null;
  if (typeof body?.message === "string") return body.message;
  return error instanceof Error ? error.message : "Something went wrong.";
}

/** The full-page workbench for a protocol (some or all runs) or one run. */
export function WorkbenchPage({ source }: { source: DatasetSource | null }) {
  if (!source) {
    return (
      <EmptyState
        icon={ChartScatter}
        title="Nothing to visualize"
        description="Open the workbench with Visualize on a protocol or a run."
      />
    );
  }
  return <Workbench source={source} />;
}

function Workbench({ source }: { source: DatasetSource }) {
  const query = useDataset(source, LEVEL);
  const nameOf = useMemberNames();
  const protocolId = source.kind === "protocol" ? source.protocolId : null;
  const { data: rowCounts } = useRunRowCounts(protocolId);
  const [pickerOpen, setPickerOpen] = useState(false);

  const ds = useMemo(
    () => (query.data ? resolveUserColumns(query.data, nameOf) : undefined),
    [query.data, nameOf],
  );

  // Known before the dataset arrives (the server refuses it with a bare 422), so the
  // chemist sees the actual count and goes straight back to the picker.
  const requested = useMemo(() => {
    if (source.kind !== "protocol" || !rowCounts) return null;
    const ids = source.runIds ?? Object.keys(rowCounts.counts);
    return ids.reduce((n, id) => n + (rowCounts.counts[id] ?? 0), 0);
  }, [source, rowCounts]);

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
  } else if (query.isError) {
    body = (
      <EmptyState
        icon={AlertTriangle}
        title="Couldn't load the data"
        description={errorText(query.error)}
        action={{ label: "Retry", onClick: () => void query.refetch() }}
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
      {body || !ds ? (
        <>
          <SourceBar source={source} />
          {body}
        </>
      ) : (
        <WorkbenchProvider key={ds.revision} initialPanels={initialPanels(ds)}>
          <WorkbenchHeader source={source} ds={ds} />
          <WorkbenchBody
            plots={<PlotsSlot ds={ds} onEdit={noEdit} />}
            table={
              <div className="flex h-full flex-col">
                <SelectionStrip ds={ds} />
                <WorkbenchTable ds={ds} />
              </div>
            }
            rail={<SlotNote>No filters yet.</SlotNote>}
          />
        </WorkbenchProvider>
      )}
      {pickerOpen && protocolId && (
        <RunPickerDialog
          protocolId={protocolId}
          initialRunIds={source.kind === "protocol" ? source.runIds : undefined}
          open
          onOpenChange={setPickerOpen}
        />
      )}
    </div>
  );
}

// The plot editor arrives with the settings drawer, which passes the real handler here.
const noEdit: OnEditPanel = () => {};

// The provider reads this once (its store is created on mount), so the ids made here stick.
const initialPanels = (ds: Dataset) => defaultPanels(ds).map((p) => makePanel(p.type, p.defaults));

function LoadingSkeleton() {
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

function SlotNote({ children }: { children: React.ReactNode }) {
  return <p className="p-3 text-sm text-muted-foreground">{children}</p>;
}

/** Plots area: the no-numeric notice plus the configured panels (only the maximized one
 * while one is). A stand-in layout until the panel grid replaces it. */
function PlotsSlot({ ds, onEdit }: { ds: Dataset; onEdit: OnEditPanel }) {
  const panels = useWorkbench((s) => s.panels);
  const maximized = useWorkbench((s) => s.maximized);
  const shown = maximized ? panels.filter((p) => p.id === maximized) : panels;
  return (
    <div className="flex h-full flex-col gap-2 p-2">
      {!numericValueColumn(ds) && (
        <p className="rounded-md border border-dashed p-2 text-sm text-muted-foreground">
          No numeric fields to plot — showing well counts by category. The table still lists every
          value.
        </p>
      )}
      <div
        className={cn(
          "grid min-h-0 flex-1 auto-rows-fr gap-2",
          shown.length > 1 && "lg:grid-cols-2",
        )}
      >
        {shown.map((p) => (
          <PanelFrame key={p.id} panel={p} ds={ds} onEdit={onEdit}>
            {p.type === "scatter" ? (
              <ScatterPanel panel={p} ds={ds} />
            ) : (
              <SlotNote>This plot type is coming in Task 11.</SlotNote>
            )}
          </PanelFrame>
        ))}
      </div>
    </div>
  );
}
