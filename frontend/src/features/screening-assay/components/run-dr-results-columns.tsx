import { StructureThumbnail } from "@/shared/components/chemistry";
import { Badge } from "@/shared/components/ui/badge";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import type { CurveClass, CurveType } from "../types";
import { CURVE_TYPE_LABELS } from "../types";
import { CurveClassBadge } from "./curve-class-badge";
import { DoseResponseSparkline } from "./dose-response-sparkline";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

// ---------------------------------------------------------------------------
// Curve class badge helper
// ---------------------------------------------------------------------------

function curveClassBadge(cc: CurveClass | null) {
  return <CurveClassBadge curveClass={cc} />;
}

// ---------------------------------------------------------------------------
// Column factory
// ---------------------------------------------------------------------------

export function buildColumnDefs(): ColDef<CompoundCurveRow>[] {
  return [
    {
      headerName: "Compound",
      field: "registration_number",
      pinned: "left",
      flex: 1,
      minWidth: 160,
      autoHeight: true,
      wrapText: true,
      cellStyle: { lineHeight: "1.3", paddingTop: 6, paddingBottom: 6 },
      // Quick-filter input spans every identifier surfaced in the cell —
      // reg id, internal name, vendor synonyms, batch number — so a search
      // for "Compound-3" or a partial vendor alias matches the row.
      getQuickFilterText: (params) => {
        if (!params.data) return "";
        const { registration_number, molecule_name, synonyms, batch_number } = params.data;
        return [registration_number, molecule_name, batch_number, ...(synonyms ?? [])]
          .filter((s): s is string => !!s)
          .join(" ");
      },
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        const { registration_number, molecule_name, synonyms, batch_number } = params.data;
        const aliases: string[] = [];
        if (molecule_name && molecule_name !== registration_number) {
          aliases.push(molecule_name);
        }
        for (const s of synonyms) {
          if (s && s !== registration_number && !aliases.includes(s)) {
            aliases.push(s);
          }
        }
        return (
          <div className="leading-tight">
            <div className="font-mono font-medium">{registration_number}</div>
            {aliases.length > 0 && (
              <div
                className="text-xs text-muted-foreground break-words whitespace-normal"
                title={aliases.join(", ")}
              >
                {aliases.join(" · ")}
              </div>
            )}
            {batch_number && (
              <div className="text-[10px] text-muted-foreground">Batch: {batch_number}</div>
            )}
          </div>
        );
      },
    },
    {
      headerName: "Structure",
      colId: "structure",
      width: 130,
      sortable: false,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data?.smiles) return <span className="text-muted-foreground">--</span>;
        return (
          <div className="flex h-full items-center justify-center py-1">
            <StructureThumbnail smiles={params.data.smiles} size={104} />
          </div>
        );
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
      sort: "desc",
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
      headerName: "R²",
      field: "r_squared",
      width: 80,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(3) : "--"),
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
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(2) : "--"),
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

// Module-level constant — buildColumnDefs has no component-state closure
// so there is no need to re-create the array each render.
export const COLUMN_DEFS = buildColumnDefs();
