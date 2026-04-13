"use client";

import { useCallback, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Upload } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useParsePlateMap, useSetUpPlate } from "../hooks/use-plate-setup";
import type { CompoundAssignment, ParsedPlateMap } from "../types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface PlateSetupDialogProps {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ─── Step 1: Upload ───────────────────────────────────────────────────────────

interface UploadStepProps {
  runId: string;
  onParsed: (result: ParsedPlateMap, file: File) => void;
}

function UploadStep({ runId, onParsed }: UploadStepProps) {
  const parse = useParsePlateMap(runId);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  const handleFile = useCallback(
    (file: File) => {
      setFileName(file.name);
      parse.mutate(file, {
        onSuccess: (result) => onParsed(result, file),
      });
    },
    [parse, onParsed]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && (file.name.endsWith(".csv") || file.name.endsWith(".txt"))) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  return (
    <div className="space-y-4">
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
        onClick={() => fileInputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 transition-colors ${
          isDragging
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50"
        }`}
      >
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {parse.isPending
            ? "Parsing..."
            : fileName
            ? fileName
            : "Drop a plate map CSV here or click to browse"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Expected columns: compound, well_positions (comma-separated, e.g. A1;A2)
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.txt"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </div>

      {parse.isError && (
        <div className="flex items-start gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Failed to parse file. Check the format and try again.</span>
        </div>
      )}
    </div>
  );
}

// ─── Step 2: Confirm ──────────────────────────────────────────────────────────

interface ConfirmStepProps {
  runId: string;
  parsed: ParsedPlateMap;
  onSuccess: () => void;
  onBack: () => void;
}

function ConfirmStep({ runId, parsed, onSuccess, onBack }: ConfirmStepProps) {
  const setup = useSetUpPlate(runId);

  const handleSetUp = () => {
    setup.mutate(
      { compound_assignments: parsed.assignments },
      {
        onSuccess: () => {
          onSuccess();
        },
      }
    );
  };

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="rounded-md bg-muted/30 px-4 py-3 text-sm">
        <p>
          <span className="font-medium">{parsed.row_count}</span> rows parsed,{" "}
          <span className="font-medium">{parsed.assignments.length}</span> compound
          {parsed.assignments.length !== 1 ? "s" : ""} found.
          {parsed.unresolved.length > 0 && (
            <span className="ml-1 text-yellow-400">
              {parsed.unresolved.length} unresolved.
            </span>
          )}
        </p>
      </div>

      {/* Unresolved warning */}
      {parsed.unresolved.length > 0 && (
        <div className="rounded-md bg-yellow-500/10 px-3 py-2 text-xs text-yellow-400">
          <p className="font-medium mb-1">Unresolved compounds (will be skipped):</p>
          <ul className="list-inside list-disc space-y-0.5">
            {parsed.unresolved.slice(0, 10).map((ref) => (
              <li key={ref}>{ref}</li>
            ))}
            {parsed.unresolved.length > 10 && (
              <li>...and {parsed.unresolved.length - 10} more</li>
            )}
          </ul>
        </div>
      )}

      {/* Assignment table */}
      <div className="max-h-60 overflow-y-auto rounded-md border">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-muted/80">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Compound Ref</th>
              <th className="px-3 py-2 text-left font-medium">Batch</th>
              <th className="px-3 py-2 text-left font-medium">Wells</th>
            </tr>
          </thead>
          <tbody>
            {parsed.assignments.map((a: CompoundAssignment, i) => (
              <tr key={i} className="border-t">
                <td className="px-3 py-1.5 font-mono">{a.molecule_ref}</td>
                <td className="px-3 py-1.5 font-mono text-muted-foreground">
                  {a.batch_ref ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-muted-foreground">
                  {a.well_positions.slice(0, 6).join(", ")}
                  {a.well_positions.length > 6
                    ? ` +${a.well_positions.length - 6} more`
                    : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Setup result */}
      {setup.isSuccess && setup.data && (
        <div className="flex items-start gap-2 rounded-md bg-green-500/10 p-3 text-sm text-green-400">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Plate set up: {setup.data.wells_created} wells created,{" "}
            {setup.data.compounds_assigned} compounds assigned.
            {setup.data.unresolved.length > 0 && (
              <span className="ml-1 text-yellow-400">
                {setup.data.unresolved.length} unresolved.
              </span>
            )}
          </span>
        </div>
      )}

      {setup.isError && (
        <div className="flex items-start gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Failed to set up plate. Please try again.</span>
        </div>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={onBack} disabled={setup.isPending}>
          Back
        </Button>
        <Button
          onClick={handleSetUp}
          disabled={
            setup.isPending || parsed.assignments.length === 0 || setup.isSuccess
          }
        >
          {setup.isPending ? "Setting Up..." : "Set Up Plate"}
        </Button>
      </DialogFooter>
    </div>
  );
}

// ─── Main Dialog ──────────────────────────────────────────────────────────────

export function PlateSetupDialog({
  runId,
  open,
  onOpenChange,
}: PlateSetupDialogProps) {
  const [step, setStep] = useState<"upload" | "confirm">("upload");
  const [parsed, setParsed] = useState<ParsedPlateMap | null>(null);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setStep("upload");
      setParsed(null);
    }
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {step === "upload" ? "Upload Plate Map" : "Confirm Plate Setup"}
          </DialogTitle>
          <DialogDescription>
            {step === "upload"
              ? "Upload a CSV mapping compounds to well positions."
              : "Review the parsed assignments before committing."}
          </DialogDescription>
        </DialogHeader>

        <div className="py-2">
          {step === "upload" && (
            <UploadStep
              runId={runId}
              onParsed={(result) => {
                setParsed(result);
                setStep("confirm");
              }}
            />
          )}

          {step === "confirm" && parsed && (
            <ConfirmStep
              runId={runId}
              parsed={parsed}
              onBack={() => setStep("upload")}
              onSuccess={() => handleOpenChange(false)}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
