"use client";

import { useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import { useRunsByProtocol } from "@/features/screening-assay/hooks/use-runs";
import { StatusBadge } from "@/shared/components/status-badge";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useRunRowCounts } from "../hooks/use-run-row-counts";
import { LEVELS, countsAtLevel } from "../lib/levels";
import { MAX_ROWS } from "../lib/limits";
import { conditionsText, newestFirst, runLabel } from "../lib/runs";
import { visualizeHref } from "../lib/source-url";
import { useOpenView } from "../store/open-view-context";
import type { Level } from "../types";

const fmt = (n: number) => n.toLocaleString();
const NOT_COUNTED = "Batches and Compounds count only completed or approved runs";

interface RunPickerDialogProps {
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Runs ticked on open; every run when omitted. */
  initialRunIds?: string[];
  /** The level the workbench opens at (kept from the one it was opened from). */
  level?: Level;
  /** Called with the chosen runs (undefined = every run) instead of opening the workbench. */
  onConfirm?: (runIds: string[] | undefined) => void;
  confirmLabel?: string;
  /** Where focus goes on close, when not back to what had it on open. */
  onCloseAutoFocus?: (e: Event) => void;
}

/** Choose which runs of a protocol to load, with each run's well count and a running
 * total against the row cap (Wells only). At Batches and Compounds, runs whose status does
 * not count there are marked but stay ticked. Opening navigates to the workbench URL, unless
 * ``onConfirm`` takes the runs. */
export function RunPickerDialog({
  protocolId,
  open,
  onOpenChange,
  initialRunIds,
  level = "wells",
  onConfirm,
  confirmLabel = "Open workbench",
  onCloseAutoFocus,
}: RunPickerDialogProps) {
  const router = useRouter();
  const viewId = useOpenView()?.view.id;
  const nameOf = useMemberNames();
  const { data: protocol } = useProtocol(protocolId);
  const { data: runs, isLoading } = useRunsByProtocol(protocolId);
  const { data: rowCounts } = useRunRowCounts(protocolId);
  const [picked, setPicked] = useState<ReadonlySet<string> | null>(
    initialRunIds ? new Set(initialRunIds) : null,
  );

  const ordered = useMemo(() => newestFirst(runs ?? []), [runs]);
  const chosen = picked ?? new Set(ordered.map((r) => r.id));
  const selected = ordered.filter((r) => chosen.has(r.id));
  const counts = rowCounts?.counts;
  const total = counts ? selected.reduce((n, r) => n + (counts[r.id] ?? 0), 0) : null;
  const wells = level === "wells";
  const counting = selected.filter((r) => countsAtLevel(level, r.status)).length;
  // Above Wells the cap applies to the server's (fewer) aggregated rows, so it checks it.
  const reason =
    selected.length === 0
      ? "Choose at least one run."
      : !wells
        ? null
        : total === null
          ? "Counting wells…"
          : total > MAX_ROWS
            ? `Over the ${fmt(MAX_ROWS)}-row limit — untick some runs.`
            : null;

  const setAll = (on: boolean) => setPicked(new Set(on ? ordered.map((r) => r.id) : []));
  const toggle = (id: string, on: boolean) => {
    const next = new Set(chosen);
    if (on) next.add(id);
    else next.delete(id);
    setPicked(next);
  };
  const submit = () => {
    const ids = selected.map((r) => r.id);
    const runIds = ids.length < ordered.length ? ids : undefined;
    if (onConfirm) onConfirm(runIds);
    else
      router.push(
        visualizeHref({ kind: "protocol", protocolId, ...(runIds && { runIds }) }, level, viewId),
      );
    onOpenChange(false);
  };

  const allState =
    selected.length === ordered.length ? true : selected.length === 0 ? false : "indeterminate";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl" onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>Choose runs to visualize</DialogTitle>
          <DialogDescription>
            {protocol?.name ?? "…"} · {LEVELS[level].caption}
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[50vh] overflow-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-muted/60 text-xs text-muted-foreground">
              <tr className="text-left">
                <th className="w-8 px-2 py-1.5">
                  <Checkbox
                    aria-label="Include all runs"
                    checked={allState}
                    onCheckedChange={(v) => setAll(v === true)}
                    disabled={ordered.length === 0}
                  />
                </th>
                <th className="px-2 py-1.5 font-medium">Run</th>
                <th className="px-2 py-1.5 font-medium">Status</th>
                <th className="px-2 py-1.5 text-right font-medium">Plates</th>
                <th className="px-2 py-1.5 font-medium">Conditions</th>
                <th className="px-2 py-1.5 text-right font-medium">Wells</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={6} className="px-2 py-4 text-center text-muted-foreground">
                    Loading runs…
                  </td>
                </tr>
              )}
              {!isLoading && ordered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-2 py-4 text-center text-muted-foreground">
                    This protocol has no runs yet.
                  </td>
                </tr>
              )}
              {ordered.map((run) => {
                const label = runLabel(run, nameOf);
                return (
                  <tr key={run.id} className="border-t">
                    <td className="px-2 py-1.5">
                      <Checkbox
                        aria-label={`Include ${label}`}
                        checked={chosen.has(run.id)}
                        onCheckedChange={(v) => toggle(run.id, v === true)}
                      />
                    </td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{label}</td>
                    <td className="px-2 py-1.5">
                      {/* Wraps "Not counted" under the status rather than widen the table. */}
                      <div className="flex flex-wrap items-center gap-1">
                        <StatusBadge status={run.status} />
                        {!countsAtLevel(level, run.status) && (
                          <>
                            <Badge variant="warning" title={NOT_COUNTED}>
                              Not counted
                            </Badge>
                            <span className="sr-only">{NOT_COUNTED}</span>
                          </>
                        )}
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {run.plate_count || "—"}
                    </td>
                    <td className="min-w-32 px-2 py-1.5 text-muted-foreground">
                      {conditionsText(run) || "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {counts ? fmt(counts[run.id] ?? 0) : "…"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <DialogFooter className="items-center sm:justify-between">
          <div className="text-sm">
            <span className="font-medium tabular-nums">
              {total === null ? "…" : `${fmt(total)} wells selected`}
            </span>
            {wells ? (
              <span className="text-muted-foreground"> · limit {fmt(MAX_ROWS)}</span>
            ) : (
              <p className="text-xs text-muted-foreground">
                {`${counting} of ${selected.length} chosen runs count at this level`}
              </p>
            )}
            {reason && <p className="text-xs text-destructive">{reason}</p>}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={reason !== null}>
              {confirmLabel}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
