import { StructureThumbnail } from "@/shared/components/chemistry";
import { formatDate } from "@/shared/lib/format-date";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Star } from "lucide-react";
import type { CompoundFlag as CompoundFlagType } from "../../types";
import type { CompoundActivity, CurveClass, ReadoutDefInfo } from "../../types";
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
                    n={rv.n}
                    {rv.sd != null ? `, SD=${rv.sd.toPrecision(2)}` : ""}
                  </div>
                )}
              </div>
            );
          }
        : undefined,
      valueFormatter: isDR
        ? (p) => (p.value != null ? Number(p.value).toPrecision(4) : "--")
        : undefined,
      ...(isFirstReadout ? { sort: isDR ? ("asc" as const) : ("desc" as const) } : {}),
    });

    // Mean column
    cols.push({
      headerName: `${rd.name} Mean${unitSuffix}`,
      colId: `${rd.name}_mean`,
      width: 120,
      valueGetter: (p) => p.data?.readouts?.[rd.name]?.mean ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toPrecision(4) : "--"),
    });

    // DR-specific extra columns
    if (isDR) {
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
