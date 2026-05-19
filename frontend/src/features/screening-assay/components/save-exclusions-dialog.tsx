"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ExclusionReason =
  | "outlier"
  | "instrument_artifact"
  | "concentration_error"
  | "contamination"
  | "qc_failure"
  | "other";

interface ReasonOption {
  value: ExclusionReason;
  label: string;
}

// Order matches the spec; user-facing labels (snake_case never shown).
// `auto_3sigma` is intentionally excluded — it's only valid for system-emitted
// suggestions, never chemist-driven saves.
const REASON_OPTIONS: ReasonOption[] = [
  { value: "outlier", label: "Outlier" },
  { value: "instrument_artifact", label: "Instrument artifact" },
  { value: "concentration_error", label: "Concentration error" },
  { value: "contamination", label: "Contamination" },
  { value: "qc_failure", label: "QC failure" },
  { value: "other", label: "Other" },
];

interface SaveExclusionsDialogProps {
  open: boolean;
  onClose: () => void;
  onSave: (input: {
    reason: ExclusionReason;
    note: string | null;
  }) => void | Promise<void>;
  /** Used in the title + Save button label ("Save 2 changes"). */
  dirtyCount: number;
  /** When true, locks the form to prevent double-submits. */
  isSaving?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SaveExclusionsDialog({
  open,
  onClose,
  onSave,
  dirtyCount,
  isSaving = false,
}: SaveExclusionsDialogProps) {
  const [reason, setReason] = useState<ExclusionReason | null>(null);
  const [note, setNote] = useState("");

  // Reset state whenever the dialog re-opens — stale picks shouldn't persist.
  useEffect(() => {
    if (open) {
      setReason(null);
      setNote("");
    }
  }, [open]);

  const canSave = reason !== null && !isSaving;

  const handleSubmit = () => {
    if (reason === null) return;
    const trimmed = note.trim();
    void onSave({ reason, note: trimmed.length > 0 ? trimmed : null });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !isSaving && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            Save {dirtyCount} exclusion {dirtyCount === 1 ? "change" : "changes"}?
          </DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="save-exclusions-reason">Reason</Label>
            <Select
              value={reason ?? ""}
              onValueChange={(v) => setReason(v as ExclusionReason)}
              disabled={isSaving}
            >
              <SelectTrigger id="save-exclusions-reason">
                <SelectValue placeholder="Select a reason…" />
              </SelectTrigger>
              <SelectContent>
                {REASON_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="save-exclusions-note">Note (optional)</Label>
            <Textarea
              id="save-exclusions-note"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={isSaving}
              placeholder="Anything worth recording for future readers…"
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isSaving}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSave}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save {dirtyCount} {dirtyCount === 1 ? "change" : "changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
