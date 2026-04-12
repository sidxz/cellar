"use client";

import { useMemo, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { Filter, RotateCcw, Settings2, FlaskConical } from "lucide-react";
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
import { HitCriteriaDialog } from "../hit-criteria-dialog";
import {
  CURVE_CLASS_LABELS,
  type ActivitySummaryItem,
  type CurveClass,
  type HitCriterion,
  type Protocol,
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
// Client-side filter
// ---------------------------------------------------------------------------

function applyFilters(
  items: ActivitySummaryItem[],
  criteria: HitCriterion[]
): ActivitySummaryItem[] {
  if (criteria.length === 0) return items;
  return items.filter((item) =>
    criteria.every((rule) => {
      if (rule.readout_name === "Curve Class") {
        if (rule.operator === "in" && Array.isArray(rule.value)) {
          return (
            item.curve_class != null && rule.value.includes(item.curve_class)
          );
        }
        return true;
      }
      const val = item.best_value;
      if (val == null) return false;
      const threshold = typeof rule.value === "number" ? rule.value : 0;
      switch (rule.operator) {
        case "gt":
          return val > threshold;
        case "lt":
          return val < threshold;
        case "gte":
          return val >= threshold;
        case "lte":
          return val <= threshold;
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
  const [selectedRows, setSelectedRows] = useState<ActivitySummaryItem[]>([]);

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<ActivitySummaryItem>) => {
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
  const readoutName = activity?.readout_name ?? "Value";
  const readoutUnit = activity?.readout_unit;
  const unitSuffix = readoutUnit ? ` (${readoutUnit})` : "";

  const filteredItems = useMemo(
    () => applyFilters(activity?.items ?? [], activeCriteria),
    [activity?.items, activeCriteria]
  );

  // ---------------------------------------------------------------------------
  // AG Grid columns
  // ---------------------------------------------------------------------------

  const columnDefs = useMemo<ColDef<ActivitySummaryItem>[]>(
    () => [
      {
        headerName: "Compound",
        field: "molecule_registration_number",
        flex: 1,
        minWidth: 160,
        headerCheckboxSelection: true,
        checkboxSelection: true,
        cellRenderer: (params: ICellRendererParams<ActivitySummaryItem>) => {
          if (!params.data) return null;
          return (
            <div className="leading-tight">
              <span className="font-medium">
                {params.data.molecule_registration_number}
              </span>
              {params.data.molecule_name && (
                <span className="ml-2 text-xs text-muted-foreground">
                  {params.data.molecule_name}
                </span>
              )}
            </div>
          );
        },
      },
      {
        headerName: `Best${unitSuffix}`,
        field: "best_value",
        width: 110,
        sort: "asc",
        valueFormatter: (p) =>
          p.value != null ? Number(p.value).toPrecision(4) : "--",
      },
      {
        headerName: `Mean${unitSuffix}`,
        field: "mean_value",
        width: 110,
        valueFormatter: (p) =>
          p.value != null ? Number(p.value).toPrecision(4) : "--",
      },
      {
        headerName: "Runs",
        field: "run_count",
        width: 70,
      },
      {
        headerName: "Range",
        colId: "range",
        width: 120,
        valueGetter: (p) => {
          if (!p.data) return null;
          const { min_value, max_value } = p.data;
          if (min_value == null || max_value == null) return null;
          if (min_value === max_value)
            return Number(min_value).toPrecision(3);
          return `${Number(min_value).toPrecision(3)}\u2013${Number(max_value).toPrecision(3)}`;
        },
      },
      {
        headerName: "Curve Class",
        field: "curve_class",
        width: 110,
        cellRenderer: (params: ICellRendererParams<ActivitySummaryItem>) =>
          curveClassBadge(params.value ?? null),
      },
      {
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
      },
    ],
    [unitSuffix]
  );

  // ---------------------------------------------------------------------------
  // Plotly comparison chart data
  // ---------------------------------------------------------------------------

  const chartData = useMemo(() => {
    if (selectedRows.length === 0) return null;
    return [
      {
        type: "bar" as const,
        x: selectedRows.map((r) => r.molecule_registration_number),
        y: selectedRows.map((r) => r.best_value ?? 0),
        marker: { color: "#3b82f6" },
        hoverinfo: "x+y",
      },
    ];
  }, [selectedRows]);

  const chartLayout = useMemo(
    () => ({
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
        title: { text: `Best ${readoutName}${unitSuffix}` },
        gridcolor: "#27272a",
      },
      margin: { l: 60, r: 20, t: 20, b: 80 },
      bargap: 0.3,
    }),
    [readoutName, unitSuffix]
  );

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

  return (
    <div className="space-y-4">
      {/* Filter bar */}
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

      {/* AG Grid */}
      <DataGrid<ActivitySummaryItem>
        rowData={filteredItems}
        columnDefs={columnDefs}
        height="500px"
        rowSelection="multiple"
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

      {/* Comparison chart — only when rows selected */}
      {chartData && selectedRows.length > 0 && (
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
