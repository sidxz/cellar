"use client";

import { Badge } from "@/shared/components/ui/badge";
import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { cn, shortId } from "@/shared/lib/utils";
import { useMemo, useState } from "react";
import {
  CURVE_CLASS_LABELS,
  CURVE_TYPE_LABELS,
  type CurveClass,
  type CurveType,
  type DoseResponseCurve,
} from "../types";

const TRACE_COLORS = GROUP_PALETTE.slice(0, 5);

interface ComparisonRow {
  label: string;
  batch?: string | null;
  color: string;
  curve_type: string;
  fitted_value: number;
  fitted_unit: string;
  hill_slope: number;
  r_squared: number;
  curve_class: CurveClass | null;
  top: number;
  bottom: number;
}

interface ComparisonTableProps {
  rows: ComparisonRow[];
}

type SortKey = "label" | "fitted_value" | "hill_slope" | "r_squared";

export function ComparisonTable({ rows }: ComparisonTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("fitted_value");
  const [sortAsc, setSortAsc] = useState(true);

  const sorted = useMemo(() => {
    return [...rows].sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === "string" && typeof bv === "string")
        return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
  }, [rows, sortKey, sortAsc]);

  const toggle = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const bestIC50 = Math.min(...rows.map((r) => r.fitted_value));
  const bestR2 = Math.max(...rows.map((r) => r.r_squared));

  const hdr = (label: string, key: SortKey) => (
    <th
      className="px-3 py-2 text-left font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none"
      onClick={() => toggle(key)}
    >
      {label} {sortKey === key ? (sortAsc ? "\u2191" : "\u2193") : ""}
    </th>
  );

  const curveLabel = rows[0]
    ? (CURVE_TYPE_LABELS[rows[0].curve_type as CurveType] ?? rows[0].curve_type)
    : "Value";

  return (
    <div className="rounded-lg border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50">
            {hdr("Compound", "label")}
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Batch</th>
            {hdr(`${curveLabel} (${rows[0]?.fitted_unit ?? ""})`, "fitted_value")}
            {hdr("Hill Slope", "hill_slope")}
            {hdr("R\u00B2", "r_squared")}
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Class</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Top%</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Bottom%</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.label} className="border-b last:border-0">
              <td className="px-3 py-2">
                <span className="inline-flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: row.color }}
                  />
                  <span className="font-medium">{row.label}</span>
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">{row.batch ?? "--"}</td>
              <td
                className={cn(
                  "px-3 py-2 font-mono",
                  row.fitted_value === bestIC50 && "text-success font-semibold",
                )}
              >
                {row.fitted_value.toPrecision(4)}
              </td>
              <td className="px-3 py-2 font-mono">{row.hill_slope.toFixed(2)}</td>
              <td
                className={cn(
                  "px-3 py-2 font-mono",
                  row.r_squared === bestR2 && "text-success font-semibold",
                )}
              >
                {row.r_squared.toFixed(3)}
              </td>
              <td className="px-3 py-2">
                {row.curve_class ? (
                  <Badge variant="outline" className="text-xs">
                    {CURVE_CLASS_LABELS[row.curve_class] ?? row.curve_class}
                  </Badge>
                ) : (
                  "--"
                )}
              </td>
              <td className="px-3 py-2 font-mono">{row.top.toFixed(1)}</td>
              <td className="px-3 py-2 font-mono">{row.bottom.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Build ComparisonRow[] from DoseResponseCurve[] + registration labels */
export function buildComparisonRows(
  curves: DoseResponseCurve[],
  labelMap: Map<string, { label: string; batch?: string | null }>,
): ComparisonRow[] {
  const byMolecule = new Map<string, DoseResponseCurve>();
  for (const c of curves) {
    const existing = byMolecule.get(c.molecule_id);
    if (!existing || c.r_squared > existing.r_squared) {
      byMolecule.set(c.molecule_id, c);
    }
  }

  let idx = 0;
  const rows: ComparisonRow[] = [];
  for (const [molId, curve] of byMolecule) {
    const info = labelMap.get(molId);
    rows.push({
      label: info?.label ?? shortId(molId),
      batch: info?.batch,
      color: TRACE_COLORS[idx % TRACE_COLORS.length],
      curve_type: curve.curve_type,
      fitted_value: curve.fitted_value,
      fitted_unit: curve.fitted_unit,
      hill_slope: curve.hill_slope,
      r_squared: curve.r_squared,
      curve_class: (curve.curve_class as CurveClass | null) ?? null,
      top: curve.top,
      bottom: curve.bottom,
    });
    idx++;
  }
  return rows;
}
