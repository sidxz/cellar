"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Upload,
} from "lucide-react";

import {
  type ImportConfidence,
  type ImportRole,
  type PreviewRunFileResponse,
  type RunImportTemplate,
} from "../hooks/use-run-import";
import { useRunImportWizard } from "../hooks/use-run-import-wizard";
import type { MappingDraft } from "../lib/run-import-mapping";
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
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { formatDate } from "@/shared/lib/format-date";
import { cn } from "@/shared/lib/utils";

const ROLE_OPTIONS: Array<{ value: ImportRole | "ignore"; label: string }> = [
  { value: "well", label: "Well" },
  { value: "plate_name", label: "Plate Name" },
  { value: "concentration", label: "Concentration" },
  { value: "batch_ref", label: "Batch Ref" },
  { value: "compound_ref", label: "Compound Ref" },
  { value: "readout", label: "Readout" },
  { value: "ignore", label: "Ignore" },
];

interface RunImportWizardProps {
  runId: string;
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function confidenceBadgeClass(c: ImportConfidence): string {
  switch (c) {
    case "high":
      return "bg-green-500/10 text-green-400 border-green-500/30";
    case "medium":
      return "bg-amber-500/10 text-amber-400 border-amber-500/30";
    case "low":
      return "bg-red-500/10 text-red-400 border-red-500/30";
  }
}

function confidenceLabel(c: ImportConfidence): string {
  return c === "high" ? "High" : c === "medium" ? "Medium" : "Low";
}

// ─── Main component ───────────────────────────────────────────────────────────

export function RunImportWizard({
  runId,
  protocolId,
  open,
  onOpenChange,
}: RunImportWizardProps) {
  const {
    step,
    setStep,
    file,
    preview,
    draft,
    setDraft,
    appliedTemplate,
    setAppliedTemplate,
    saveAsTemplate,
    setSaveAsTemplate,
    templateName,
    setTemplateName,
    compoundPicks,
    setCompoundPicks,
    isDragging,
    setIsDragging,
    fileInputRef,
    previewMutation,
    repreviewMutation,
    importMutation,
    createTemplate,
    readoutDefs,
    protocol,
    lowConfidenceHeaders,
    canContinueStep2,
    handleOpenChange,
    handleFile,
    handleDrop,
    handleSetRole,
    handleSetReadoutDef,
    handleContinueFromMapping,
    handleSubmit,
  } = useRunImportWizard({ runId, protocolId, onClose: () => onOpenChange(false) });

  // ─── Render ──────────────────────────────────────────────────────────────────

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-[min(95vw,1200px)] max-w-[1200px] sm:max-w-[1200px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import Run File</DialogTitle>
          <DialogDescription>
            Upload a long-format CSV or XLSX with plate name, well, concentration,
            batch ref, and readout values.
          </DialogDescription>
        </DialogHeader>

        <StepIndicator step={step} />

        {step === 1 && (
          <UploadStep
            isDragging={isDragging}
            file={file}
            isPending={previewMutation.isPending}
            onFile={handleFile}
            onDrop={handleDrop}
            setIsDragging={setIsDragging}
            inputRef={fileInputRef}
          />
        )}

        {step === 2 && preview && (
          <MappingStep
            preview={preview}
            draft={draft}
            readoutDefs={readoutDefs}
            doseUnit={protocol?.dose_unit ?? "uM"}
            appliedTemplate={appliedTemplate}
            onClearTemplate={() => setAppliedTemplate(null)}
            onSetRole={handleSetRole}
            onSetReadoutDef={handleSetReadoutDef}
            onAckLowConfidence={(v) =>
              setDraft((d) => ({ ...d, acknowledgedLowConfidence: v }))
            }
            lowConfidenceHeaders={lowConfidenceHeaders}
          />
        )}

        {step === 3 && preview && (
          <PreviewStep
            preview={preview}
            compoundPicks={compoundPicks}
            onCompoundPick={(moleculeId, batchId) =>
              setCompoundPicks((p) => ({ ...p, [moleculeId]: batchId }))
            }
          />
        )}

        {step === 4 && importMutation.data && (
          <ConfirmStep
            result={importMutation.data}
            saveAsTemplate={saveAsTemplate}
            templateName={templateName}
            onSaveAsTemplate={setSaveAsTemplate}
            onTemplateName={setTemplateName}
            templateAlreadySaved={createTemplate.isSuccess}
          />
        )}

        <DialogFooter className="gap-2">
          {step > 1 && step < 4 && (
            <Button
              variant="ghost"
              onClick={() => setStep((step - 1) as 1 | 2 | 3 | 4)}
              disabled={importMutation.isPending}
            >
              <ChevronLeft className="h-4 w-4" /> Back
            </Button>
          )}
          {step === 1 && (
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={previewMutation.isPending}
            >
              Choose file
            </Button>
          )}
          {step === 2 && (
            <Button
              onClick={handleContinueFromMapping}
              disabled={!canContinueStep2 || repreviewMutation.isPending}
            >
              {repreviewMutation.isPending ? "Resolving…" : "Continue"}
              {!repreviewMutation.isPending && <ChevronRight className="h-4 w-4" />}
            </Button>
          )}
          {step === 3 && (
            <Button
              onClick={handleSubmit}
              disabled={
                importMutation.isPending ||
                (preview?.validation_errors.length ?? 0) > 0 ||
                (preview?.row_conflicts.length ?? 0) > 0 ||
                (preview?.ambiguous_compounds ?? []).some(
                  (a) => !compoundPicks[a.molecule_id],
                )
              }
            >
              {importMutation.isPending
                ? "Importing…"
                : (preview?.will_create_plates ?? 0) +
                    (preview?.will_create_wells ?? 0) +
                    (preview?.will_create_readouts ?? 0) ===
                  0
                ? "Attach file"
                : "Import"}
            </Button>
          )}
          {step === 4 && (
            <Button onClick={() => handleOpenChange(false)}>Done</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Step indicator ──────────────────────────────────────────────────────────

function StepIndicator({ step }: { step: 1 | 2 | 3 | 4 }) {
  const steps = ["Upload", "Mapping", "Preview", "Confirm"];
  return (
    <div className="flex items-center gap-2 text-xs">
      {steps.map((label, i) => {
        const n = (i + 1) as 1 | 2 | 3 | 4;
        const active = step === n;
        const done = step > n;
        return (
          <div key={label} className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-medium",
                active && "border-primary bg-primary/10 text-primary",
                done && "border-green-500 bg-green-500/10 text-green-400",
                !active && !done && "border-muted text-muted-foreground",
              )}
            >
              {n}
            </span>
            <span
              className={cn(
                active && "text-foreground",
                !active && "text-muted-foreground",
              )}
            >
              {label}
            </span>
            {i < steps.length - 1 && (
              <span className="mx-1 h-px w-6 bg-border" />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Step 1 ────────────────────────────────────────────────────────────────

function UploadStep({
  isDragging,
  file,
  isPending,
  onFile,
  onDrop,
  setIsDragging,
  inputRef,
}: {
  isDragging: boolean;
  file: File | null;
  isPending: boolean;
  onFile: (f: File) => void;
  onDrop: (e: React.DragEvent) => void;
  setIsDragging: (b: boolean) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="py-2">
      <div
        onDrop={onDrop}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragging(false);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 transition-colors",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50",
        )}
      >
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {isPending
            ? "Parsing…"
            : file
              ? file.name
              : "Drop a CSV or XLSX here, or click to browse"}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
          }}
        />
      </div>
    </div>
  );
}

// ─── Step 2 ────────────────────────────────────────────────────────────────

function MappingStep({
  preview,
  draft,
  readoutDefs,
  appliedTemplate,
  onClearTemplate,
  onSetRole,
  onSetReadoutDef,
  doseUnit,
  onAckLowConfidence,
  lowConfidenceHeaders,
}: {
  preview: PreviewRunFileResponse;
  draft: MappingDraft;
  readoutDefs: { id: string; name: string }[];
  doseUnit: string;
  appliedTemplate: RunImportTemplate | null;
  onClearTemplate: () => void;
  onSetRole: (h: string, r: ImportRole | "ignore") => void;
  onSetReadoutDef: (h: string, defId: string) => void;
  onAckLowConfidence: (v: boolean) => void;
  lowConfidenceHeaders: string[];
}) {
  return (
    <div className="space-y-4 py-2">
      {appliedTemplate && (
        <div className="flex items-center justify-between rounded-md border border-primary/40 bg-primary/5 p-3 text-sm">
          <span>
            Applied template <strong>{appliedTemplate.name}</strong>. Adjust as
            needed.
          </span>
          <Button variant="ghost" size="sm" onClick={onClearTemplate}>
            Clear
          </Button>
        </div>
      )}

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
              const role = draft.roles[s.header] ?? null;
              return (
                <tr key={s.header} className="border-b last:border-b-0">
                  <td className="px-3 py-2 font-mono">{s.header}</td>
                  <td className="px-3 py-2">
                    <Select
                      value={role ?? "ignore"}
                      onValueChange={(v) =>
                        onSetRole(s.header, v as ImportRole | "ignore")
                      }
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
                    <Badge
                      variant="outline"
                      className={confidenceBadgeClass(s.confidence)}
                    >
                      {confidenceLabel(s.confidence)}
                    </Badge>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {s.reason}
                    </span>
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
                          {readoutDefs.map((rd) => (
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

      <div className="rounded-md border border-muted bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
        Dose values in this file are interpreted as{" "}
        <span className="font-mono font-medium text-foreground">{doseUnit}</span>{" "}
        (per protocol). To change the unit, edit the protocol&apos;s Dose Unit
        on the Design tab.
      </div>

      {lowConfidenceHeaders.length > 0 && (
        <label className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
          <Checkbox
            checked={draft.acknowledgedLowConfidence}
            onCheckedChange={(v) => onAckLowConfidence(!!v)}
          />
          <span>
            <strong>{lowConfidenceHeaders.length}</strong> column(s) have low
            confidence: <span className="font-mono">{lowConfidenceHeaders.join(", ")}</span>.
            Confirm assignments before continuing.
          </span>
        </label>
      )}
    </div>
  );
}

// ─── Step 3 ────────────────────────────────────────────────────────────────

function PreviewStep({
  preview,
  compoundPicks,
  onCompoundPick,
}: {
  preview: PreviewRunFileResponse;
  compoundPicks: Record<string, string>;
  onCompoundPick: (moleculeId: string, batchId: string) => void;
}) {
  const willCreateTotal =
    preview.will_create_plates +
    preview.will_create_wells +
    preview.will_create_readouts;
  const willSkipTotal =
    preview.will_skip_wells.length + preview.will_skip_readouts.length;

  return (
    <div className="space-y-4 py-2">
      <div className="grid grid-cols-3 gap-3">
        <SummaryCard
          label="Will create"
          value={willCreateTotal}
          accent={willCreateTotal > 0 ? "ok" : undefined}
        />
        <SummaryCard
          label="Will skip"
          value={willSkipTotal}
          accent={willSkipTotal > 0 ? "warn" : undefined}
        />
        <SummaryCard
          label="Will fail"
          value={preview.validation_errors.length}
          accent={preview.validation_errors.length > 0 ? "fail" : undefined}
        />
      </div>

      {willCreateTotal > 0 && (
        <div className="rounded-md border border-green-500/30 bg-green-500/5 p-3 text-xs text-muted-foreground">
          <span className="font-medium text-green-300">Will create: </span>
          {preview.will_create_plates > 0 && (
            <>{preview.will_create_plates} plate{preview.will_create_plates === 1 ? "" : "s"}, </>
          )}
          {preview.will_create_wells} well{preview.will_create_wells === 1 ? "" : "s"},{" "}
          {preview.will_create_readouts} readout cell
          {preview.will_create_readouts === 1 ? "" : "s"}
        </div>
      )}

      {willCreateTotal === 0 && preview.validation_errors.length === 0 && (
        <div className="rounded-md border border-muted bg-muted/30 p-3 text-sm text-muted-foreground">
          Nothing new to import — this file is fully redundant with what&apos;s
          already on the run. The file will still be saved to the Files tab as
          an audit artifact. Use <span className="font-medium">Reset Run Data</span>{" "}
          on the run header if you want to wipe and re-import.
        </div>
      )}

      {willSkipTotal > 0 && (
        <ConflictPanel
          wells={preview.will_skip_wells}
          readouts={preview.will_skip_readouts}
        />
      )}

      <div>
        <p className="mb-2 text-xs font-medium text-muted-foreground">
          Per-plate summary
        </p>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr className="border-b">
                <th className="px-3 py-2 text-left font-medium">Plate</th>
                <th className="px-3 py-2 text-left font-medium">Format</th>
                <th className="px-3 py-2 text-right font-medium">Wells</th>
                <th className="px-3 py-2 text-right font-medium">Samples</th>
                <th className="px-3 py-2 text-right font-medium">Blanks</th>
              </tr>
            </thead>
            <tbody>
              {preview.plates.map((p) => (
                <tr key={p.plate_name} className="border-b last:border-b-0">
                  <td className="px-3 py-2 font-mono">{p.plate_name}</td>
                  <td className="px-3 py-2">{p.plate_format}</td>
                  <td className="px-3 py-2 text-right">{p.well_count}</td>
                  <td className="px-3 py-2 text-right">{p.sample_count}</td>
                  <td className="px-3 py-2 text-right">{p.blank_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {preview.validation_errors.length > 0 && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <div className="mb-1 flex items-center gap-2 font-medium text-destructive">
            <AlertCircle className="h-4 w-4" />
            Cannot import — protocol setup needed
          </div>
          <ul className="ml-5 list-disc space-y-1 text-xs text-muted-foreground">
            {preview.validation_errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            Configure on the protocol&apos;s <span className="font-medium">Design</span> tab → Control Layouts. You&apos;ll need a Plate Template first (Administration → Screening Setup → Plate Templates).
          </p>
        </div>
      )}

      {preview.unmatched_batches.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
          <div className="mb-1 flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
            <AlertCircle className="h-4 w-4" />
            {preview.unmatched_batches.length} unmatched batch ref(s)
          </div>
          <p className="text-xs text-muted-foreground">
            These wells will be skipped. Register the batches first if they
            should be included.
          </p>
          <p className="mt-2 break-words font-mono text-xs">
            {preview.unmatched_batches.slice(0, 20).join(", ")}
            {preview.unmatched_batches.length > 20 && "…"}
          </p>
        </div>
      )}

      {preview.unmatched_compound_refs.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
          <div className="mb-1 flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
            <AlertCircle className="h-4 w-4" />
            {preview.unmatched_compound_refs.length} unmatched compound ref(s)
          </div>
          <p className="text-xs text-muted-foreground">
            No molecule matches these identifiers (or the molecule has no
            registered batches). Wells will be skipped.
          </p>
          <p className="mt-2 break-words font-mono text-xs">
            {preview.unmatched_compound_refs.slice(0, 20).join(", ")}
            {preview.unmatched_compound_refs.length > 20 && "…"}
          </p>
        </div>
      )}

      {preview.ambiguous_compounds.length > 0 && (
        <DisambiguatePanel
          ambiguous={preview.ambiguous_compounds}
          picks={compoundPicks}
          onPick={onCompoundPick}
        />
      )}

      {preview.row_conflicts.length > 0 && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
          <div className="mb-1 flex items-center gap-2 font-medium text-destructive">
            <AlertCircle className="h-4 w-4" />
            Batch Ref / Compound Ref disagree on{" "}
            {preview.row_conflicts.length} row(s)
          </div>
          <p className="text-xs text-muted-foreground">
            Each row's Batch Ref and Compound Ref point to different molecules.
            Fix the file (drop one column or correct the values) and re-upload.
          </p>
          <ul className="ml-2 mt-2 space-y-1 font-mono text-xs">
            {preview.row_conflicts.slice(0, 10).map((line, i) => (
              <li key={i}>{line}</li>
            ))}
            {preview.row_conflicts.length > 10 && (
              <li className="text-muted-foreground">
                …and {preview.row_conflicts.length - 10} more
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

function DisambiguatePanel({
  ambiguous,
  picks,
  onPick,
}: {
  ambiguous: import("../hooks/use-run-import").AmbiguousCompound[];
  picks: Record<string, string>;
  onPick: (moleculeId: string, batchId: string) => void;
}) {
  const resolvedCount = ambiguous.filter((a) => picks[a.molecule_id]).length;
  const allPicked = resolvedCount === ambiguous.length;

  // Convenience: fills unpicked rows with each compound's most-recently
  // created batch. Existing picks are left alone — chemist's deliberate
  // choices win over auto-fill. Defensive sort in case the BE ever
  // returns batch_options in a different order.
  const handleAutoPickLatest = () => {
    for (const a of ambiguous) {
      if (picks[a.molecule_id]) continue;
      if (a.batch_options.length === 0) continue;
      const latest = [...a.batch_options].sort((x, y) =>
        y.created_at.localeCompare(x.created_at),
      )[0];
      onPick(a.molecule_id, latest.batch_id);
    }
  };

  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
      <div className="mb-2 flex items-center justify-between gap-2 font-medium text-amber-700 dark:text-amber-300">
        <div className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          Disambiguate compounds ({resolvedCount} / {ambiguous.length} picked)
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleAutoPickLatest}
          disabled={allPicked}
          title="Picks the most recently created batch for every compound that hasn't been picked yet"
        >
          Auto-pick latest
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        These compounds have multiple registered batches. Pick the lot that
        was actually assayed; your choice applies to every row referencing
        that compound.
      </p>
      <div className="mt-3 space-y-2">
        {ambiguous.map((a) => {
          const value = picks[a.molecule_id] ?? "";
          return (
            <div
              key={a.molecule_id}
              className="flex flex-col gap-1 rounded-md border border-muted bg-background/50 p-2 sm:flex-row sm:items-center sm:gap-3"
            >
              <div className="flex-1 min-w-0">
                <div className="font-mono text-xs text-foreground">
                  {a.compound_ref}
                </div>
                <div className="text-xs text-muted-foreground">
                  {a.molecule_name} · {a.affected_row_count} row
                  {a.affected_row_count === 1 ? "" : "s"}
                </div>
              </div>
              <Select
                value={value}
                onValueChange={(v) => onPick(a.molecule_id, v)}
              >
                <SelectTrigger className="h-8 w-full sm:w-80">
                  <SelectValue placeholder="Pick a batch…" />
                </SelectTrigger>
                <SelectContent>
                  {a.batch_options.map((b) => (
                    <SelectItem key={b.batch_id} value={b.batch_id}>
                      <span className="font-mono">{b.batch_number}</span>
                      {b.salt_form && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          · {b.salt_form}
                        </span>
                      )}
                      {b.purity != null && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          · {b.purity}%
                        </span>
                      )}
                      <span className="ml-2 text-xs text-muted-foreground">
                        · {formatDate(b.created_at)}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ConflictPanel({
  wells,
  readouts,
}: {
  wells: import("../hooks/use-run-import").WellConflict[];
  readouts: import("../hooks/use-run-import").ReadoutConflict[];
}) {
  const SAMPLE = 10;
  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
      <div className="mb-2 flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
        <AlertCircle className="h-4 w-4" />
        Will skip: {wells.length} well metadata mismatch
        {wells.length === 1 ? "" : "es"}, {readouts.length} readout cell
        {readouts.length === 1 ? "" : "s"} already populated
      </div>
      <p className="text-xs text-muted-foreground">
        Existing values are never overwritten. New plates, new wells, and
        empty readout cells will still write.
      </p>
      {wells.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-amber-700 dark:text-amber-200/90">
            Well metadata conflicts ({wells.length})
          </summary>
          <ul className="ml-2 mt-2 space-y-1 font-mono text-xs">
            {wells.slice(0, SAMPLE).map((w, i) => (
              <li key={i}>
                <span className="text-foreground">{w.plate_name} {w.well_position}</span>
                <span className="ml-2 text-muted-foreground">— {w.reason}</span>
              </li>
            ))}
            {wells.length > SAMPLE && (
              <li className="text-muted-foreground">
                …and {wells.length - SAMPLE} more
              </li>
            )}
          </ul>
        </details>
      )}
      {readouts.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-amber-700 dark:text-amber-200/90">
            Readout cells already populated ({readouts.length})
          </summary>
          <ul className="ml-2 mt-2 space-y-1 font-mono text-xs">
            {readouts.slice(0, SAMPLE).map((r, i) => (
              <li key={i}>
                <span className="text-foreground">
                  {r.plate_name} {r.well_position}
                </span>
                <span className="ml-2 text-muted-foreground">
                  — {r.readout_name || "readout"}
                </span>
              </li>
            ))}
            {readouts.length > SAMPLE && (
              <li className="text-muted-foreground">
                …and {readouts.length - SAMPLE} more
              </li>
            )}
          </ul>
        </details>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: "ok" | "warn" | "fail";
}) {
  return (
    <div
      className={cn(
        "rounded-md border p-3",
        accent === "warn" && "border-amber-500/30 bg-amber-500/5",
        accent === "ok" && "border-green-500/30 bg-green-500/5",
        accent === "fail" && "border-destructive/40 bg-destructive/5",
      )}
    >
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}

// ─── Step 4 ────────────────────────────────────────────────────────────────

function ConfirmStep({
  result,
  saveAsTemplate,
  templateName,
  onSaveAsTemplate,
  onTemplateName,
  templateAlreadySaved,
}: {
  result: import("../hooks/use-run-import").ImportRunFileResponse;
  saveAsTemplate: boolean;
  templateName: string;
  onSaveAsTemplate: (v: boolean) => void;
  onTemplateName: (v: string) => void;
  templateAlreadySaved: boolean;
}) {
  return (
    <div className="space-y-4 py-2">
      <div className="flex items-start gap-2 rounded-md border border-green-500/30 bg-green-500/5 p-3 text-sm">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-400" />
        <div className="text-green-300">
          <p className="font-medium">Import complete</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {result.plates_created} plates · {result.wells_created} wells ·{" "}
            {result.readouts_created} readouts ·{" "}
            {result.controls_from_template} controls from layout
            {result.controls_unclassified > 0 && (
              <> · {result.controls_unclassified} blank wells unclassified</>
            )}
            {result.conflicts_well_metadata.length > 0 && (
              <>
                {" "}· {result.conflicts_well_metadata.length} well metadata
                conflict
                {result.conflicts_well_metadata.length === 1 ? "" : "s"} skipped
              </>
            )}
            {result.conflicts_readout.length > 0 && (
              <>
                {" "}· {result.conflicts_readout.length} readout cell
                {result.conflicts_readout.length === 1 ? "" : "s"} skipped
                (already present)
              </>
            )}
            {result.unmatched_batches.length > 0 && (
              <>
                {" "}
                · {result.unmatched_batches.length} unmatched batch refs
                skipped
              </>
            )}
          </p>
          {result.attachment_id && (
            <p className="mt-1 text-xs text-muted-foreground">
              Source file saved to the run&apos;s Files tab.
            </p>
          )}
          {result.attachment_warning && (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-300/90">
              File attachment failed: {result.attachment_warning}
            </p>
          )}
        </div>
      </div>

      {result.compute_warning && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
          <div className="mb-1 flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
            <AlertCircle className="h-4 w-4" />
            Post-import calculation failed
          </div>
          <p className="text-xs text-muted-foreground">
            Normalization / aggregation did not run. Dose-response curves and
            QC metrics will be empty until this is resolved.
          </p>
          <p className="mt-2 break-words font-mono text-xs">
            {result.compute_warning}
          </p>
        </div>
      )}

      <div className="rounded-md border p-3">
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={saveAsTemplate}
            onCheckedChange={(v) => onSaveAsTemplate(!!v)}
            disabled={templateAlreadySaved}
          />
          Save this mapping as a workspace template
        </label>
        {saveAsTemplate && !templateAlreadySaved && (
          <div className="mt-2">
            <Input
              placeholder="Template name (e.g. Standard 384-well long format)"
              value={templateName}
              onChange={(e) => onTemplateName(e.target.value)}
            />
          </div>
        )}
        {templateAlreadySaved && (
          <p className="mt-1 text-xs text-muted-foreground">Template saved.</p>
        )}
      </div>
    </div>
  );
}

