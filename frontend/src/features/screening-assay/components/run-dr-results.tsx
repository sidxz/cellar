"use client";

import { useMemo, useState, useCallback } from "react";
import { Eye, Filter, FlaskConical, Settings2, RotateCcw } from "lucide-react";
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
import type { ExcelEnhancer } from "@/shared/components/data-grid/export-toolbar";
import { renderCurveToBase64 } from "@/shared/lib/export/curve-image";
import { fetchStructureImages } from "@/shared/lib/export/structure-image";
import { useMolecules } from "@/features/chemical-registration/hooks/use-molecules";
import { DoseResponseSparkline } from "./dose-response-sparkline";
import { StructureRenderer } from "@/shared/components/chemistry";
import { DoseResponseChart } from "./dose-response-chart";
import { HitCriteriaDialog } from "./hit-criteria-dialog";
import { useProtocol } from "../hooks/use-protocols";
import {
  CURVE_CLASS_LABELS,
  CURVE_TYPE_LABELS,
  type CurveClass,
  type CurveType,
  type DoseResponseCurve,
  type HitCriterion,
  type Run,
} from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** One row in the grid = one compound (best curve per molecule) */
interface CompoundCurveRow {
  molecule_id: string;
  molecule_name: string;
  registration_number: string;
  smiles: string | null;
  batch_number: string | null;
  curve_type: string;
  fitted_value: number;
  fitted_unit: string;
  hill_slope: number;
  top: number;
  bottom: number;
  r_squared: number;
  num_points: number;
  curve_class: CurveClass | null;
  data_points: Array<{ x: number; y: number }> | null;
  /** All curves for this molecule in this run (for detail panel) */
  all_curves: DoseResponseCurve[];
}

// ---------------------------------------------------------------------------
// Helpers
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

/** Group curves by molecule, pick best (lowest fitted_value for IC50-type) */
function buildCompoundRows(
  curves: DoseResponseCurve[],
  molMap: Map<string, { registration_number: string; smiles: string | null; synonyms: string[] }>,
): CompoundCurveRow[] {
  const byMolecule = new Map<string, DoseResponseCurve[]>();
  for (const c of curves) {
    const mid = c.molecule_id;
    if (!byMolecule.has(mid)) byMolecule.set(mid, []);
    byMolecule.get(mid)!.push(c);
  }

  const rows: CompoundCurveRow[] = [];
  for (const [, molCurves] of byMolecule) {
    // Best curve = lowest fitted_value (most potent), excluding inactive
    const active = molCurves.filter((c) => c.curve_class !== "inactive");
    const sorted = (active.length > 0 ? active : molCurves).sort(
      (a, b) => a.fitted_value - b.fitted_value
    );
    const best = sorted[0];

    // Condense raw_data to [{x, y}]
    let dataPoints: Array<{ x: number; y: number }> | null = null;
    if (best.raw_data && Array.isArray(best.raw_data)) {
      dataPoints = [];
      for (const pt of best.raw_data) {
        const x = (pt as Record<string, unknown>).concentration ?? (pt as Record<string, unknown>).x;
        const y = (pt as Record<string, unknown>).response ?? (pt as Record<string, unknown>).y;
        if (typeof x === "number" && typeof y === "number") {
          dataPoints.push({ x, y });
        }
      }
    }

    rows.push({
      molecule_id: best.molecule_id,
      molecule_name: best.molecule_name ?? best.molecule_id.slice(0, 8),
      registration_number: molMap.get(best.molecule_id)?.registration_number ?? best.molecule_id.slice(0, 8),
      smiles: molMap.get(best.molecule_id)?.smiles ?? null,
      batch_number: best.batch_number,
      curve_type: best.curve_type,
      fitted_value: best.fitted_value,
      fitted_unit: best.fitted_unit,
      hill_slope: best.hill_slope,
      top: best.top,
      bottom: best.bottom,
      r_squared: best.r_squared,
      num_points: best.num_points,
      curve_class: best.curve_class as CurveClass | null,
      data_points: dataPoints,
      all_curves: molCurves,
    });
  }
  return rows;
}

/** Apply hit criteria filter to compound rows */
function applyHitFilter(
  rows: CompoundCurveRow[],
  criteria: HitCriterion[]
): CompoundCurveRow[] {
  if (criteria.length === 0) return rows;
  return rows.filter((row) =>
    criteria.every((rule) => {
      if (rule.readout_name === "Curve Class") {
        if (rule.operator === "in" && Array.isArray(rule.value)) {
          return (
            row.curve_class != null &&
            (rule.value as string[]).includes(row.curve_class)
          );
        }
        return true;
      }
      // For IC50/EC50 rules — match against fitted_value
      const threshold = typeof rule.value === "number" ? rule.value : 0;
      switch (rule.operator) {
        case "gt":
          return row.fitted_value > threshold;
        case "lt":
          return row.fitted_value < threshold;
        case "gte":
          return row.fitted_value >= threshold;
        case "lte":
          return row.fitted_value <= threshold;
        default:
          return true;
      }
    })
  );
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

function buildColumnDefs(): ColDef<CompoundCurveRow>[] {
  return [
    {
      headerName: "Compound",
      field: "registration_number",
      pinned: "left",
      flex: 1,
      minWidth: 160,
      headerCheckboxSelection: true,
      checkboxSelection: true,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        return (
          <div className="leading-tight">
            <span className="font-medium">{params.data.registration_number}</span>
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
      headerName: "Structure",
      colId: "structure",
      width: 100,
      sortable: false,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data?.smiles) return <span className="text-muted-foreground">--</span>;
        return <StructureRenderer smiles={params.data.smiles} width={80} height={55} />;
      },
    },
    {
      headerName: "Type",
      field: "curve_type",
      width: 70,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.value) return null;
        return (
          <Badge variant="outline" className="text-xs">
            {CURVE_TYPE_LABELS[params.value as CurveType] ?? params.value}
          </Badge>
        );
      },
    },
    {
      headerName: "Fitted Value",
      field: "fitted_value",
      width: 120,
      sort: "asc",
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        return (
          <span className="font-mono">
            {params.data.fitted_value.toPrecision(4)} {params.data.fitted_unit}
          </span>
        );
      },
    },
    {
      headerName: "R\u00B2",
      field: "r_squared",
      width: 80,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(3) : "--",
      cellClass: "font-mono",
    },
    {
      headerName: "Class",
      field: "curve_class",
      width: 90,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) =>
        curveClassBadge(params.value ?? null),
    },
    {
      headerName: "Hill Slope",
      field: "hill_slope",
      width: 90,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(2) : "--",
      cellClass: "font-mono",
    },
    {
      headerName: "Curve",
      colId: "sparkline",
      width: 150,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        return (
          <DoseResponseSparkline
            params={{
              hill_slope: params.data.hill_slope,
              top: params.data.top,
              bottom: params.data.bottom,
              fitted_value: params.data.fitted_value,
              r_squared: params.data.r_squared,
            }}
            dataPoints={params.data.data_points}
            curveClass={params.data.curve_class}
          />
        );
      },
    },
    {
      headerName: "Points",
      field: "num_points",
      width: 70,
    },
  ];
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RunDoseResponseResultsProps {
  run: Run;
  curves: DoseResponseCurve[];
  isLoading?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RunDoseResponseResults({
  run,
  curves,
  isLoading,
}: RunDoseResponseResultsProps) {
  const { data: protocol } = useProtocol(run.protocol_id);
  const { data: molecules } = useMolecules();

  const molMap = useMemo(() => {
    const m = new Map<string, { registration_number: string; smiles: string | null; synonyms: string[] }>();
    for (const mol of molecules ?? []) {
      m.set(mol.id, {
        registration_number: mol.registration_number,
        smiles: mol.structure?.smiles ?? null,
        synonyms: mol.identifiers
          ?.filter((id) => id.identifier_type === "custom")
          .map((id) => id.identifier) ?? [],
      });
    }
    return m;
  }, [molecules]);

  // Hit criteria state
  const savedCriteria: HitCriterion[] =
    protocol?.recommended_hit_criteria ?? [];
  const [activeCriteria, setActiveCriteria] =
    useState<HitCriterion[]>(savedCriteria);
  const isModified =
    JSON.stringify(activeCriteria) !== JSON.stringify(savedCriteria);

  const [criteriaDialogOpen, setCriteriaDialogOpen] = useState(false);

  // Selection state
  const [selectedRows, setSelectedRows] = useState<CompoundCurveRow[]>([]);

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<CompoundCurveRow>) => {
      setSelectedRows(event.api.getSelectedRows());
    },
    []
  );

  // Sync savedCriteria when protocol updates
  const prevSavedRef = JSON.stringify(protocol?.recommended_hit_criteria ?? []);
  const [lastSynced, setLastSynced] = useState(prevSavedRef);
  if (prevSavedRef !== lastSynced) {
    setActiveCriteria(protocol?.recommended_hit_criteria ?? []);
    setLastSynced(prevSavedRef);
  }

  // Build rows from curves
  const allRows = useMemo(() => buildCompoundRows(curves, molMap), [curves, molMap]);
  const filteredRows = useMemo(
    () => applyHitFilter(allRows, activeCriteria),
    [allRows, activeCriteria]
  );

  const columnDefs = useMemo(() => buildColumnDefs(), []);

  // Excel enhancer — sparkline images + raw data sheet
  const excelEnhancer: ExcelEnhancer = useCallback(
    async (workbook, worksheet, rows: CompoundCurveRow[]) => {
      // Find "Curve" column (by header text)
      const curveColIdx = worksheet.columns.findIndex(
        (_, i) => worksheet.getRow(1).getCell(i + 1).value === "Curve"
      );

      if (curveColIdx >= 0) {
        for (let r = 0; r < rows.length; r++) {
          const row = rows[r];
          const base64 = renderCurveToBase64(
            {
              hill_slope: row.hill_slope,
              top: row.top,
              bottom: row.bottom,
              fitted_value: row.fitted_value,
            },
            row.data_points
          );
          if (!base64) continue;

          const imageId = workbook.addImage({ base64, extension: "png" });
          worksheet.addImage(imageId, {
            tl: { col: curveColIdx, row: r + 1 },
            ext: { width: 200, height: 60 },
          });
        }
        const col = worksheet.getColumn(curveColIdx + 1);
        col.width = 30;
        for (let r = 2; r <= rows.length + 1; r++) {
          worksheet.getRow(r).height = 50;
        }
      }

      // Add Structure, SMILES, and Synonyms columns
      const lastCol = worksheet.columnCount;
      const structCol = lastCol + 1;
      const smilesCol = lastCol + 2;
      const synonymsCol = lastCol + 3;
      worksheet.getRow(1).getCell(structCol).value = "Structure";
      worksheet.getRow(1).getCell(smilesCol).value = "SMILES";
      worksheet.getRow(1).getCell(synonymsCol).value = "Synonyms";

      // Batch-fetch structure images from backend
      const allSmiles = rows
        .map((r) => molMap.get(r.molecule_id)?.smiles)
        .filter(Boolean) as string[];
      const structImages = await fetchStructureImages(allSmiles, 150, 100);

      for (let r = 0; r < rows.length; r++) {
        const mol = molMap.get(rows[r].molecule_id);
        const smiles = mol?.smiles ?? "";
        worksheet.getRow(r + 2).getCell(smilesCol).value = smiles;
        worksheet.getRow(r + 2).getCell(synonymsCol).value =
          (mol?.synonyms ?? []).join("; ");

        if (smiles && structImages[smiles]) {
          const imgId = workbook.addImage({
            base64: structImages[smiles],
            extension: "png",
          });
          worksheet.addImage(imgId, {
            tl: { col: structCol - 1, row: r + 1 },
            ext: { width: 150, height: 80 },
          });
        }
        worksheet.getRow(r + 2).height = 65;
      }
      worksheet.getColumn(structCol).width = 22;
      worksheet.getColumn(smilesCol).width = 40;
      worksheet.getColumn(synonymsCol).width = 30;

      // Raw data points sheet
      const rawSheet = workbook.addWorksheet("Raw Data Points");
      rawSheet.addRow(["Compound", "SMILES", "Concentration", "Response"]);
      for (const row of rows) {
        const name = row.molecule_name || row.molecule_id;
        const mol = molMap.get(row.molecule_id);
        if (row.data_points) {
          for (const pt of row.data_points) {
            rawSheet.addRow([name, mol?.smiles ?? "", pt.x, pt.y]);
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

  // Detail panel: curves for selected compound
  const selectedCurves =
    selectedRows.length === 1 ? selectedRows[0].all_curves : null;

  // Loading
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (curves.length === 0) {
    return (
      <EmptyState
        icon={FlaskConical}
        title="No dose-response curves"
        description="Fit curves from readout data or add curves manually to see results here."
      />
    );
  }

  const hasCriteria = savedCriteria.length > 0 || activeCriteria.length > 0;

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center gap-4 text-sm">
        <Badge variant="secondary">
          {allRows.length} compound{allRows.length !== 1 ? "s" : ""}
        </Badge>
        {hasCriteria && (
          <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
            {filteredRows.length} hit{filteredRows.length !== 1 ? "s" : ""}
          </Badge>
        )}
      </div>

      {/* Hit Criteria Filter Bar */}
      {!hasCriteria ? (
        <Card className="border-2 border-dashed">
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="font-medium">No hit criteria defined</p>
              <p className="text-sm text-muted-foreground">
                Define criteria on the protocol to filter hits in this run.
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
              activeCriteria.map((rule, i) => {
                const op = { gt: ">", lt: "<", gte: ">=", lte: "<=", in: "in" }[
                  rule.operator
                ] ?? rule.operator;
                const val = Array.isArray(rule.value)
                  ? rule.value.join(", ")
                  : rule.value;
                return (
                  <Badge key={i} variant="secondary">
                    {rule.readout_name} {op} {val}
                  </Badge>
                );
              })
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
                <Settings2 className="mr-1 h-3.5 w-3.5" /> Edit Criteria
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* AG Grid */}
      <DataGrid<CompoundCurveRow>
        rowData={filteredRows}
        columnDefs={columnDefs}
        height="500px"
        rowSelection="multiple"
        rowHeight={70}
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.molecule_id}
        exportFilename={`run-${run.id.slice(0, 8)}-dose-response`}
        excelEnhancer={excelEnhancer}
        emptyState={
          <EmptyState
            icon={Filter}
            title="No compounds match criteria"
            description="Adjust or remove hit criteria to see more compounds."
          />
        }
      />

      {/* Detail panel — single compound selected */}
      {selectedCurves && selectedRows.length === 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {selectedRows[0].molecule_name}
              {selectedRows[0].batch_number && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  Batch: {selectedRows[0].batch_number}
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DoseResponseChart
              curves={selectedCurves}
              isInteractive={!run.is_locked}
            />
          </CardContent>
        </Card>
      )}

      {/* Hit criteria dialog */}
      {protocol && (
        <HitCriteriaDialog
          protocolId={protocol.id}
          readoutDefinitions={protocol.readout_definitions}
          currentCriteria={protocol.recommended_hit_criteria}
          open={criteriaDialogOpen}
          onOpenChange={setCriteriaDialogOpen}
        />
      )}
    </div>
  );
}
