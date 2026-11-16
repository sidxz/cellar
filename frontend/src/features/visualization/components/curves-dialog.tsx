"use client";

import { CurveClassBadge } from "@/features/screening-assay/components/curve-class-badge";
import { useCompoundCurves } from "@/features/screening-assay/hooks/use-compound-curves";
import { useRunsByProtocol } from "@/features/screening-assay/hooks/use-runs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { formatCount, formatMeasurementValue } from "@/shared/lib/format-number";
import { Plot } from "@/shared/lib/plotly";
import { DoseResponseChartView } from "@structflo/components/dose-response";
import { useMemo } from "react";
import { column } from "../lib/dataset";
import { runLabel } from "../lib/runs";
import type { Dataset } from "../types";

/** Whose curves the dialog shows: one compound's fits of one dose-response readout in some
 * runs (and one batch, when the row is one). */
export interface CurvesTarget {
  protocolId: string;
  readoutDefinitionId: string;
  moleculeId: string;
  compound: string;
  /** The value column's label, e.g. "Enzyme · IC50". */
  readout: string;
  runIds: string[];
  batchId: string | null;
}

/** The curves behind dose-response value ``key`` of row ``i``: a Runs row's own run, else
 * ``runIds`` (the source runs that count at the level). */
export function curvesTarget(
  ds: Dataset,
  key: string,
  i: number,
  runIds: string[],
): CurvesTarget | null {
  const c = column(ds, key);
  const moleculeId = ds.values.molecule_id?.[i];
  const { protocol_id: protocolId, readout_definition_id: readoutDefinitionId } =
    c?.provenance ?? {};
  if (!c || !protocolId || !readoutDefinitionId || typeof moleculeId !== "string") return null;
  const batchId = ds.values.batch_id?.[i];
  return {
    protocolId,
    readoutDefinitionId,
    moleculeId,
    compound: String(ds.values.compound?.[i] ?? "this compound"),
    readout: c.label,
    // A Runs row id leads with its run id.
    runIds: ds.level === "runs" ? [ds.row_ids[i].split(":")[0]] : runIds,
    batchId: typeof batchId === "string" ? batchId : null,
  };
}

/** One compound's fitted curves in the chosen runs, drawn by the shared read-only chart, with
 * a table of run (date · operator), batch, fitted value and class. */
export function CurvesDialog({
  protocolId,
  readoutDefinitionId,
  moleculeId,
  compound,
  readout,
  runIds,
  batchId,
  open,
  onOpenChange,
}: CurvesTarget & { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { data, isLoading } = useCompoundCurves(protocolId, open ? moleculeId : null);
  const { data: runs } = useRunsByProtocol(protocolId);
  const nameOf = useMemberNames();

  const curves = useMemo(() => {
    const byId = new Map((runs ?? []).map((r) => [r.id, r]));
    const chosen = new Set(runIds);
    return (data ?? [])
      .filter(
        (c) =>
          chosen.has(c.run_id) &&
          c.readout_definition_id === readoutDefinitionId &&
          (!batchId || c.batch_id === batchId),
      )
      .map((c) => {
        const run = byId.get(c.run_id);
        return { ...c, label: run ? runLabel(run, nameOf) : "Run", date: run?.run_date ?? "" };
      })
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [data, runs, runIds, readoutDefinitionId, batchId, nameOf]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* The chart's summary cards sit below the plot, so the dialog scrolls. */}
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {compound} · {readout}
          </DialogTitle>
          <DialogDescription>
            {isLoading ? "Loading curves…" : formatCount(curves.length, "curve")}
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <Skeleton className="h-[300px] w-full" />
        ) : curves.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No curves for {compound} in the chosen runs.
          </p>
        ) : (
          <>
            <DoseResponseChartView curves={curves} plot={Plot} />
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="px-2 py-1.5 font-medium">Run</th>
                  <th className="px-2 py-1.5 font-medium">Batch</th>
                  <th className="px-2 py-1.5 text-right font-medium">Fitted value</th>
                  <th className="px-2 py-1.5 font-medium">Class</th>
                </tr>
              </thead>
              <tbody>
                {curves.map((c) => (
                  <tr key={c.id} className="border-b last:border-0">
                    <td className="px-2 py-1.5">{c.label}</td>
                    <td className="px-2 py-1.5 text-muted-foreground">{c.batch_number ?? "—"}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {c.curve_class === "inactive"
                        ? "—"
                        : `${formatMeasurementValue(c.fitted_value, 4)} ${c.fitted_unit}`}
                    </td>
                    <td className="px-2 py-1.5">
                      <CurveClassBadge curveClass={c.curve_class} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
