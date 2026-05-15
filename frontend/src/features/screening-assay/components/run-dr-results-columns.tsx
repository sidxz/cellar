import { StructureThumbnail } from "@/shared/components/chemistry";
import { Badge } from "@/shared/components/ui/badge";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import {
  findInterceptValue,
  formatInterceptDisplay,
  interceptLabel,
  maxDoseFromRawData,
} from "../lib/intercept-label";
import type { CurveClass, InterceptSpec } from "../types";
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
//
// The column set is data-driven: one column per protocol intercept
// (EC50, EC90, IC10, ...) plus the fixed metadata columns (Compound,
// Structure, R², Class, Hill, Curve sparkline, Points). No literal
// "EC50" / "EC90" appears anywhere — headers come from
// `interceptLabel(spec)` and cells match by `(kind, level)` so a
// protocol-level relabel after fit doesn't lose data.
// ---------------------------------------------------------------------------

export function buildColumnDefs(intercepts: InterceptSpec[]): ColDef<CompoundCurveRow>[] {
  const interceptColumns = buildInterceptColumns(intercepts);
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
    ...interceptColumns,
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

/**
 * One column per protocol intercept spec.
 *
 * The primary intercept (`intercepts[0]`) reads `row.fitted_value` — the
 * domain layer guarantees this equals `intercept_values[0].value`, and
 * legacy curves that lack any persisted `intercept_values` still expose
 * the headline value here. Sort defaults to ascending on the primary
 * (lowest = most potent).
 *
 * Secondary intercepts look up their value via `findInterceptValue` —
 * matched by `(kind, level)` so a later protocol relabel of an intercept
 * doesn't break the column→cell wiring on existing curves.
 *
 * Edge cases:
 *   - `at_bound = true` → amber chip "⚠︎ at bound" (the curve never reaches
 *     the response threshold; the fit value is just the asymptotic bound).
 *   - Missing match → "—" with a "Recompute needed" title (the curve was
 *     fit before this intercept was added to the protocol).
 *
 * When the protocol declares no intercepts (legacy or single-intercept
 * curves), fall back to a single "Fitted Value" column so the table
 * still surfaces the headline number.
 */
function buildInterceptColumns(intercepts: InterceptSpec[]): ColDef<CompoundCurveRow>[] {
  if (intercepts.length === 0) {
    return [
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
    ];
  }

  return intercepts.map((spec, idx): ColDef<CompoundCurveRow> => {
    const label = interceptLabel(spec);
    return {
      headerName: label,
      colId: `intercept:${spec.kind}:${spec.level}`,
      width: 120,
      // Primary intercept gets default sort: lowest fitted value is most
      // potent for IC/EC curves.
      ...(idx === 0 ? { sort: "asc" as const } : {}),
      // valueGetter feeds AG Grid's sort + filter; cellRenderer paints
      // the chip / dash / at-bound state.
      valueGetter: (params) => {
        if (!params.data) return null;
        // Primary intercept tracks `fitted_value` even on legacy curves
        // that haven't been re-fit since intercept_values was added.
        if (idx === 0) return params.data.fitted_value;
        const iv = findInterceptValue(params.data.intercept_values, spec);
        return iv?.value ?? null;
      },
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        const iv = findInterceptValue(params.data.intercept_values, spec);
        const value = iv?.value ?? (idx === 0 ? params.data.fitted_value : null);
        const display = formatInterceptDisplay({
          value,
          at_bound: iv?.at_bound,
          curve_class: params.data.curve_class,
          max_dose: maxDoseFromRawData(params.data.data_points),
        });
        const showUnit = display.kind === "scalar" || display.kind === "qualifier";
        const unitSuffix =
          showUnit && params.data.fitted_unit ? ` ${params.data.fitted_unit}` : "";
        if (display.warning) {
          return (
            <Badge
              variant="outline"
              className="text-xs border-amber-500 text-amber-700"
              title={display.tooltip}
            >
              <span className="font-mono">
                {display.text}
                {unitSuffix}
              </span>
            </Badge>
          );
        }
        const className =
          display.kind === "scalar" ? "font-mono" : "font-mono text-muted-foreground";
        return (
          <span className={className} title={display.tooltip || undefined}>
            {display.text}
            {unitSuffix}
          </span>
        );
      },
    };
  });
}
