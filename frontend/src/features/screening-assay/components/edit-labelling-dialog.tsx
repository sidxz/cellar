"use client";

import { useId, useMemo, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { ApiError } from "@/shared/lib/api/custom-instance";
import { showSuccess, showWarning } from "@/shared/lib/toast";
import { apiReason } from "../hooks/use-instrument-import-wizard";
import { useRelabelPositions } from "../hooks/use-relabel-positions";
import {
  type LabellingRow,
  compoundWithoutBatch,
  rowsProblem,
  setRoleForRows,
  withoutBatchLine,
} from "../lib/labelling-rows";
import {
  buildPositionEdits,
  calculatedLockedReason,
  reasonRequired,
  rowsFromPositions,
} from "../lib/position-edits";
import type { Run, RunCurves, WellType } from "../types";
import { LabellingTable, Notice } from "./labelling-table";

type Position = RunCurves["positions"][number];

/** The API names the refusal of an edit made from values someone else changed since. */
function isStaleEdit(body: unknown): boolean {
  return (body as { error?: unknown } | null)?.error === "StaleEditError";
}
type EditableRun = Pick<Run, "id" | "status" | "is_locked">;

interface EditLabellingDialogProps {
  run: EditableRun;
  positions: readonly Position[];
  doseUnit: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onReload: () => Promise<unknown>;
}

/** The import wizard's labelling table over the run's current positions.
 *  Nothing is sent until Save. */
export function EditLabellingDialog({ open, onOpenChange, ...rest }: EditLabellingDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Header and footer stay put; only the labelling table scrolls. */}
      <DialogContent className="flex max-h-[90vh] w-[min(95vw,1280px)] max-w-[1280px] flex-col overflow-hidden sm:max-w-[1280px]">
        <DialogHeader>
          <DialogTitle>Edit labelling</DialogTitle>
          <DialogDescription>
            Change what was in each position. Nothing is saved until you press Save.
          </DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so each opening starts from the run's values. */}
        {open && <EditLabellingBody {...rest} onOpenChange={onOpenChange} />}
      </DialogContent>
    </Dialog>
  );
}

function EditLabellingBody({
  run,
  positions,
  doseUnit,
  onOpenChange,
  onReload,
}: Omit<EditLabellingDialogProps, "open">) {
  // Null until the first edit: the table shows the positions as they are. The
  // first edit freezes them as the values the save says it started from.
  const [draft, setDraft] = useState<{
    base: readonly Position[];
    rows: LabellingRow[];
  } | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<{ message: string; stale: boolean } | null>(null);
  const [reloading, setReloading] = useState(false);
  const relabel = useRelabelPositions(run.id);
  const reasonId = useId();

  const base = draft?.base ?? positions;
  const rows = useMemo(() => draft?.rows ?? rowsFromPositions(positions), [draft, positions]);
  const edits = useMemo(() => buildPositionEdits(base, rows), [base, rows]);
  const problem = rowsProblem(rows);
  const needsReason = reasonRequired(run);
  const withoutBatch = withoutBatchLine(compoundWithoutBatch(rows));
  const canSave =
    edits.length > 0 &&
    problem === null &&
    (!needsReason || reason.trim() !== "") &&
    !relabel.isPending &&
    !reloading;

  const edit = (change: (rows: LabellingRow[]) => LabellingRow[]) =>
    setDraft((d) => ({
      base: d?.base ?? positions,
      rows: change(d?.rows ?? rowsFromPositions(positions)),
    }));

  const save = () => {
    setError(null);
    relabel.mutate(
      { positions: edits, ...(needsReason ? { reason: reason.trim() } : {}) },
      {
        onSuccess: (result) => {
          showSuccess("Labelling saved");
          if (result.compute_warning) {
            showWarning(
              `The labelling was saved, but the calculations were not rebuilt: ${result.compute_warning}. Press Recompute on the run to rebuild them.`,
            );
          }
          onOpenChange(false);
        },
        onError: (e) =>
          setError({
            message: apiReason(e),
            // Only a stale edit is helped by reloading; other refusals keep the edits.
            stale: e instanceof ApiError && isStaleEdit(e.body),
          }),
      },
    );
  };

  // Discards the edits: the table follows the freshly loaded positions.
  const reload = async () => {
    setReloading(true);
    try {
      await onReload();
    } finally {
      setReloading(false);
    }
    setDraft(null);
    setError(null);
  };

  return (
    <>
      <div className="flex min-h-0 min-w-0 flex-col gap-3">
        <LabellingTable
          rows={rows}
          runId={run.id}
          doseUnit={doseUnit}
          onUpdate={(key, patch) =>
            edit((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)))
          }
          onSetRole={(keys: ReadonlySet<string>, wellType: WellType) =>
            edit((rs) => setRoleForRows(rs, keys, wellType))
          }
          onReplaceRows={(filled) => edit(() => filled)}
          templateName="labelling-template.csv"
          showUse={false}
          calculatedLocked={calculatedLockedReason(run)}
          problem={problem}
        />
        {needsReason && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={reasonId}>Reason</Label>
            <Input
              id={reasonId}
              required
              maxLength={500}
              placeholder="Why the labelling of a completed or approved run is changing"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
        )}
        {error && (
          <Notice tone="bad">
            <div className="flex flex-wrap items-center gap-3">
              <span>{error.message}</span>
              {error.stale && (
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  disabled={reloading}
                  onClick={reload}
                >
                  Reload
                </Button>
              )}
            </div>
          </Notice>
        )}
      </div>

      <DialogFooter className="items-center gap-2">
        <div className="flex flex-col text-right text-sm text-muted-foreground sm:mr-2">
          {edits.length > 0 && (
            <span>
              {edits.length} position{edits.length === 1 ? "" : "s"} changed
            </span>
          )}
          {withoutBatch && (
            <span className="text-amber-600 dark:text-amber-400">{withoutBatch}</span>
          )}
        </div>
        <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={relabel.isPending}>
          Cancel
        </Button>
        <Button onClick={save} disabled={!canSave}>
          {relabel.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </>
  );
}
