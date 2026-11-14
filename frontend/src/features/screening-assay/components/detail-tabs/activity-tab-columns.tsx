import { StructureThumbnail } from "@/shared/components/chemistry/structure-thumbnail";
import { EntityLink } from "@/shared/components/entity-link";
import { Badge } from "@/shared/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/components/ui/tooltip";
import { formatDate } from "@/shared/lib/format-date";
import type { ColDef, ColGroupDef, ICellRendererParams } from "ag-grid-community";
import { Star } from "lucide-react";
import { type CatalogColumn, compareForDirection } from "../../lib/activity-columns";
import {
  findInterceptValue,
  formatInterceptDisplay,
  maxDoseFromRawData,
} from "../../lib/intercept-label";
import type {
  CompoundActivity,
  CompoundFlag as CompoundFlagType,
  CurveClass,
  ReadoutDefInfo,
} from "../../types";
import { CurveClassBadge } from "../curve-class-badge";
import { DoseResponseSparkline } from "../dose-response-sparkline";
import { structureColumn } from "../grid-columns";
import type { HitStatus } from "./use-activity-tab";

export type Statistic = "best" | "mean";

export interface ActivityColumnOptions {
  catalog: readonly CatalogColumn[];
  visible: ReadonlySet<string>;
  readoutDefs: readonly ReadoutDefInfo[];
  statistic: Statistic;
  showStructures: boolean;
  /** Hit status per molecule; null when the protocol has no hit rule. */
  hits: ReadonlyMap<string, HitStatus> | null;
  sort: { colId: string; sort: "asc" | "desc" } | null;
  flagsByMolecule: Map<string, CompoundFlagType>;
  onToggleFlag: (moleculeId: string, existingFlagId: string | null) => void;
}

type Col = ColDef<CompoundActivity> | ColGroupDef<CompoundActivity>;

const NUMERIC = "text-right tabular-nums";
const SIGNED = new Set(["delta_tm", "max_delta_tm", "delta_tm_at_concentration"]);

/** Four significant figures, true minus; shifts carry their sign. */
function fmtValue(v: number, signed: boolean): string {
  const size = String(Number(Math.abs(v).toPrecision(4)));
  return `${v < 0 ? "−" : signed && v > 0 ? "+" : ""}${size}`;
}

const HIT_LABEL: Record<HitStatus, string> = {
  meets: "Meets",
  fails: "Doesn't meet",
  no_data: "No data",
};
const HIT_RANK: Record<HitStatus, number> = { meets: 0, no_data: 1, fails: 2 };

function CompoundCell({
  row,
  flag,
  onToggleFlag,
}: {
  row: CompoundActivity;
  flag: CompoundFlagType | undefined;
  onToggleFlag: ActivityColumnOptions["onToggleFlag"];
}) {
  const link = <EntityLink type="compound" id={row.molecule_id} label={row.registration_number} />;
  return (
    <div className="flex h-full items-center gap-2 leading-tight">
      <button
        type="button"
        className="flex-shrink-0"
        onClick={(e) => {
          e.stopPropagation();
          onToggleFlag(row.molecule_id, flag?.id ?? null);
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
      {row.smiles ? (
        <Tooltip>
          {/* EntityLink takes no trigger props or ref, so a span carries them. */}
          <TooltipTrigger asChild>
            <span className="inline-flex font-medium">{link}</span>
          </TooltipTrigger>
          <TooltipContent
            side="right"
            sideOffset={6}
            collisionPadding={12}
            className="border bg-popover p-1.5 text-popover-foreground shadow-lg"
          >
            <div className="rounded-sm bg-white p-1">
              <StructureThumbnail smiles={row.smiles} size={160} />
            </div>
          </TooltipContent>
        </Tooltip>
      ) : (
        <span className="font-medium">{link}</span>
      )}
      {row.synonyms?.[0] && (
        <span className="truncate text-xs text-muted-foreground">{row.synonyms[0]}</span>
      )}
    </div>
  );
}

function valueColumn(
  c: CatalogColumn,
  rd: ReadoutDefInfo | undefined,
  o: ActivityColumnOptions,
): ColDef<CompoundActivity> {
  const signed = SIGNED.has(rd?.melt_config?.measure ?? "");
  return {
    headerName: c.label,
    headerTooltip: c.readout,
    colId: c.colId,
    hide: !o.visible.has(c.colId),
    width: 130,
    wrapHeaderText: true,
    autoHeaderHeight: true,
    headerClass: "ag-right-aligned-header",
    cellClass: NUMERIC,
    comparator: compareForDirection(rd?.best_direction ?? "high"),
    ...(o.sort?.colId === c.colId ? { sort: o.sort.sort } : {}),
    valueGetter: (p) => p.data?.readouts?.[c.readout]?.[o.statistic] ?? null,
    cellRenderer: (p: ICellRendererParams<CompoundActivity>) => {
      if (p.value == null) return <span className="text-muted-foreground">—</span>;
      const rv = p.data?.readouts?.[c.readout];
      const parts = [
        rv?.n != null ? `n=${rv.n}` : null,
        rv?.best != null ? `best ${fmtValue(rv.best, signed)}` : null,
        rv?.mean != null ? `mean ${fmtValue(rv.mean, signed)}` : null,
        rv?.sd != null ? `SD ${rv.sd.toPrecision(2)}` : null,
      ].filter(Boolean);
      return <span title={parts.join(" · ")}>{fmtValue(p.value as number, signed)}</span>;
    },
  };
}

function interceptColumn(
  c: CatalogColumn,
  rd: ReadoutDefInfo | undefined,
  o: ActivityColumnOptions,
): ColDef<CompoundActivity> {
  // The table-wide Mean shows the geometric mean of the primary fits;
  // secondary intercepts always read the best curve.
  const useMean = o.statistic === "mean" && c.primary;
  const readValue = (data: CompoundActivity | undefined) => {
    const rv = data?.readouts?.[c.readout];
    if (!rv) return { rv, iv: undefined, value: null };
    if (useMean) return { rv, iv: undefined, value: rv.mean ?? null };
    const iv = c.intercept
      ? findInterceptValue(rv.curve_params?.intercept_values, c.intercept)
      : undefined;
    return { rv, iv, value: iv?.value ?? (c.primary ? (rv.best ?? null) : null) };
  };
  const display = (data: CompoundActivity | undefined) => {
    const { rv, iv, value } = readValue(data);
    return formatInterceptDisplay({
      value,
      at_bound: iv?.at_bound,
      curve_class: rv?.curve_class,
      max_dose: maxDoseFromRawData(rv?.data_points),
    });
  };
  return {
    headerName: useMean ? `${c.label} · geo. mean` : c.label,
    headerTooltip: c.readout,
    colId: c.colId,
    hide: !o.visible.has(c.colId),
    width: 130,
    wrapHeaderText: true,
    autoHeaderHeight: true,
    comparator: compareForDirection(rd?.best_direction ?? "low"),
    ...(o.sort?.colId === c.colId ? { sort: o.sort.sort } : {}),
    // Same rule as the cell, so sorting and display agree (inactive → null).
    valueGetter: (p) => display(p.data).sortValue,
    cellRenderer: (p: ICellRendererParams<CompoundActivity>) => {
      const d = display(p.data);
      if (d.warning) {
        return (
          <Badge
            variant="outline"
            className="border-amber-500 text-xs text-amber-700"
            title={d.tooltip}
          >
            <span className="font-mono">{d.text}</span>
          </Badge>
        );
      }
      return (
        <span
          className={d.kind === "scalar" ? "font-mono" : "font-mono text-muted-foreground"}
          title={d.tooltip || undefined}
        >
          {d.text}
        </span>
      );
    },
  };
}

function curveColumn(c: CatalogColumn, o: ActivityColumnOptions): ColDef<CompoundActivity> {
  const base = { headerName: c.label, colId: c.colId, hide: !o.visible.has(c.colId) };
  if (c.kind === "class") {
    return {
      ...base,
      width: 90,
      valueGetter: (p) => p.data?.readouts?.[c.readout]?.curve_class ?? null,
      cellRenderer: (p: ICellRendererParams<CompoundActivity>) => (
        <CurveClassBadge curveClass={(p.value as CurveClass | null) ?? null} />
      ),
    };
  }
  return {
    ...base,
    width: 150,
    sortable: false,
    cellRenderer: (p: ICellRendererParams<CompoundActivity>) => {
      const rv = p.data?.readouts?.[c.readout];
      if (!rv?.curve_params) return <span className="text-muted-foreground">—</span>;
      return (
        <DoseResponseSparkline
          params={rv.curve_params}
          dataPoints={rv.data_points}
          curveClass={rv.curve_class}
        />
      );
    },
  };
}

/** The Activity grid's columns: compound, hit status, then one column per
 *  result from the catalog, grouped by window or dose-response readout. */
export function buildColumnDefs(o: ActivityColumnOptions): Col[] {
  const cols: Col[] = [
    {
      headerName: "Compound",
      colId: "compound",
      field: "registration_number",
      pinned: "left",
      minWidth: 200,
      width: 220,
      checkboxSelection: true,
      headerCheckboxSelection: true,
      cellRenderer: (p: ICellRendererParams<CompoundActivity>) =>
        p.data ? (
          <CompoundCell
            row={p.data}
            flag={o.flagsByMolecule.get(p.data.molecule_id)}
            onToggleFlag={o.onToggleFlag}
          />
        ) : null,
    },
  ];
  const hits = o.hits;
  if (hits) {
    cols.push({
      headerName: "Hit",
      colId: "hit",
      pinned: "left",
      width: 130,
      headerTooltip: "The protocol's recommended hit rule, on each compound's best values",
      valueGetter: (p) => {
        const s = p.data ? hits.get(p.data.molecule_id) : undefined;
        return s ? HIT_RANK[s] : null;
      },
      cellRenderer: (p: ICellRendererParams<CompoundActivity>) => {
        const s = p.data ? hits.get(p.data.molecule_id) : undefined;
        if (!s) return null;
        return (
          <Badge
            variant={s === "meets" ? "default" : "outline"}
            className={s === "meets" ? undefined : "text-muted-foreground"}
          >
            {HIT_LABEL[s]}
          </Badge>
        );
      },
    });
  }
  if (o.showStructures) cols.push(structureColumn<CompoundActivity>((row) => row.smiles));

  const rdByName = new Map(o.readoutDefs.map((rd) => [rd.name, rd]));
  for (const c of o.catalog) {
    const rd = rdByName.get(c.readout);
    const leaf =
      c.kind === "value"
        ? valueColumn(c, rd, o)
        : c.kind === "intercept"
          ? interceptColumn(c, rd, o)
          : curveColumn(c, o);
    const last = cols.at(-1);
    if (c.group == null) cols.push(leaf);
    else if (last && "children" in last && last.groupId === c.group) last.children.push(leaf);
    else cols.push({ headerName: c.group, groupId: c.group, children: [leaf] });
  }

  cols.push(
    { headerName: "Runs", field: "run_count", width: 80, cellClass: NUMERIC },
    {
      headerName: "Last tested",
      field: "last_tested",
      width: 120,
      valueFormatter: (p) => (p.value ? formatDate(p.value as string) : "—"),
    },
  );
  return cols;
}
