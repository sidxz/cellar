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
import { showError, showSuccess } from "@/shared/lib/toast";
import { useResetRunData } from "../hooks/use-run-import";

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

  const handleConfirm = () => {
    reset.mutate(undefined, {
      onSuccess: (out) => {
        showSuccess(
          `Reset run data — ${out.plates_deleted} plates, ${out.wells_deleted} wells, ${out.readouts_deleted} readouts, ${out.curves_deleted} curves removed.`,
        );
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
            This will delete all plates ({plateCount}), wells, readout data, dose-response curves,
            and QC metrics for this run.
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
