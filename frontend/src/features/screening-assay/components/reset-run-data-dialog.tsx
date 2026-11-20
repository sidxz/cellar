"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { formatCount } from "@/shared/lib/format-number";
import { showError, showSuccess } from "@/shared/lib/toast";
import { usePlateMap } from "../hooks/use-plate-setup";
import { type ResetRunDataResponse, useResetRunData } from "../hooks/use-run-import";

/** What the dialog says will be deleted. A holder that is not a plate has positions, not wells. */
export function resetDamageText(
  holderLabel: string | null,
  plateCount: number,
  hasMeasuredCurves: boolean,
): string {
  return holderLabel !== null
    ? `This will delete the holder (${holderLabel}) and its positions, readout data, dose-response curves${hasMeasuredCurves ? ", traces" : ""} and QC metrics for this run.`
    : `This will delete all plates (${plateCount}), wells, readout data, dose-response curves,${hasMeasuredCurves ? " traces," : ""} and QC metrics for this run.`;
}

/** The toast after a reset: what was removed, in the run's own holder words. */
export function resetDoneText(out: ResetRunDataResponse, isHolder: boolean): string {
  const measured =
    out.measured_curves_deleted > 0 ? `, ${formatCount(out.measured_curves_deleted, "trace")}` : "";
  return isHolder
    ? `Reset run data — ${formatCount(out.wells_deleted, "position")}, ${formatCount(out.readouts_deleted, "readout")}, ${formatCount(out.curves_deleted, "dose-response curve")}${measured} removed.`
    : `Reset run data — ${out.plates_deleted} plates, ${out.wells_deleted} wells, ${out.readouts_deleted} readouts, ${out.curves_deleted} curves${measured} removed.`;
}

interface ResetRunDataDialogProps {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Counts shown in the damage report. */
  plateCount: number;
}

export function ResetRunDataDialog({
  runId,
  open,
  onOpenChange,
  plateCount,
}: ResetRunDataDialogProps) {
  const reset = useResetRunData(runId);
  // Holder wording comes from the API; a holder that is not a plate has positions, not wells.
  const { data: plateMap } = usePlateMap(runId);
  const holder = plateMap?.plates.find((p) => p.holder_kind !== "plate");
  const hasMeasuredCurves = !!plateMap?.has_measured_curves;

  const handleConfirm = () => {
    reset.mutate(undefined, {
      onSuccess: (out) => {
        showSuccess(resetDoneText(out, !!holder));
        onOpenChange(false);
      },
      onError: () => {
        showError("Failed to reset run data");
      },
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Reset run data?</AlertDialogTitle>
          <AlertDialogDescription>
            {resetDamageText(holder ? holder.holder_label : null, plateCount, hasMeasuredCurves)}
            <br />
            <br />
            The run itself, its metadata, and any uploaded files will be kept. This cannot be
            undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={reset.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {reset.isPending ? "Resetting…" : "Reset Run Data"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
