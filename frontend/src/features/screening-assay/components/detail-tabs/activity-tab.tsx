"use client";

import { useMemo, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { Filter, FlaskConical, RotateCcw, Settings2 } from "lucide-react";
import type {
  ColDef,
  ICellRendererParams,
  SelectionChangedEvent,
} from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { EmptyState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useProtocolActivity } from "../../hooks/use-protocol-activity";
import { useCompoundCurves } from "../../hooks/use-compound-curves";
import { DoseResponseChart } from "../dose-response-chart";
import { DoseResponseSparkline } from "../dose-response-sparkline";
import { HitCriteriaDialog } from "../hit-criteria-dialog";
import {
  CURVE_CLASS_LABELS,
  type CompoundActivity,
  type CurveClass,
  type HitCriterion,
  type Protocol,
  type ReadoutDefInfo,
} from "../../types";

// ---------------------------------------------------------------------------
// Dynamic Plotly import (no SSR)
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Plot = dynamic<any>(
  () => import("react-plotly.js").then((mod) => mod.default as any),
  {
    ssr: false,
    loading: () => <Skeleton className="h-[350px] w-full" />,
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
) as React.ComponentType<any>;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const OPERATOR_LABELS: Record<string, string> = {
  gt: ">",
  lt: "<",
  gte: ">=",
  lte: "<=",
  in: "in",
};

// ---------------------------------------------------------------------------
// Curve class badge
// ---------------------------------------------------------------------------

function curveClassBadge(cc: CurveClass | null) {
  if (cc == null) {
    return (
      <Badge variant="outline" className="text-muted-foreground">
        --
      </Badge>
    );
  }
  const styles: Record<CurveClass, string> = {
    full: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
    partial: "border-yellow-500/40 bg-yellow-500/10 text-yellow-400",
    bell_shaped: "border-blue-500/40 bg-blue-500/10 text-blue-400",
    inactive: "border-muted text-muted-foreground",
  };
  return <Badge className={styles[cc]}>{CURVE_CLASS_LABELS[cc]}</Badge>;
}

// ---------------------------------------------------------------------------
// Client-side filter (multi-readout)
// ---------------------------------------------------------------------------

function applyFilters(
  items: CompoundActivity[],
  criteria: HitCriterion[]
): CompoundActivity[] {
  if (criteria.length === 0) return items;
  return items.filter((item) =>
    criteria.every((rule) => {
      if (rule.readout_name === "Curve Class") {
        if (rule.operator === "in" && Array.isArray(rule.value)) {
          return Object.values(item.readouts).some(
            (rv) =>
              rv.curve_class != null &&
              (rule.value as string[]).includes(rv.curve_class)
          );
        }
        return true;
      }
      const readout = item.readouts[rule.readout_name];
      if (!readout || readout.best == null) return false;
      const threshold = typeof rule.value === "number" ? rule.value : 0;
      switch (rule.operator) {
        case "gt":
          return readout.best > threshold;
        case "lt":
          return readout.best < threshold;
        case "gte":
          return readout.best >= threshold;
        case "lte":
          return readout.best <= threshold;
        default:
          return true;
      }
    })
  );
}

// ---------------------------------------------------------------------------
// Criterion badge display
// ---------------------------------------------------------------------------

function criterionLabel(rule: HitCriterion): string {
  const op = OPERATOR_LABELS[rule.operator] ?? rule.operator;
  const val = Array.isArray(rule.value) ? rule.value.join(", ") : rule.value;
  return `${rule.readout_name} ${op} ${val}`;
}

// ---------------------------------------------------------------------------
// Dynamic column generation
// ---------------------------------------------------------------------------

function buildColumnDefs(
  readoutDefs: ReadoutDefInfo[]
): ColDef<CompoundActivity>[] {
  const cols: ColDef<CompoundActivity>[] = [];

  // Fixed left: Compound
  cols.push({
    headerName: "Compound",
    field: "registration_number",
    pinned: "left",
    flex: 1,
    minWidth: 160,
    headerCheckboxSelection: true,
    checkboxSelection: true,
    cellRenderer: (params: ICellRendererParams<CompoundActivity>) => {
      if (!params.data) return null;
      return (
        <div className="leading-tight">
          <span className="font-medium">
            {params.data.registration_number}
          </span>
          {params.data.molecule_name && (
            <span className="ml-2 text-xs text-muted-foreground">
              {params.data.molecule_name}
            </span>
          )}
        </div>
      );
    },
  });

  // Per readout definition
  let isFirstReadout = true;
  for (const rd of readoutDefs) {
    const isDR = rd.data_type === "dose_response";
    const unitSuffix = rd.unit ? ` (${rd.unit})` : "";

    // Best column
    cols.push({
      headerName: `${rd.name} Best${unitSuffix}`,
      colId: `${rd.name}_best`,
      width: 120,
      valueGetter: (p) => p.data?.readouts?.[rd.name]?.best ?? null,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toPrecision(4) : "--",
      // Default sort on first readout
      ...(isFirstReadout
        ? { sort: isDR ? ("asc" as const) : ("desc" as const) }
        : {}),
    });

    // Mean column
    cols.push({
      headerName: `${rd.name} Mean${unitSuffix}`,
      colId: `${rd.name}_mean`,
      width: 120,
      valueGetter: (p) => p.data?.readouts?.[rd.name]?.mean ?? null,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toPrecision(4) : "--",
    });

    // DR-specific extra columns
    if (isDR) {
      cols.push({
        headerName: "Class",
        colId: `${rd.name}_class`,
        width: 90,
        valueGetter: (p) =>
          p.data?.readouts?.[rd.name]?.curve_class ?? null,
        cellRenderer: (params: ICellRendererParams<CompoundActivity>) =>
          curveClassBadge(params.value ?? null),
      });

      cols.push({
        headerName: "Curve",
        colId: `${rd.name}_curve`,
        width: 130,
        cellRenderer: (params: ICellRendererParams<CompoundActivity>) => {
          if (!params.data) return null;
          const rv = params.data.readouts?.[rd.name];
          const cp = rv?.curve_params;
          const cc = rv?.curve_class;
          if (!cp) return <span className="text-muted-foreground">--</span>;
          return <DoseResponseSparkline params={cp} curveClass={cc} />;
        },
      });
    }

    isFirstReadout = false;
  }

  // Fixed right: Runs + Last Tested
  cols.push({
    headerName: "Runs",
    field: "run_count",
    width: 70,
  });

  cols.push({
    headerName: "Last Tested",
    field: "last_tested",
    width: 110,
    cellClass: "font-mono",
    valueFormatter: (p) => {
      if (!p.value) return "--";
      return new Date(p.value as string).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    },
  });

  return cols;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ActivityTabProps {
  protocol: Protocol;
  protocolId: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ActivityTab({ protocol, protocolId }: ActivityTabProps) {
  const { data: activity, isLoading } = useProtocolActivity(protocolId);

  // Hit criteria state
  const savedCriteria: HitCriterion[] =
    protocol.recommended_hit_criteria ?? [];
  const [activeCriteria, setActiveCriteria] =
    useState<HitCriterion[]>(savedCriteria);
  const isModified =
    JSON.stringify(activeCriteria) !== JSON.stringify(savedCriteria);

  // Dialog state
  const [criteriaDialogOpen, setCriteriaDialogOpen] = useState(false);

  // Selection state
  const [selectedRows, setSelectedRows] = useState<CompoundActivity[]>([]);

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<CompoundActivity>) => {
      setSelectedRows(event.api.getSelectedRows());
    },
    []
  );

  // Sync savedCriteria when protocol updates (e.g. after dialog save)
  const prevSavedRef = JSON.stringify(protocol.recommended_hit_criteria ?? []);
  const [lastSynced, setLastSynced] = useState(prevSavedRef);
  if (prevSavedRef !== lastSynced) {
    setActiveCriteria(protocol.recommended_hit_criteria ?? []);
    setLastSynced(prevSavedRef);
  }

  // Derived data
  const readoutDefs = activity?.readout_definitions ?? [];

  const filteredItems = useMemo(
    () => applyFilters(activity?.items ?? [], activeCriteria),
    [activity?.items, activeCriteria]
  );

  // AG Grid columns (dynamic from readout definitions)
  const columnDefs = useMemo<ColDef<CompoundActivity>[]>(
    () => buildColumnDefs(readoutDefs),
    [readoutDefs]
  );

  // ---------------------------------------------------------------------------
  // Compound detail panel
  // ---------------------------------------------------------------------------

  const singleSelectedMoleculeId =
    selectedRows.length === 1 ? selectedRows[0].molecule_id : null;

  const { data: compoundCurves, isLoading: curvesLoading } =
    useCompoundCurves(protocolId, singleSelectedMoleculeId);

  // Comparison bar chart data (2-5 selected, first readout)
  const chartData = useMemo(() => {
    if (selectedRows.length < 2 || selectedRows.length > 5) return null;
    const firstReadout = readoutDefs[0];
    if (!firstReadout) return null;
    return [
      {
        type: "bar" as const,
        x: selectedRows.map((r) => r.registration_number),
        y: selectedRows.map(
          (r) => r.readouts?.[firstReadout.name]?.best ?? 0
        ),
        marker: { color: "#3b82f6" },
        hoverinfo: "x+y",
      },
    ];
  }, [selectedRows, readoutDefs]);

  const chartLayout = useMemo(() => {
    const firstReadout = readoutDefs[0];
    const unitSuffix = firstReadout?.unit ? ` (${firstReadout.unit})` : "";
    return {
      height: 350,
      autosize: true,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: "#a1a1aa" },
      xaxis: {
        title: { text: "Compound" },
        gridcolor: "#27272a",
        tickangle: -45,
      },
      yaxis: {
        title: { text: `Best ${firstReadout?.name ?? "Value"}${unitSuffix}` },
        gridcolor: "#27272a",
      },
      margin: { l: 60, r: 20, t: 20, b: 80 },
      bargap: 0.3,
    };
  }, [readoutDefs]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (!activity || activity.items.length === 0) {
    return (
      <EmptyState
        icon={FlaskConical}
        title="No activity data"
        description="Complete some runs with readout data to see compound activity here."
      />
    );
  }

  const hasCriteria =
    savedCriteria.length > 0 || activeCriteria.length > 0;

  return (
    <div className="space-y-4">
      {/* Hit Criteria CTA or Filter Bar */}
      {!hasCriteria ? (
        <Card className="border-2 border-dashed">
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="font-medium">No hit criteria defined</p>
              <p className="text-sm text-muted-foreground">
                Define recommended criteria so your team knows which compounds
                qualify as hits.
              </p>
            </div>
            <Button onClick={() => setCriteriaDialogOpen(true)}>
              <Settings2 className="mr-2 h-4 w-4" /> Set Hit Criteria
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-2 p-3">
            <Filter className="h-4 w-4 text-muted-foreground" />

            {activeCriteria.length > 0 ? (
              activeCriteria.map((rule, i) => (
                <Badge key={i} variant="secondary">
                  {criterionLabel(rule)}
                </Badge>
              ))
            ) : (
              <span className="text-sm text-muted-foreground">
                No filter criteria
              </span>
            )}

            {isModified && (
              <Badge
                variant="outline"
                className="border-yellow-500/40 text-yellow-400"
              >
                Modified
              </Badge>
            )}

            <div className="ml-auto flex items-center gap-2">
              {isModified && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveCriteria(savedCriteria)}
                >
                  <RotateCcw className="mr-1 h-3.5 w-3.5" />
                  Reset
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCriteriaDialogOpen(true)}
              >
                <Settings2 className="mr-1 h-3.5 w-3.5" />
                Edit Criteria
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filtered count indicator */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {filteredItems.length} of {activity.items.length} compound
          {activity.items.length !== 1 ? "s" : ""}
          {activeCriteria.length > 0 ? " match criteria" : ""}
        </span>
        {selectedRows.length > 0 && (
          <span>{selectedRows.length} selected</span>
        )}
      </div>

      {/* AG Grid with dynamic columns */}
      <DataGrid<CompoundActivity>
        rowData={filteredItems}
        columnDefs={columnDefs}
        height="500px"
        rowSelection="multiple"
        rowHeight={70}
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.molecule_id}
        exportFilename={`${protocol.name}-activity`}
        emptyState={
          <EmptyState
            icon={Filter}
            title="No compounds match"
            description="Adjust or remove hit criteria to see more compounds."
          />
        }
      />

      {/* Compound detail panel */}
      {selectedRows.length === 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {selectedRows[0].registration_number}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {curvesLoading ? (
              <Skeleton className="h-[350px] w-full" />
            ) : compoundCurves && compoundCurves.length > 0 ? (
              <DoseResponseChart
                curves={compoundCurves}
                isInteractive={false}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                No dose-response curves available for this compound.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Comparison chart — 2-5 selected */}
      {chartData && selectedRows.length >= 2 && selectedRows.length <= 5 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Comparison ({selectedRows.length} compound
              {selectedRows.length !== 1 ? "s" : ""})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={chartData}
              layout={chartLayout}
              config={{ displayModeBar: false, responsive: true }}
              useResizeHandler
              style={{ width: "100%", height: "350px" }}
            />
          </CardContent>
        </Card>
      )}

      {/* >5 selected — count text */}
      {selectedRows.length > 5 && (
        <p className="text-sm text-muted-foreground">
          {selectedRows.length} compounds selected. Select 5 or fewer to see a
          comparison chart, or 1 to see dose-response curves.
        </p>
      )}

      {/* Hit criteria dialog */}
      <HitCriteriaDialog
        protocolId={protocolId}
        readoutDefinitions={protocol.readout_definitions}
        currentCriteria={protocol.recommended_hit_criteria}
        open={criteriaDialogOpen}
        onOpenChange={setCriteriaDialogOpen}
      />
    </div>
  );
}
