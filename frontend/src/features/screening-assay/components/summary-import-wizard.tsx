"use client";

import { AlertCircle, CheckCircle2, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useRef } from "react";

import { CsvDropzone } from "@/shared/components/csv-dropzone";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { WizardStepIndicator } from "@/shared/components/wizard-step-indicator";
import { cn } from "@/shared/lib/utils";
import type {
  SummaryImportResponse,
  SummaryPreviewResponse,
  SummaryResolveResponse,
  SummaryRole,
} from "../hooks/use-summary-import";
import { useSummaryImportWizard } from "../hooks/use-summary-import-wizard";
import type { SummaryMappingDraft } from "../lib/summary-import-mapping";

// Summary import recognizes only these four roles — no Well / Plate /
// Concentration (those are plate-import concepts). Compound/Batch ref plus
// one or more readout columns is the entire mapping surface.
const ROLE_OPTIONS: Array<{ value: SummaryRole; label: string }> = [
  { value: "compound_ref", label: "Compound Ref" },
  { value: "batch_ref", label: "Batch Ref" },
  { value: "readout", label: "Readout" },
  { value: "ignore", label: "Ignore" },
];

interface SummaryImportWizardProps {
  runId: string;
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function confidenceBadgeClass(c: string): string {
  switch (c) {
    case "high":
      return "bg-green-500/10 text-green-400 border-green-500/30";
    case "medium":
      return "bg-amber-500/10 text-amber-400 border-amber-500/30";
    default:
      return "bg-red-500/10 text-red-400 border-red-500/30";
  }
}

function confidenceLabel(c: string): string {
  return c === "high" ? "High" : c === "medium" ? "Medium" : "Low";
}

// ─── Main component ───────────────────────────────────────────────────────────

export function SummaryImportWizard({
  runId,
  protocolId,
  open,
  onOpenChange,
}: SummaryImportWizardProps) {
  const {
    step,
    file,
    preview,
    draft,
    resolvePreview,
    result,
    readoutDefOptions,
    canContinueMapping,
    canImport,
    isPreviewing,
    isResolving,
    isImporting,
    setStep,
    handleOpenChange,
    handleFile,
    setRole,
    setReadoutDef,
    handleContinueToPreview,
    handleImport,
  } = useSummaryImportWizard({ runId, protocolId, open, onOpenChange });

  // The footer "Choose file" button opens the dropzone's native file picker.
  const openPickerRef = useRef<(() => void) | null>(null);
  const handleOpenReady = useCallback((open: () => void) => {
    openPickerRef.current = open;
  }, []);

  // ─── Render ──────────────────────────────────────────────────────────────────

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-[min(95vw,1000px)] max-w-[1000px] sm:max-w-[1000px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import Summary Results</DialogTitle>
          <DialogDescription>
            Upload a wide file of compound/batch ref + endpoint values (e.g. IC50, MIC, Notes). No
            plate or well needed.
          </DialogDescription>
        </DialogHeader>

        <WizardStepIndicator steps={["Upload", "Mapping", "Preview", "Confirm"]} current={step} />

        {step === 1 && (
          <CsvDropzone
            file={file}
            isPending={isPreviewing}
            onFile={handleFile}
            onOpenReady={handleOpenReady}
          />
        )}

        {step === 2 && preview && (
          <MappingStep
            preview={preview}
            draft={draft}
            readoutDefOptions={readoutDefOptions}
            onSetRole={setRole}
            onSetReadoutDef={setReadoutDef}
          />
        )}

        {step === 3 && resolvePreview && <PreviewStep preview={resolvePreview} />}

        {step === 4 && result && <ConfirmStep result={result} />}

        <DialogFooter className="gap-2">
          {step === 2 && (
            <Button variant="ghost" onClick={() => setStep(1)} disabled={isResolving}>
              <ChevronLeft className="h-4 w-4" /> Back
            </Button>
          )}
          {step === 3 && (
            <Button variant="ghost" onClick={() => setStep(2)} disabled={isImporting}>
              <ChevronLeft className="h-4 w-4" /> Back
            </Button>
          )}
          {step === 1 && (
            <Button onClick={() => openPickerRef.current?.()} disabled={isPreviewing}>
              Choose file
            </Button>
          )}
          {step === 2 && (
            <Button onClick={handleContinueToPreview} disabled={!canContinueMapping || isResolving}>
              {isResolving ? "Resolving…" : "Continue"}
              {!isResolving && <ChevronRight className="h-4 w-4" />}
            </Button>
          )}
          {step === 3 && (
            <Button onClick={handleImport} disabled={!canImport || isImporting}>
              {isImporting ? "Importing…" : "Import"}
              {!isImporting && <ChevronRight className="h-4 w-4" />}
            </Button>
          )}
          {step === 4 && <Button onClick={() => handleOpenChange(false)}>Done</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Step 2 — Map ────────────────────────────────────────────────────────────

function MappingStep({
  preview,
  draft,
  readoutDefOptions,
  onSetRole,
  onSetReadoutDef,
}: {
  preview: SummaryPreviewResponse;
  draft: SummaryMappingDraft;
  readoutDefOptions: { id: string; name: string }[];
  onSetRole: (header: string, role: SummaryRole) => void;
  onSetReadoutDef: (header: string, defId: string) => void;
}) {
  const sampleRows = preview.sample_rows.slice(0, 5);
  return (
    <div className="space-y-4 py-2">
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr className="border-b">
              <th className="px-3 py-2 text-left font-medium">Header</th>
              <th className="px-3 py-2 text-left font-medium">Role</th>
              <th className="px-3 py-2 text-left font-medium">Confidence</th>
              <th className="px-3 py-2 text-left font-medium">Readout def</th>
            </tr>
          </thead>
          <tbody>
            {preview.suggestions.map((s) => {
              const role = draft.roles[s.header] ?? "ignore";
              return (
                <tr key={s.header} className="border-b last:border-b-0">
                  <td className="px-3 py-2 font-mono">{s.header}</td>
                  <td className="px-3 py-2">
                    <Select
                      value={role}
                      onValueChange={(v) => onSetRole(s.header, v as SummaryRole)}
                    >
                      <SelectTrigger className="h-8 w-44">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ROLE_OPTIONS.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={confidenceBadgeClass(s.confidence)}>
                      {confidenceLabel(s.confidence)}
                    </Badge>
                    {s.note && <span className="ml-2 text-xs text-muted-foreground">{s.note}</span>}
                  </td>
                  <td className="px-3 py-2">
                    {role === "readout" ? (
                      <Select
                        value={draft.readoutDefByHeader[s.header] ?? ""}
                        onValueChange={(v) => onSetReadoutDef(s.header, v)}
                      >
                        <SelectTrigger className="h-8 w-56">
                          <SelectValue placeholder="Select readout…" />
                        </SelectTrigger>
                        <SelectContent>
                          {readoutDefOptions.map((rd) => (
                            <SelectItem key={rd.id} value={rd.id}>
                              {rd.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {sampleRows.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Sample rows</p>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="border-b">
                  {preview.headers.map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium font-mono">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sampleRows.map((row, i) => (
                  <tr
                    key={`${preview.headers.map((h) => row[h]).join("|")}-${i}`}
                    className="border-b last:border-b-0"
                  >
                    {preview.headers.map((h) => (
                      <td key={h} className="px-3 py-2 font-mono text-xs">
                        {row[h] ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Step 3 — Preview (dry-run forecast) ─────────────────────────────────────

function UnmatchedRefsCard({
  count,
  refs,
  title,
  help,
}: {
  count: number;
  refs: string[];
  title: string;
  help: string;
}) {
  const shown = refs.slice(0, 20);
  const extra = refs.length - shown.length;
  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
      <div className="mb-1 flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
        <AlertCircle className="h-4 w-4" />
        {count} {title}
      </div>
      <p className="text-xs text-muted-foreground">{help}</p>
      <p className="mt-2 break-words font-mono text-xs">
        {shown.join(", ")}
        {extra > 0 && ` … +${extra} more`}
      </p>
    </div>
  );
}

function PreviewStep({ preview }: { preview: SummaryResolveResponse }) {
  const unmatchedCompounds = preview.unmatched_compound_refs ?? [];
  const unmatchedBatches = preview.unmatched_batch_refs ?? [];
  const errors = preview.errors ?? [];
  const willWrite = preview.values_to_insert + preview.values_to_update;
  const shownErrors = errors.slice(0, 20);

  return (
    <div className="space-y-4 py-2">
      {/* Compound match summary */}
      <div className="flex items-center gap-2 rounded-md border p-3 text-sm">
        <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/30">
          {preview.matched_compound_count} matched
        </Badge>
        <span className="text-muted-foreground">
          compound{preview.matched_compound_count === 1 ? "" : "s"} matched across{" "}
          {preview.total_rows} row{preview.total_rows === 1 ? "" : "s"}
        </span>
      </div>

      {unmatchedCompounds.length > 0 && (
        <UnmatchedRefsCard
          count={unmatchedCompounds.length}
          refs={unmatchedCompounds}
          title={`unmatched compound ref${unmatchedCompounds.length === 1 ? "" : "s"}`}
          help="No molecule matches these identifiers. Their rows will be skipped. Register the compounds first if they should be included."
        />
      )}

      {unmatchedBatches.length > 0 && (
        <UnmatchedRefsCard
          count={unmatchedBatches.length}
          refs={unmatchedBatches}
          title={`unmatched batch ref${unmatchedBatches.length === 1 ? "" : "s"}`}
          help="No batch matches these identifiers. Their rows will be skipped. Register the batches first if they should be included."
        />
      )}

      {/* Value forecast */}
      <div className="grid grid-cols-3 gap-3">
        <ResultCard
          label="New values"
          value={preview.values_to_insert}
          accent={preview.values_to_insert > 0 ? "ok" : undefined}
        />
        <ResultCard
          label="Overwrites"
          value={preview.values_to_update}
          accent={preview.values_to_update > 0 ? "warn" : undefined}
        />
        <ResultCard
          label="Rows skipped"
          value={preview.rows_skipped}
          accent={preview.rows_skipped > 0 ? "warn" : undefined}
        />
      </div>

      {willWrite === 0 && (
        <p className="text-xs text-muted-foreground">
          Nothing to import — check your compound column mapping.
        </p>
      )}

      {errors.length > 0 && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <div className="mb-1 flex items-center gap-2 font-medium text-destructive">
            <AlertCircle className="h-4 w-4" />
            {errors.length} row error{errors.length === 1 ? "" : "s"}
          </div>
          <ul className="ml-2 mt-2 space-y-1 font-mono text-xs">
            {shownErrors.map((e, i) => (
              <li key={`${e.row}-${i}`}>
                <span className="text-foreground">Row {e.row}</span>
                <span className="ml-2 text-muted-foreground">— {e.error}</span>
              </li>
            ))}
            {errors.length > shownErrors.length && (
              <li className="text-muted-foreground">
                …and {errors.length - shownErrors.length} more
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Step 4 — Confirm ────────────────────────────────────────────────────────

function ConfirmStep({ result }: { result: SummaryImportResponse }) {
  const errors = result.errors ?? [];
  return (
    <div className="space-y-4 py-2">
      <div className="flex items-start gap-2 rounded-md border border-green-500/30 bg-green-500/5 p-3 text-sm">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-400" />
        <div className="text-green-300">
          <p className="font-medium">Import complete</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {result.values_inserted} inserted · {result.values_updated} updated ·{" "}
            {result.rows_skipped} skipped · {result.rows_processed} rows processed
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <ResultCard label="Inserted" value={result.values_inserted} accent="ok" />
        <ResultCard label="Updated" value={result.values_updated} accent="ok" />
        <ResultCard
          label="Skipped"
          value={result.rows_skipped}
          accent={result.rows_skipped > 0 ? "warn" : undefined}
        />
        <ResultCard label="Rows processed" value={result.rows_processed} />
      </div>

      {errors.length > 0 && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <div className="mb-1 flex items-center gap-2 font-medium text-destructive">
            <AlertCircle className="h-4 w-4" />
            {errors.length} row error{errors.length === 1 ? "" : "s"}
          </div>
          <ul className="ml-2 mt-2 space-y-1 font-mono text-xs">
            {errors.map((e, i) => (
              <li key={`${e.row}-${i}`}>
                <span className="text-foreground">Row {e.row}</span>
                <span className="ml-2 text-muted-foreground">— {e.error}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ResultCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: "ok" | "warn";
}) {
  return (
    <div
      className={cn(
        "rounded-md border p-3",
        accent === "warn" && "border-amber-500/30 bg-amber-500/5",
        accent === "ok" && value > 0 && "border-green-500/30 bg-green-500/5",
      )}
    >
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}
