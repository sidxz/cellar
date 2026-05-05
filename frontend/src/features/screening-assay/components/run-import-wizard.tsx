"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useProtocol } from "../hooks/use-protocols";
import {
  useCreateRunImportTemplate,
  useImportRunFile,
  usePreviewRunFile,
  useRunImportTemplates,
  type ColumnMappingPayload,
  type HeaderSuggestion,
  type ImportConfidence,
  type ImportRole,
  type PreviewRunFileResponse,
  type ReadoutColumnPayload,
  type RunImportTemplate,
} from "../hooks/use-run-import";
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
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { showError, showSuccess } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";

const ROLE_OPTIONS: Array<{ value: ImportRole | "ignore"; label: string }> = [
  { value: "well", label: "Well" },
  { value: "plate_name", label: "Plate Name" },
  { value: "concentration", label: "Concentration" },
  { value: "batch_ref", label: "Batch Ref" },
  { value: "scientist", label: "Scientist" },
  { value: "readout", label: "Readout" },
  { value: "ignore", label: "Ignore" },
];

const CONC_UNITS = ["uM", "nM", "mM", "mg/mL"] as const;

interface RunImportWizardProps {
  runId: string;
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface MappingDraft {
  // role per header (null = unassigned/ignore)
  roles: Record<string, ImportRole | null>;
  // header → readout_definition_id, only for headers with role=readout
  readoutDefByHeader: Record<string, string>;
  concentrationUnit: string;
  acknowledgedLowConfidence: boolean;
}

function emptyDraft(): MappingDraft {
  return {
    roles: {},
    readoutDefByHeader: {},
    concentrationUnit: "uM",
    acknowledgedLowConfidence: false,
  };
}

function suggestionToInitialDraft(
  suggestions: HeaderSuggestion[],
): MappingDraft {
  const roles: Record<string, ImportRole | null> = {};
  for (const s of suggestions) {
    roles[s.header] = s.role;
  }
  return {
    roles,
    readoutDefByHeader: {},
    concentrationUnit: "uM",
    acknowledgedLowConfidence: false,
  };
}

function applyTemplateToDraft(
  draft: MappingDraft,
  template: RunImportTemplate,
  headers: string[],
): MappingDraft {
  const next: MappingDraft = {
    ...draft,
    roles: { ...draft.roles },
    concentrationUnit: template.concentration_unit || draft.concentrationUnit,
  };
  const mapping = template.column_mapping as Record<string, unknown>;
  const setIfPresent = (header: unknown, role: ImportRole) => {
    if (typeof header === "string" && headers.includes(header)) {
      next.roles[header] = role;
    }
  };
  setIfPresent(mapping.well, "well");
  setIfPresent(mapping.plate_name, "plate_name");
  setIfPresent(mapping.concentration, "concentration");
  setIfPresent(mapping.batch_ref, "batch_ref");
  setIfPresent(mapping.scientist, "scientist");
  if (Array.isArray(mapping.readout_headers)) {
    for (const h of mapping.readout_headers) {
      if (typeof h === "string" && headers.includes(h)) {
        next.roles[h] = "readout";
      }
    }
  }
  return next;
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
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRunFileResponse | null>(null);
  const [draft, setDraft] = useState<MappingDraft>(emptyDraft());
  const [appliedTemplate, setAppliedTemplate] = useState<RunImportTemplate | null>(
    null,
  );
  const [saveAsTemplate, setSaveAsTemplate] = useState(false);
  const [templateName, setTemplateName] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const previewMutation = usePreviewRunFile(runId);
  const importMutation = useImportRunFile(runId);
  const createTemplate = useCreateRunImportTemplate();
  const { data: templates = [] } = useRunImportTemplates();
  const { data: protocol } = useProtocol(protocolId);

  const readoutDefs = protocol?.readout_definitions ?? [];

  const reset = useCallback(() => {
    setStep(1);
    setFile(null);
    setPreview(null);
    setDraft(emptyDraft());
    setAppliedTemplate(null);
    setSaveAsTemplate(false);
    setTemplateName("");
    previewMutation.reset();
    importMutation.reset();
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [importMutation, previewMutation]);

  const handleOpenChange = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
      previewMutation.mutate(
        { file: f },
        {
          onSuccess: (data) => {
            setPreview(data);
            setDraft(suggestionToInitialDraft(data.suggestions));
            // Auto-suggest a matching template if any header set lines up.
            const match = pickBestTemplate(templates, data.headers);
            if (match) {
              setAppliedTemplate(match);
              setDraft((d) => applyTemplateToDraft(d, match, data.headers));
            }
            setStep(2);
          },
          onError: () => showError("Could not parse file"),
        },
      );
    },
    [previewMutation, templates],
  );

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  // ─── Step 2 — mapping ───────────────────────────────────────────────────────

  const wellHeader = useMemo(() => {
    return Object.entries(draft.roles).find(([, r]) => r === "well")?.[0] ?? null;
  }, [draft.roles]);

  const lowConfidenceHeaders = useMemo(() => {
    if (!preview) return [] as string[];
    return preview.suggestions
      .filter((s) => s.confidence === "low" && draft.roles[s.header] !== null)
      .map((s) => s.header);
  }, [preview, draft.roles]);

  const readoutHeaders = useMemo(
    () =>
      Object.entries(draft.roles)
        .filter(([, r]) => r === "readout")
        .map(([h]) => h),
    [draft.roles],
  );

  const allReadoutsBound = readoutHeaders.every(
    (h) => !!draft.readoutDefByHeader[h],
  );

  const canContinueStep2 =
    !!wellHeader &&
    readoutHeaders.length > 0 &&
    allReadoutsBound &&
    (lowConfidenceHeaders.length === 0 || draft.acknowledgedLowConfidence);

  // ─── Run preview again when concentration unit changes (keeps cached parse) ─

  const handleSetRole = (header: string, role: ImportRole | "ignore") => {
    setDraft((d) => {
      const nextRoles = { ...d.roles };
      // well, plate_name, concentration, batch_ref, scientist are unique — clear any existing.
      const unique: ImportRole[] = ["well", "plate_name", "concentration", "batch_ref", "scientist"];
      const r: ImportRole | null = role === "ignore" ? null : role;
      if (r && unique.includes(r)) {
        for (const [h, existing] of Object.entries(nextRoles)) {
          if (existing === r && h !== header) {
            nextRoles[h] = null;
          }
        }
      }
      nextRoles[header] = r;
      // If we changed away from readout, drop the binding.
      const nextBindings = { ...d.readoutDefByHeader };
      if (r !== "readout" && nextBindings[header]) {
        delete nextBindings[header];
      }
      return { ...d, roles: nextRoles, readoutDefByHeader: nextBindings };
    });
  };

  const handleSetReadoutDef = (header: string, defId: string) => {
    setDraft((d) => ({
      ...d,
      readoutDefByHeader: { ...d.readoutDefByHeader, [header]: defId },
    }));
  };

  // ─── Step 4 — submit ─────────────────────────────────────────────────────────

  const buildMapping = (): ColumnMappingPayload | null => {
    if (!wellHeader) return null;
    const find = (role: ImportRole): string | null =>
      Object.entries(draft.roles).find(([, r]) => r === role)?.[0] ?? null;

    const readout_columns: ReadoutColumnPayload[] = readoutHeaders.map((h) => ({
      header: h,
      readout_definition_id: draft.readoutDefByHeader[h]!,
    }));

    return {
      well: wellHeader,
      plate_name: find("plate_name"),
      concentration: find("concentration"),
      batch_ref: find("batch_ref"),
      scientist: find("scientist"),
      readout_columns,
    };
  };

  const handleSubmit = () => {
    if (!preview) return;
    const mapping = buildMapping();
    if (!mapping) {
      showError("Mapping incomplete — pick a Well column.");
      return;
    }
    importMutation.mutate(
      {
        preview_id: preview.preview_id,
        mapping,
        concentration_unit: draft.concentrationUnit,
        replace_existing: false,
      },
      {
        onSuccess: (data) => {
          showSuccess(
            `Imported ${data.wells_created} wells / ${data.readouts_created} readouts`,
          );
          if (saveAsTemplate && templateName.trim()) {
            const column_mapping: Record<string, unknown> = {
              well: mapping.well,
              plate_name: mapping.plate_name,
              concentration: mapping.concentration,
              batch_ref: mapping.batch_ref,
              scientist: mapping.scientist,
              readout_headers: mapping.readout_columns.map((rc) => rc.header),
            };
            createTemplate.mutate({
              name: templateName.trim(),
              column_mapping,
              concentration_unit: draft.concentrationUnit,
            });
          }
          setStep(4);
        },
        onError: () => showError("Import failed"),
      },
    );
  };

  // ─── Render ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
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
            appliedTemplate={appliedTemplate}
            onClearTemplate={() => setAppliedTemplate(null)}
            onSetRole={handleSetRole}
            onSetReadoutDef={handleSetReadoutDef}
            onSetConcentrationUnit={(u) =>
              setDraft((d) => ({ ...d, concentrationUnit: u }))
            }
            onAckLowConfidence={(v) =>
              setDraft((d) => ({ ...d, acknowledgedLowConfidence: v }))
            }
            lowConfidenceHeaders={lowConfidenceHeaders}
          />
        )}

        {step === 3 && preview && (
          <PreviewStep preview={preview} />
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
              onClick={() => setStep((s) => (s - 1) as 1 | 2 | 3 | 4)}
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
              onClick={() => setStep(3)}
              disabled={!canContinueStep2}
            >
              Continue <ChevronRight className="h-4 w-4" />
            </Button>
          )}
          {step === 3 && (
            <Button
              onClick={handleSubmit}
              disabled={importMutation.isPending}
            >
              {importMutation.isPending ? "Importing…" : "Import"}
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
  onSetConcentrationUnit,
  onAckLowConfidence,
  lowConfidenceHeaders,
}: {
  preview: PreviewRunFileResponse;
  draft: MappingDraft;
  readoutDefs: { id: string; name: string }[];
  appliedTemplate: RunImportTemplate | null;
  onClearTemplate: () => void;
  onSetRole: (h: string, r: ImportRole | "ignore") => void;
  onSetReadoutDef: (h: string, defId: string) => void;
  onSetConcentrationUnit: (u: string) => void;
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

      <div className="flex items-center gap-3">
        <Label className="text-sm">Concentration unit</Label>
        <Select
          value={draft.concentrationUnit}
          onValueChange={onSetConcentrationUnit}
        >
          <SelectTrigger className="h-8 w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CONC_UNITS.map((u) => (
              <SelectItem key={u} value={u}>
                {u}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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

function PreviewStep({ preview }: { preview: PreviewRunFileResponse }) {
  return (
    <div className="space-y-4 py-2">
      <div className="grid grid-cols-3 gap-3">
        <SummaryCard label="Total rows" value={preview.total_rows} />
        <SummaryCard label="Plates" value={preview.plates.length} />
        <SummaryCard
          label="Matched batches"
          value={preview.matched_batches}
          accent={
            preview.unmatched_batches.length > 0 ? "warn" : "ok"
          }
        />
      </div>

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

      {preview.unmatched_batches.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
          <div className="mb-1 flex items-center gap-2 font-medium text-amber-300">
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
  accent?: "ok" | "warn";
}) {
  return (
    <div
      className={cn(
        "rounded-md border p-3",
        accent === "warn" && "border-amber-500/30 bg-amber-500/5",
        accent === "ok" && "border-green-500/30 bg-green-500/5",
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
            {result.readouts_created} readouts · {result.controls_inferred}{" "}
            blanks inferred
            {result.unmatched_batches.length > 0 && (
              <>
                {" "}
                · {result.unmatched_batches.length} unmatched batch refs
                skipped
              </>
            )}
          </p>
        </div>
      </div>

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

// ─── Helpers ──────────────────────────────────────────────────────────────

function pickBestTemplate(
  templates: RunImportTemplate[],
  headers: string[],
): RunImportTemplate | null {
  let best: RunImportTemplate | null = null;
  let bestScore = 0;
  const headerSet = new Set(headers.map((h) => normalize(h)));
  for (const t of templates) {
    const score = scoreTemplate(t, headerSet);
    if (score > bestScore) {
      bestScore = score;
      best = t;
    }
  }
  return bestScore >= 0.7 ? best : null;
}

function scoreTemplate(
  t: RunImportTemplate,
  headerSet: Set<string>,
): number {
  const m = t.column_mapping as Record<string, unknown>;
  const refs: string[] = [];
  for (const [k, v] of Object.entries(m)) {
    if (k === "readout_headers" && Array.isArray(v)) {
      refs.push(...v.filter((x): x is string => typeof x === "string"));
    } else if (typeof v === "string" && v) {
      refs.push(v);
    }
  }
  if (refs.length === 0) return 0;
  if (typeof m.well === "string" && !headerSet.has(normalize(m.well))) return 0;
  const hits = refs.filter((r) => headerSet.has(normalize(r))).length;
  return hits / refs.length;
}

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "");
}
