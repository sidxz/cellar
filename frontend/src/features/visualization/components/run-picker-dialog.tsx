"use client";

import { useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import { useRunsByProtocol } from "@/features/screening-assay/hooks/use-runs";
import { StatusBadge } from "@/shared/components/status-badge";
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
import { MAX_ROWS } from "../lib/limits";
import { conditionsText, newestFirst, runLabel } from "../lib/runs";
import { visualizeHref } from "../lib/source-url";

const fmt = (n: number) => n.toLocaleString();

interface RunPickerDialogProps {
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Runs ticked on open; every run when omitted. */
  initialRunIds?: string[];
}

/** Choose which runs of a protocol to load, with each run's well count and a running
 * total against the row cap. Opening navigates to the workbench URL. */
export function RunPickerDialog({
  protocolId,
  open,
  onOpenChange,
  initialRunIds,
}: RunPickerDialogProps) {
  const router = useRouter();
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
  const reason =
    selected.length === 0
      ? "Choose at least one run."
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
  const openWorkbench = () => {
    const runIds = selected.map((r) => r.id);
    router.push(
      visualizeHref({
        kind: "protocol",
        protocolId,
        ...(runIds.length < ordered.length ? { runIds } : {}),
      }),
    );
    onOpenChange(false);
  };

  const allState =
    selected.length === ordered.length ? true : selected.length === 0 ? false : "indeterminate";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Choose runs to visualize</DialogTitle>
          <DialogDescription>{protocol?.name ?? "…"} · each row is one well</DialogDescription>
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
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {run.plate_count || "—"}
                    </td>
                    <td className="max-w-[16rem] truncate px-2 py-1.5 text-muted-foreground">
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
            <span className="text-muted-foreground"> · limit {fmt(MAX_ROWS)}</span>
            {reason && <p className="text-xs text-destructive">{reason}</p>}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={openWorkbench} disabled={reason !== null}>
              Open workbench
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
