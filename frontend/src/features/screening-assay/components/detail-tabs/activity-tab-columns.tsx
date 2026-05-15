import { StructureThumbnail } from "@/shared/components/chemistry";
import { Badge } from "@/shared/components/ui/badge";
import { formatDate } from "@/shared/lib/format-date";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Star } from "lucide-react";
import {
  findInterceptValue,
  formatInterceptDisplay,
  interceptLabel,
  maxDoseFromRawData,
} from "../../lib/intercept-label";
import type {
  CompoundActivity,
  CompoundFlag as CompoundFlagType,
  CurveClass,
  InterceptSpec,
  ReadoutDefInfo,
} from "../../types";
import { CurveClassBadge } from "../curve-class-badge";
import { DoseResponseSparkline } from "../dose-response-sparkline";

// ---------------------------------------------------------------------------
// Curve class badge helper
// ---------------------------------------------------------------------------

function curveClassBadge(cc: CurveClass | null) {
  return <CurveClassBadge curveClass={cc} />;
}

// ---------------------------------------------------------------------------
// Dynamic column factory
// ---------------------------------------------------------------------------

export function buildColumnDefs(
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
              // biome-ignore lint/style/noNonNullAssertion: null-guard above guarantees params.data is set
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
            <span className="font-medium">{params.data.registration_number}</span>
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

    if (isDR) {
      // Dose-response readouts get one column per protocol-declared
      // intercept (EC50, EC90, ...). Each cell reads the value from the
      // best curve's `intercept_values`, matched by (kind, level) so a
      // protocol relabel doesn't break the column→cell wiring.
      const specs = rd.intercepts ?? [];
      if (specs.length === 0) {
        // No declared intercepts (legacy / single-intercept protocols)
        // — fall back to one "Best" column reading the headline value.
        cols.push(
          buildPrimaryFitColumn(rd, unitSuffix, /* defaultSort */ isFirstReadout),
        );
      } else {
        specs.forEach((spec, idx) => {
          cols.push(
            buildInterceptColumn(rd, spec, idx === 0, isFirstReadout && idx === 0),
          );
        });
      }
      cols.push({
        headerName: "Mean",
        colId: `${rd.name}_mean`,
        width: 120,
        valueGetter: (p) => p.data?.readouts?.[rd.name]?.mean ?? null,
        valueFormatter: (p) => (p.value != null ? Number(p.value).toPrecision(4) : "--"),
      });
      cols.push({
        headerName: "Class",
        colId: `${rd.name}_class`,
        width: 90,
        valueGetter: (p) => p.data?.readouts?.[rd.name]?.curve_class ?? null,
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
    } else {
      // Numeric readout — single Best + Mean pair as before.
      cols.push({
        headerName: `${rd.name} Best${unitSuffix}`,
        colId: `${rd.name}_best`,
        width: 120,
        valueGetter: (p) => p.data?.readouts?.[rd.name]?.best ?? null,
        cellRenderer: (params: ICellRendererParams<CompoundActivity>) => {
          if (params.value == null) return "--";
          const rv = params.data?.readouts?.[rd.name];
          return (
            <div className="leading-tight">
              <span>{Number(params.value).toPrecision(4)}</span>
              {rv?.n != null && rv.n > 1 && (
                <div className="text-[10px] text-muted-foreground">
                  n={rv.n}
                  {rv.sd != null ? `, SD=${rv.sd.toPrecision(2)}` : ""}
                </div>
              )}
            </div>
          );
        },
        ...(isFirstReadout ? { sort: "desc" as const } : {}),
      });
      cols.push({
        headerName: `${rd.name} Mean${unitSuffix}`,
        colId: `${rd.name}_mean`,
        width: 120,
        valueGetter: (p) => p.data?.readouts?.[rd.name]?.mean ?? null,
        valueFormatter: (p) => (p.value != null ? Number(p.value).toPrecision(4) : "--"),
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
      return formatDate(p.value as string);
    },
  });

  return cols;
}

// ---------------------------------------------------------------------------
// Per-intercept column builders for DR readouts
// ---------------------------------------------------------------------------

/** Fallback "Best" column when a DR readout declares no explicit intercept
 *  list (legacy protocol or single-intercept curve). Reads the headline
 *  fitted value off `ReadoutValue.best`. */
function buildPrimaryFitColumn(
  rd: ReadoutDefInfo,
  unitSuffix: string,
  defaultSort: boolean,
): ColDef<CompoundActivity> {
  return {
    headerName: `${rd.name} Best${unitSuffix}`,
    colId: `${rd.name}_best`,
    width: 120,
    valueGetter: (p) => p.data?.readouts?.[rd.name]?.best ?? null,
    valueFormatter: (p) => (p.value != null ? Number(p.value).toPrecision(4) : "--"),
    ...(defaultSort ? { sort: "asc" as const } : {}),
  };
}

/** One column per protocol intercept spec. Primary intercept reads
 *  `ReadoutValue.best` (back-compat with legacy fits that lack a
 *  persisted `intercept_values[0]`); secondaries read via
 *  `findInterceptValue` and surface "—" with a Recompute hint when the
 *  curve wasn't fit under this spec. */
function buildInterceptColumn(
  rd: ReadoutDefInfo,
  spec: InterceptSpec,
  isPrimary: boolean,
  defaultSort: boolean,
): ColDef<CompoundActivity> {
  const unitSuffix = rd.unit ? ` (${rd.unit})` : "";
  const headerLabel = interceptLabel(spec);
  return {
    headerName: `${rd.name} ${headerLabel}${unitSuffix}`,
    colId: `${rd.name}_${spec.kind}_${spec.level}`,
    width: 130,
    ...(defaultSort ? { sort: "asc" as const } : {}),
    valueGetter: (params) => {
      const rv = params.data?.readouts?.[rd.name];
      if (!rv) return null;
      const iv = findInterceptValue(rv.curve_params?.intercept_values, spec);
      // Same display rule the cellRenderer applies — keeps sort and
      // display in lockstep (inactive → null, qualifier → +Infinity).
      const value = iv?.value ?? (isPrimary ? (rv.best ?? null) : null);
      return formatInterceptDisplay({
        value,
        at_bound: iv?.at_bound,
        curve_class: rv.curve_class,
        max_dose: maxDoseFromRawData(rv.data_points),
      }).sortValue;
    },
    cellRenderer: (params: ICellRendererParams<CompoundActivity>) => {
      const rv = params.data?.readouts?.[rd.name];
      const iv = findInterceptValue(rv?.curve_params?.intercept_values, spec);
      const value = iv?.value ?? (isPrimary ? (rv?.best ?? null) : null);
      const display = formatInterceptDisplay({
        value,
        at_bound: iv?.at_bound,
        curve_class: rv?.curve_class,
        max_dose: maxDoseFromRawData(rv?.data_points),
      });
      if (display.warning) {
        return (
          <Badge
            variant="outline"
            className="text-xs border-amber-500 text-amber-700"
            title={display.tooltip}
          >
            <span className="font-mono">{display.text}</span>
          </Badge>
        );
      }
      const className =
        display.kind === "scalar" ? "font-mono" : "font-mono text-muted-foreground";
      return (
        <span className={className} title={display.tooltip || undefined}>
          {display.text}
        </span>
      );
    },
  };
}
