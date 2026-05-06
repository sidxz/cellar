"use client";

import { useMemo, useState, useCallback } from "react";
import { Plot } from "@/shared/lib/plotly";
import { GROUP_PALETTE, CHART_COLORS, CHART_AXIS } from "@/shared/lib/chart-colors";
import { Eye, Filter, FlaskConical, FolderPlus, RotateCcw, Settings2, Star } from "lucide-react";
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
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { EmptyState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import type { ExcelEnhancer } from "@/shared/components/data-grid/export-toolbar";
import { renderCurveToBase64 } from "@/shared/lib/export/curve-image";
import { fetchStructureImages } from "@/shared/lib/export/structure-image";
import { useProtocolActivity } from "../../hooks/use-protocol-activity";
import { useCompoundFlags, useCreateFlag, useDeleteFlag } from "../../hooks/use-compound-flags";
import { COMPACT_DR_CHART } from "../../lib/dose-response-display";
import { groupBy } from "@/shared/lib/group-by";
import type { CompoundFlag as CompoundFlagType } from "../../types";
import { useCompoundCurves, useMultiCompoundCurves } from "../../hooks/use-compound-curves";
import { DoseResponseChart } from "../dose-response-chart";
import { DoseResponseSparkline } from "../dose-response-sparkline";
import { CurveNavigator } from "../curve-navigator";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { HitCriteriaDialog } from "../hit-criteria-dialog";
import { CollectionPickerDialog } from "../collection-picker-dialog";
import { ComparisonTable, buildComparisonRows } from "../comparison-table";
import {
  CURVE_CLASS_LABELS,
  type CompoundActivity,
  type CurveClass,
  type HitCriterion,
  type Protocol,
  type ReadoutDefInfo,
} from "../../types";

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
    full: "border-success/40 bg-success/10 text-success",
    partial: "border-yellow-500/40 bg-yellow-500/10 text-yellow-400",
    bell_shaped: "border-primary/40 bg-primary/10 text-primary",
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
  readoutDefs: ReadoutDefInfo[],
  flagsByMolecule: Map<string, CompoundFlagType>,
  onToggleFlag: (moleculeId: string, existingFlagId: string | null) => void,
): ColDef<CompoundActivity>[] {
  const cols: ColDef<CompoundActivity>[] = [];

  // Fixed left: Compound — also hosts the multi-select checkbox AND the
  // star/flag toggle. Three left-anchored columns collapsed into one to
  // reclaim ~90px of horizontal space.
  cols.push({
    headerName: "Compound",
    field: "registration_number",
    pinned: "left",
    flex: 1,
    minWidth: 230,
    checkboxSelection: true,
    headerCheckboxSelection: true,
    cellRenderer: (params: ICellRendererParams<CompoundActivity>) => {
      if (!params.data) return null;
      const flag = flagsByMolecule.get(params.data.molecule_id);
      return (
        <div className="flex items-start gap-2 leading-tight">
          <button
            type="button"
            className="mt-0.5 flex-shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              onToggleFlag(params.data!.molecule_id, flag?.id ?? null);
            }}
            aria-label={flag ? "Unflag compound" : "Flag compound"}
          >
            <Star
              className={`h-4 w-4 transition-colors ${
                flag
                  ? "fill-yellow-400 text-yellow-400"
                  : "text-muted-foreground/30 hover:text-yellow-400/50"
              }`}
            />
          </button>
          <div className="min-w-0">
            <span className="font-medium">
              {params.data.registration_number}
            </span>
            {params.data.molecule_name && (
              <span className="ml-2 text-xs text-muted-foreground">
                {params.data.molecule_name}
              </span>
            )}
            {params.data.batch_number && (
              <div className="text-[10px] text-muted-foreground">
                Batch: {params.data.batch_number}
              </div>
            )}
          </div>
        </div>
      );
    },
  });

  // Structure column
  cols.push({
    headerName: "Structure",
    colId: "structure",
    width: 130,
    sortable: false,
    cellRenderer: (params: ICellRendererParams<CompoundActivity>) => {
      if (!params.data?.smiles) return <span className="text-muted-foreground">--</span>;
      return (
        <div className="flex h-full items-center justify-center py-1">
          <StructureThumbnail smiles={params.data.smiles} size={104} />
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
      cellRenderer: !isDR
        ? (params: ICellRendererParams<CompoundActivity>) => {
            if (params.value == null) return "--";
            const rv = params.data?.readouts?.[rd.name];
            return (
              <div className="leading-tight">
                <span>{Number(params.value).toPrecision(4)}</span>
                {rv?.n != null && rv.n > 1 && (
                  <div className="text-[10px] text-muted-foreground">
                    n={rv.n}{rv.sd != null ? `, SD=${rv.sd.toPrecision(2)}` : ""}
                  </div>
                )}
              </div>
            );
          }
        : undefined,
      valueFormatter: isDR
        ? (p) => (p.value != null ? Number(p.value).toPrecision(4) : "--")
        : undefined,
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
        width: 150,
        cellRenderer: (params: ICellRendererParams<CompoundActivity>) => {
          if (!params.data) return null;
          const rv = params.data.readouts?.[rd.name];
          const cp = rv?.curve_params;
          const cc = rv?.curve_class;
          const dp = rv?.data_points;
          if (!cp) return <span className="text-muted-foreground">--</span>;
          return <DoseResponseSparkline params={cp} dataPoints={dp} curveClass={cc} />;
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

  // Compound flags
  const { data: flags } = useCompoundFlags(protocolId);
  const createFlag = useCreateFlag(protocolId);
  const deleteFlag = useDeleteFlag(protocolId);
  const [showFlaggedOnly, setShowFlaggedOnly] = useState(false);

  const flagsByMolecule = useMemo(() => {
    const map = new Map<string, CompoundFlagType>();
    for (const f of flags ?? []) {
      if (f.flag_type === "star") map.set(f.molecule_id, f);
    }
    return map;
  }, [flags]);

  // Hit criteria state
  const savedCriteria: HitCriterion[] =
    protocol.recommended_hit_criteria ?? [];
  const [activeCriteria, setActiveCriteria] =
    useState<HitCriterion[]>(savedCriteria);
  const isModified =
    JSON.stringify(activeCriteria) !== JSON.stringify(savedCriteria);

  // Dialog state
  const [criteriaDialogOpen, setCriteriaDialogOpen] = useState(false);
  const [collectionDialogOpen, setCollectionDialogOpen] = useState(false);

  // Selection state (checkbox-driven, for multi-compound actions)
  const [selectedRows, setSelectedRows] = useState<CompoundActivity[]>([]);

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<CompoundActivity>) => {
      setSelectedRows(event.api.getSelectedRows());
    },
    []
  );

  // Viewing state (row-click-driven, for single-compound detail sheet)
  const [viewingId, setViewingId] = useState<string | null>(null);

  // Sync savedCriteria when protocol updates (e.g. after dialog save)
  const prevSavedRef = JSON.stringify(protocol.recommended_hit_criteria ?? []);
  const [lastSynced, setLastSynced] = useState(prevSavedRef);
  if (prevSavedRef !== lastSynced) {
    setActiveCriteria(protocol.recommended_hit_criteria ?? []);
    setLastSynced(prevSavedRef);
  }

  // Derived data
  const readoutDefs = activity?.readout_definitions ?? [];

  const filteredItems = useMemo(() => {
    let items = applyFilters(activity?.items ?? [], activeCriteria);
    if (showFlaggedOnly) {
      items = items.filter((item) => flagsByMolecule.has(item.molecule_id));
    }
    return items;
  }, [activity?.items, activeCriteria, showFlaggedOnly, flagsByMolecule]);

  // Curve navigation (prev/next of the currently viewed compound)
  const viewing = useMemo(
    () => filteredItems.find((r) => r.molecule_id === viewingId) ?? null,
    [filteredItems, viewingId]
  );
  const selectedIndex = viewing
    ? filteredItems.findIndex((r) => r.molecule_id === viewing.molecule_id)
    : -1;

  const navigateTo = useCallback((index: number) => {
    const target = filteredItems[index];
    if (target) setViewingId(target.molecule_id);
  }, [filteredItems]);

  const handlePrev = useCallback(() => {
    const newIdx = selectedIndex <= 0 ? filteredItems.length - 1 : selectedIndex - 1;
    navigateTo(newIdx);
  }, [selectedIndex, filteredItems.length, navigateTo]);

  const handleNext = useCallback(() => {
    const newIdx = selectedIndex >= filteredItems.length - 1 ? 0 : selectedIndex + 1;
    navigateTo(newIdx);
  }, [selectedIndex, filteredItems.length, navigateTo]);

  // AG Grid columns (dynamic from readout definitions). The Compound column
  // hosts the checkbox + star toggle; no standalone star column.
  const handleToggleFlag = useCallback(
    (moleculeId: string, existingFlagId: string | null) => {
      if (existingFlagId) {
        deleteFlag.mutate(existingFlagId);
      } else {
        createFlag.mutate({ molecule_id: moleculeId });
      }
    },
    [createFlag, deleteFlag],
  );

  const columnDefs = useMemo<ColDef<CompoundActivity>[]>(
    () => buildColumnDefs(readoutDefs, flagsByMolecule, handleToggleFlag),
    [readoutDefs, flagsByMolecule, handleToggleFlag],
  );

  // ---------------------------------------------------------------------------
  // Compound detail panel
  // ---------------------------------------------------------------------------

  const { data: compoundCurves, isLoading: curvesLoading } =
    useCompoundCurves(protocolId, viewing?.molecule_id ?? null);

  // Multi-compound curve overlay (2-5 selected)
  const multiMoleculeIds = useMemo(
    () =>
      selectedRows.length >= 2 && selectedRows.length <= 5
        ? selectedRows.map((r) => r.molecule_id)
        : [],
    [selectedRows]
  );

  const { data: multiCurves, isLoading: multiCurvesLoading } =
    useMultiCompoundCurves(protocolId, multiMoleculeIds);

  const hasDRCurves = multiCurves && multiCurves.length > 0;

  // Build Plotly curve overlay traces
  const overlayTraces = useMemo(() => {
    if (!multiCurves || multiCurves.length === 0) return null;
    const TRACE_COLORS = GROUP_PALETTE.slice(0, 5);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const traces: any[] = [];

    const byMolecule = groupBy(multiCurves, (curve) => curve.molecule_id);

    let colorIdx = 0;
    for (const [molId, curves] of byMolecule) {
      const color = TRACE_COLORS[colorIdx % TRACE_COLORS.length];
      const row = selectedRows.find((r) => r.molecule_id === molId);
      const label = row?.registration_number ?? molId.slice(0, 8);
      const bestCurve = curves[0];

      const allX = curves.flatMap((c) =>
        (c.raw_data ?? [])
          .map(
            (pt: Record<string, unknown>) =>
              (pt.concentration ?? pt.x) as number
          )
          .filter((v): v is number => typeof v === "number")
      );
      const xMin = Math.max(
        Math.min(...allX, bestCurve.fitted_value) * 0.1,
        1e-12
      );
      const xMax = Math.max(...allX, bestCurve.fitted_value) * 10;

      // Data points scatter
      const rawPts = bestCurve.raw_data ?? [];
      const ptX = rawPts
        .map(
          (p: Record<string, unknown>) =>
            (p.concentration ?? p.x) as number
        )
        .filter((v): v is number => typeof v === "number");
      const ptY = rawPts
        .map(
          (p: Record<string, unknown>) =>
            (p.response ?? p.y) as number
        )
        .filter((v): v is number => typeof v === "number");

      if (ptX.length > 0) {
        traces.push({
          type: "scatter",
          mode: "markers",
          name: label,
          legendgroup: label,
          x: ptX,
          y: ptY,
          marker: { color, size: 6 },
          showlegend: true,
          hovertemplate: `${label}<br>x: %{x:.4g}<br>y: %{y:.4g}<extra></extra>`,
        });
      }

      // Fitted sigmoid
      const logMin = Math.log10(xMin);
      const logMax = Math.log10(xMax);
      const lineX: number[] = [];
      const lineY: number[] = [];
      for (let i = 0; i <= COMPACT_DR_CHART.POINTS; i++) {
        const logX = logMin + (logMax - logMin) * (i / COMPACT_DR_CHART.POINTS);
        const x = Math.pow(10, logX);
        const y =
          bestCurve.bottom +
          (bestCurve.top - bestCurve.bottom) /
            (1 +
              Math.pow(x / bestCurve.fitted_value, bestCurve.hill_slope));
        lineX.push(x);
        lineY.push(y);
      }
      traces.push({
        type: "scatter",
        mode: "lines",
        name: `${label} fit`,
        legendgroup: label,
        x: lineX,
        y: lineY,
        line: { color, width: 2 },
        showlegend: false,
        hoverinfo: "skip",
      });

      colorIdx++;
    }
    return traces;
  }, [multiCurves, selectedRows]);

  // Fallback bar chart for single-point-only selection
  const barChartData = useMemo(() => {
    if (
      hasDRCurves ||
      selectedRows.length < 2 ||
      selectedRows.length > 5
    )
      return null;
    const firstReadout = readoutDefs[0];
    if (!firstReadout) return null;
    return [
      {
        type: "bar" as const,
        x: selectedRows.map((r) => r.registration_number),
        y: selectedRows.map(
          (r) => r.readouts?.[firstReadout.name]?.best ?? 0
        ),
        marker: { color: CHART_COLORS.primary },
        hoverinfo: "x+y",
      },
    ];
  }, [selectedRows, readoutDefs, hasDRCurves]);

  const comparisonLayout = useMemo(() => {
    const firstReadout = readoutDefs[0];
    const unitSuffix = firstReadout?.unit ? ` (${firstReadout.unit})` : "";
    const isDR = firstReadout?.data_type === "dose_response";
    return {
      height: 350,
      autosize: true,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: CHART_AXIS.label },
      xaxis: {
        title: { text: isDR ? "Concentration" : "Compound" },
        type: isDR ? ("log" as const) : undefined,
        gridcolor: CHART_AXIS.grid,
        ...(isDR ? {} : { tickangle: -45 }),
      },
      yaxis: {
        title: {
          text: isDR
            ? "Response (%)"
            : `Best ${firstReadout?.name ?? "Value"}${unitSuffix}`,
        },
        gridcolor: CHART_AXIS.grid,
      },
      legend: {
        orientation: "h" as const,
        y: -0.25,
        font: { color: CHART_AXIS.label },
      },
      margin: { l: 60, r: 20, t: 20, b: 80 },
      bargap: 0.3,
    };
  }, [readoutDefs]);

  // ---------------------------------------------------------------------------
  // Excel enhancer — sparkline images + raw data sheet
  // ---------------------------------------------------------------------------
  const excelEnhancer: ExcelEnhancer = useCallback(
    async (workbook, worksheet, rows: CompoundActivity[]) => {
      // Helper: find column index (0-based) by header text
      const findCol = (name: string) => {
        const row1 = worksheet.getRow(1);
        for (let c = 1; c <= worksheet.columnCount; c++) {
          if (row1.getCell(c).value === name) return c - 1;
        }
        return -1;
      };

      // Batch-fetch structure images from backend
      const allSmiles = rows.map((r) => r.smiles).filter(Boolean) as string[];
      const structImages = await fetchStructureImages(allSmiles, 150, 100);

      // Fill existing "Structure" column with images (grid exported it empty)
      const structColIdx = findCol("Structure");
      if (structColIdx >= 0) {
        worksheet.getColumn(structColIdx + 1).width = 22;
        for (let r = 0; r < rows.length; r++) {
          const smiles = rows[r].smiles;
          if (smiles && structImages[smiles]) {
            const imgId = workbook.addImage({ base64: structImages[smiles], extension: "png" });
            worksheet.addImage(imgId, {
              tl: { col: structColIdx, row: r + 1 },
              ext: { width: 150, height: 80 },
            });
          }
        }
      }

      // Fill existing "Curve" column with sparkline images
      const curveColIdx = findCol("Curve");
      if (curveColIdx >= 0) {
        worksheet.getColumn(curveColIdx + 1).width = 30;
        for (let r = 0; r < rows.length; r++) {
          const drReadout = Object.values(rows[r].readouts).find((rv) => rv.curve_params);
          if (!drReadout?.curve_params) continue;
          const base64 = renderCurveToBase64(drReadout.curve_params, drReadout.data_points);
          if (!base64) continue;
          const imageId = workbook.addImage({ base64, extension: "png" });
          worksheet.addImage(imageId, {
            tl: { col: curveColIdx, row: r + 1 },
            ext: { width: 200, height: 60 },
          });
        }
      }

      // Set consistent row heights for images
      for (let r = 2; r <= rows.length + 1; r++) {
        worksheet.getRow(r).height = 65;
      }

      // Append SMILES and Synonyms as new columns at the end
      const lastCol = worksheet.columnCount;
      const smilesCol = lastCol + 1;
      const synonymsCol = lastCol + 2;
      worksheet.getRow(1).getCell(smilesCol).value = "SMILES";
      worksheet.getRow(1).getCell(synonymsCol).value = "Synonyms";
      for (let r = 0; r < rows.length; r++) {
        worksheet.getRow(r + 2).getCell(smilesCol).value = rows[r].smiles ?? "";
        worksheet.getRow(r + 2).getCell(synonymsCol).value =
          (rows[r].synonyms ?? []).join("; ");
      }
      worksheet.getColumn(smilesCol).width = 40;
      worksheet.getColumn(synonymsCol).width = 30;

      // Add raw data points sheet
      const rawSheet = workbook.addWorksheet("Raw Data Points");
      rawSheet.addRow(["Compound", "SMILES", "Concentration", "Response"]);

      for (const row of rows) {
        const name =
          row.registration_number || row.molecule_name || row.molecule_id;
        for (const rv of Object.values(row.readouts)) {
          if (rv.data_points) {
            for (const pt of rv.data_points) {
              rawSheet.addRow([name, row.smiles ?? "", pt.x, pt.y]);
            }
          }
        }
      }
      rawSheet.getColumn(1).width = 20;
      rawSheet.getColumn(2).width = 40;
      rawSheet.getColumn(3).width = 15;
      rawSheet.getColumn(4).width = 15;
    },
    []
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
            <span className="text-sm font-medium">Hit Criteria Filter</span>
            <span className="text-muted-foreground">|</span>

            {activeCriteria.length > 0 ? (
              activeCriteria.map((rule, i) => (
                <Badge key={i} variant="secondary">
                  {criterionLabel(rule)}
                </Badge>
              ))
            ) : (
              <span className="text-sm text-muted-foreground italic">
                Disabled — showing all compounds
              </span>
            )}

            {isModified && activeCriteria.length > 0 && (
              <Badge
                variant="outline"
                className="border-yellow-500/40 text-yellow-400"
              >
                Modified
              </Badge>
            )}

            <div className="ml-auto flex items-center gap-2">
              <Button
                variant={showFlaggedOnly ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setShowFlaggedOnly((v) => !v)}
              >
                <Star
                  className={`mr-1 h-3.5 w-3.5 ${
                    showFlaggedOnly
                      ? "fill-yellow-400 text-yellow-400"
                      : ""
                  }`}
                />
                Flagged
              </Button>
              {activeCriteria.length > 0 ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveCriteria([])}
                >
                  <Eye className="mr-1 h-3.5 w-3.5" />
                  Show All
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveCriteria(savedCriteria)}
                >
                  <Filter className="mr-1 h-3.5 w-3.5" />
                  Apply Filter
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
        <div className="flex items-center gap-2">
          {selectedRows.length > 0 && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCollectionDialogOpen(true)}
              >
                <FolderPlus className="mr-1.5 h-3.5 w-3.5" />
                Add to Collection
              </Button>
              <span>{selectedRows.length} selected</span>
            </>
          )}
        </div>
      </div>

      {/* AG Grid with dynamic columns */}
      <DataGrid<CompoundActivity>
        rowData={filteredItems}
        columnDefs={columnDefs}
        height="auto"
        domLayout="autoHeight"
        rowHeight={115}
        onRowClick={(row) => setViewingId(row.molecule_id)}
        enableMultiSelect
        suppressSelectColumn
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.molecule_id}
        exportFilename={`${protocol.name}-activity`}
        excelEnhancer={excelEnhancer}
        emptyState={
          <EmptyState
            icon={Filter}
            title="No compounds match"
            description="Adjust or remove hit criteria to see more compounds."
          />
        }
      />

      {/* Compound detail sheet — driven by row click, independent from selection */}
      <Sheet
        open={!!viewing}
        onOpenChange={(open) => { if (!open) setViewingId(null); }}
      >
        <SheetContent side="right" className="w-[55vw] sm:max-w-[55vw] p-0 flex flex-col" showCloseButton>
          {viewing && (
            <>
              <SheetHeader className="px-4 pt-4 pb-2 pr-12 shrink-0 flex flex-row items-center justify-between">
                <div>
                  <SheetTitle>{viewing.registration_number}</SheetTitle>
                  {viewing.molecule_name && (
                    <p className="text-sm text-muted-foreground">{viewing.molecule_name}</p>
                  )}
                </div>
                <CurveNavigator
                  currentIndex={selectedIndex}
                  total={filteredItems.length}
                  onPrev={handlePrev}
                  onNext={handleNext}
                />
              </SheetHeader>
              <ScrollArea className="flex-1 min-h-0 px-4 pb-6">
                <div className="space-y-4">
                  {curvesLoading ? (
                    <Skeleton className="h-[300px] w-full" />
                  ) : compoundCurves && compoundCurves.length > 0 ? (
                    <>
                      <DoseResponseChart
                        curves={compoundCurves}
                        isInteractive={false}
                      />
                      <div className="rounded-lg border">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b bg-muted/50">
                              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Run</th>
                              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Batch</th>
                              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Fitted Value</th>
                              <th className="px-3 py-2 text-left font-medium text-muted-foreground">R²</th>
                              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Class</th>
                              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Hill Slope</th>
                            </tr>
                          </thead>
                          <tbody>
                            {compoundCurves.map((curve) => (
                              <tr key={curve.id} className="border-b last:border-0">
                                <td className="px-3 py-2 font-mono text-xs">{curve.run_id.slice(0, 8)}</td>
                                <td className="px-3 py-2 text-xs text-muted-foreground">
                                  {curve.batch_number ?? curve.batch_id.slice(0, 8)}
                                </td>
                                <td className="px-3 py-2 font-mono">
                                  {curve.fitted_value.toPrecision(4)} {curve.fitted_unit}
                                </td>
                                <td className="px-3 py-2 font-mono">{curve.r_squared.toFixed(3)}</td>
                                <td className="px-3 py-2">
                                  {curve.curve_class ? curveClassBadge(curve.curve_class) : "--"}
                                </td>
                                <td className="px-3 py-2 font-mono">{curve.hill_slope.toFixed(2)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No dose-response curves available for this compound.
                    </p>
                  )}
                </div>
              </ScrollArea>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* Curve overlay — 2-5 selected with DR data */}
      {overlayTraces && selectedRows.length >= 2 && selectedRows.length <= 5 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Dose-Response Comparison ({selectedRows.length} compounds)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {multiCurvesLoading ? (
              <Skeleton className="h-[350px] w-full" />
            ) : (
              <Plot
                data={overlayTraces}
                layout={comparisonLayout}
                config={{ displayModeBar: false, responsive: true }}
                useResizeHandler
                style={{ width: "100%", height: "350px" }}
              />
            )}
            {multiCurves && multiCurves.length > 0 && (
              <div className="mt-4">
                <ComparisonTable
                  rows={buildComparisonRows(
                    multiCurves,
                    new Map(selectedRows.map((r) => [r.molecule_id, { label: r.registration_number, batch: r.batch_number }]))
                  )}
                />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Fallback bar chart — 2-5 selected, no DR data */}
      {barChartData && !hasDRCurves && selectedRows.length >= 2 && selectedRows.length <= 5 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Comparison ({selectedRows.length} compounds)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={barChartData}
              layout={comparisonLayout}
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

      {/* Collection picker dialog */}
      <CollectionPickerDialog
        open={collectionDialogOpen}
        onOpenChange={setCollectionDialogOpen}
        moleculeIds={selectedRows.map((r) => r.molecule_id)}
      />
    </div>
  );
}
