"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  Download,
  FileUp,
  Loader2,
  XCircle,
} from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useProtocols } from "@/features/screening-assay/hooks/use-protocols";
import {
  useCreateImportTemplate,
  useDeleteImportTemplate,
  useImportTemplates,
} from "../hooks/use-import-templates";
import { ColumnMappingStep } from "./column-mapping-step";

// ── Types ─────────────────────────────────────────────────────────────────────

interface PreviewResponse {
  headers: string[];
  preview_rows: string[][];
  total_rows: number;
  file_key: string;
}

interface ValidationIssue {
  row: number;
  column: string;
  message: string;
}

interface ValidationResponse {
  matched: number;
  unresolved: number;
  errors: number;
  issues: ValidationIssue[];
  valid: boolean;
}

interface ImportResult {
  imported: number;
  skipped: number;
  errors: number;
  plate_ids: string[];
}

// ── Step indicator ─────────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: 1 | 2 | 3 }) {
  const steps = [
    { n: 1, label: "Upload" },
    { n: 2, label: "Map Columns" },
    { n: 3, label: "Confirm" },
  ] as const;

  return (
    <div className="flex items-center gap-2 mb-6">
      {steps.map(({ n, label }, idx) => (
        <div key={n} className="flex items-center gap-2">
          {idx > 0 && (
            <div
              className={`h-px w-8 ${current > idx ? "bg-primary" : "bg-border"}`}
            />
          )}
          <div className="flex items-center gap-1.5">
            <div
              className={`h-7 w-7 rounded-full flex items-center justify-center text-xs font-semibold ${
                current === n
                  ? "bg-primary text-primary-foreground"
                  : current > n
                    ? "bg-primary/20 text-primary"
                    : "bg-muted text-muted-foreground"
              }`}
            >
              {n}
            </div>
            <span
              className={`text-sm ${current === n ? "font-medium" : "text-muted-foreground"}`}
            >
              {label}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main wizard ────────────────────────────────────────────────────────────────

export function ImportWizard() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [columnMappings, setColumnMappings] = useState<Record<string, string>>(
    {}
  );
  const [protocolId, setProtocolId] = useState("");
  const [runId, setRunId] = useState("");
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [saveTemplateName, setSaveTemplateName] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);

  const { data: protocols } = useProtocols();
  const { data: importTemplates } = useImportTemplates();
  const createTemplate = useCreateImportTemplate();
  const deleteTemplate = useDeleteImportTemplate();
  const [showTemplates, setShowTemplates] = useState(false);

  // ── Step 1: Upload ───────────────────────────────────────────────────────────

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await customInstance<PreviewResponse>({
        url: "/api/v1/plates/import/preview",
        method: "POST",
        data: formData,
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(response);
      // Auto-detect obvious column mappings by name
      const auto: Record<string, string> = {};
      for (const h of response.headers) {
        const lower = h.toLowerCase().replace(/[\s_-]+/g, "_");
        if (lower.includes("barcode") || lower.includes("plate_id"))
          auto[h] = "plate_barcode";
        else if (lower.includes("well") && lower.includes("pos"))
          auto[h] = "well_position";
        else if (
          lower.includes("cmpd") ||
          lower.includes("compound") ||
          lower.includes("mol_id") ||
          lower.includes("reg_no")
        )
          auto[h] = "molecule_identifier";
        else if (lower.includes("qualifier")) auto[h] = "qualifier";
        else auto[h] = "skip";
      }
      setColumnMappings(auto);
      setStep(2);
    } catch (err: unknown) {
      showError(
        err instanceof Error ? err.message : "Upload failed. Check the file format."
      );
    } finally {
      setUploading(false);
    }
  }

  function handleTemplateLoad(templateId: string) {
    const tpl = importTemplates?.find((t) => t.id === templateId);
    if (!tpl) return;
    setColumnMappings(tpl.column_mappings);
    if (tpl.default_protocol_id) setProtocolId(tpl.default_protocol_id);
  }

  function downloadTemplate() {
    const selectedProtocol = protocols?.find((p) => p.id === protocolId);
    const readoutDefs = selectedProtocol?.readout_definitions ?? [];

    const baseHeaders = ["plate_barcode", "well_position", "molecule_identifier", "qualifier"];
    const baseExample = ["PLT-001", "A01", "CV-000001", "="];

    const readoutHeaders = readoutDefs.map((rd) =>
      rd.unit ? `${rd.name} (${rd.unit})` : rd.name
    );
    const readoutExample = readoutDefs.map((rd) =>
      rd.data_type === "numeric" ? "0.00" : ""
    );

    const headers = [...baseHeaders, ...readoutHeaders];
    const example = [...baseExample, ...readoutExample];

    const csv = [headers.join(","), example.join(",")].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = selectedProtocol
      ? `plate_import_template_${selectedProtocol.name.replace(/\s+/g, "_")}.csv`
      : "plate_import_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Step 2: Validate ─────────────────────────────────────────────────────────

  async function handleValidate() {
    if (!preview) return;
    setValidating(true);
    try {
      const response = await customInstance<ValidationResponse>({
        url: "/api/v1/plates/import/validate",
        method: "POST",
        data: {
          file_key: preview.file_key,
          column_mappings: columnMappings,
          protocol_id: protocolId || null,
          run_id: runId || null,
        },
      });
      setValidation(response);
      setStep(3);
    } catch (err: unknown) {
      showError(
        err instanceof Error ? err.message : "Validation failed."
      );
    } finally {
      setValidating(false);
    }
  }

  async function handleSaveTemplate() {
    if (!saveTemplateName.trim()) return;
    setSavingTemplate(true);
    try {
      await createTemplate.mutateAsync({
        name: saveTemplateName.trim(),
        column_mappings: columnMappings,
        default_protocol_id: protocolId || null,
      });
      setSaveTemplateName("");
    } finally {
      setSavingTemplate(false);
    }
  }

  // ── Step 3: Import ───────────────────────────────────────────────────────────

  async function handleImport() {
    if (!preview) return;
    setImporting(true);
    try {
      const response = await customInstance<ImportResult>({
        url: "/api/v1/plates/import/execute",
        method: "POST",
        data: {
          file_key: preview.file_key,
          column_mappings: columnMappings,
          protocol_id: protocolId || null,
          run_id: runId || null,
        },
      });
      setImportResult(response);
      showSuccess(`Imported ${response.imported} plate(s)`);
    } catch (err: unknown) {
      showError(
        err instanceof Error ? err.message : "Import failed."
      );
    } finally {
      setImporting(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Import Plate Data</h1>
        <p className="mt-1 text-muted-foreground">
          Upload a CSV/TSV file and map columns to plate fields.
        </p>
      </div>

      <StepIndicator current={step} />

      {/* Saved templates management */}
      {importTemplates && importTemplates.length > 0 && (
        <div className="mb-4">
          <button
            type="button"
            onClick={() => setShowTemplates((v) => !v)}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            {showTemplates ? "Hide" : "Manage"} saved templates ({importTemplates.length})
          </button>
          {showTemplates && (
            <Card className="mt-2">
              <CardContent className="pt-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Columns</TableHead>
                      <TableHead className="w-20" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {importTemplates.map((tpl) => (
                      <TableRow key={tpl.id}>
                        <TableCell className="font-medium">{tpl.name}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {tpl.description || "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {Object.keys(tpl.column_mappings).length} mappings
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => deleteTemplate.mutate(tpl.id)}
                          >
                            Delete
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── Step 1: Upload ── */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Upload File</CardTitle>
            <CardDescription>
              Supported formats: CSV, TSV, TXT, XLSX. Max 10 MB.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Template helpers */}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={downloadTemplate}>
                <Download className="mr-2 h-4 w-4" />
                Download Template
              </Button>
              {importTemplates && importTemplates.length > 0 && (
                <Select onValueChange={handleTemplateLoad}>
                  <SelectTrigger className="w-[220px]">
                    <SelectValue placeholder="Load saved template…" />
                  </SelectTrigger>
                  <SelectContent>
                    {importTemplates.map((tpl) => (
                      <SelectItem key={tpl.id} value={tpl.id}>
                        {tpl.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Drop zone */}
            <div
              className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/30 p-10 text-center cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const dropped = e.dataTransfer.files[0];
                if (dropped) setFile(dropped);
              }}
            >
              <FileUp className="h-10 w-10 text-muted-foreground/40 mb-3" />
              {file ? (
                <p className="text-sm font-medium">{file.name}</p>
              ) : (
                <>
                  <p className="text-sm font-medium">
                    Drop a file here or click to browse
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    CSV, TSV, TXT, XLSX
                  </p>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.tsv,.txt,.xlsx"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) setFile(f);
                }}
              />
            </div>

            <div className="flex justify-end">
              <Button
                onClick={handleUpload}
                disabled={!file || uploading}
              >
                {uploading && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Upload &amp; Preview
              </Button>
            </div>

            {/* Preview table shown if we already have preview and come back */}
            {preview && (
              <PreviewTable
                headers={preview.headers}
                rows={preview.preview_rows.slice(0, 10)}
                totalRows={preview.total_rows}
              />
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Step 2: Map Columns ── */}
      {step === 2 && preview && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Map Columns</CardTitle>
              <CardDescription>
                {preview.total_rows} data rows detected. Assign each file
                column to a plate field.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ColumnMappingStep
                headers={preview.headers}
                previewRows={preview.preview_rows}
                columnMappings={columnMappings}
                onMappingsChange={setColumnMappings}
                protocolId={protocolId || undefined}
              />
            </CardContent>
          </Card>

          {/* Protocol + Run */}
          <Card>
            <CardHeader>
              <CardTitle>Protocol &amp; Run</CardTitle>
              <CardDescription>
                Optionally link imported data to a screening protocol and run.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Protocol</label>
                  {protocols && protocols.length > 0 ? (
                    <Select value={protocolId || "__none__"} onValueChange={(v) => setProtocolId(v === "__none__" ? "" : v)}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select protocol…" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">None</SelectItem>
                        {protocols.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      placeholder="Protocol ID (optional)"
                      value={protocolId}
                      onChange={(e) => setProtocolId(e.target.value)}
                    />
                  )}
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Run ID</label>
                  <Input
                    placeholder="Run ID (optional)"
                    value={runId}
                    onChange={(e) => setRunId(e.target.value)}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Save template */}
          <Card>
            <CardHeader>
              <CardTitle>Save as Template</CardTitle>
              <CardDescription>
                Reuse this column mapping for future imports.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                <Input
                  placeholder="Template name…"
                  value={saveTemplateName}
                  onChange={(e) => setSaveTemplateName(e.target.value)}
                  className="max-w-xs"
                />
                <Button
                  variant="outline"
                  disabled={!saveTemplateName.trim() || savingTemplate}
                  onClick={handleSaveTemplate}
                >
                  {savingTemplate && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Save Template
                </Button>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-between">
            <Button variant="outline" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button onClick={handleValidate} disabled={validating}>
              {validating && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Validate &amp; Continue
            </Button>
          </div>
        </div>
      )}

      {/* ── Step 3: Confirm ── */}
      {step === 3 && (
        <div className="space-y-4">
          {importResult ? (
            <ImportResultCard result={importResult} onDone={() => router.push("/inventory/plates")} />
          ) : (
            <>
              {validation && (
                <ValidationSummaryCard validation={validation} />
              )}
              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(2)}>
                  Back
                </Button>
                <Button
                  onClick={handleImport}
                  disabled={importing || (validation != null && !validation.valid)}
                >
                  {importing && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Import Now
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function PreviewTable({
  headers,
  rows,
  totalRows,
}: {
  headers: string[];
  rows: string[][];
  totalRows: number;
}) {
  return (
    <div>
      <p className="mb-2 text-sm text-muted-foreground">
        Previewing first {rows.length} of {totalRows} rows
      </p>
      <div className="rounded-md border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {headers.map((h) => (
                <TableHead key={h} className="font-mono text-xs whitespace-nowrap">
                  {h}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, i) => (
              <TableRow key={i}>
                {row.map((cell, j) => (
                  <TableCell key={j} className="font-mono text-xs max-w-[120px] truncate">
                    {cell}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function ValidationSummaryCard({
  validation,
}: {
  validation: ValidationResponse;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {validation.valid ? (
            <CheckCircle2 className="h-5 w-5 text-green-500" />
          ) : (
            <XCircle className="h-5 w-5 text-destructive" />
          )}
          Validation {validation.valid ? "Passed" : "Failed"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-4">
          <Stat label="Matched" value={validation.matched} variant="success" />
          <Stat label="Unresolved" value={validation.unresolved} variant="warn" />
          <Stat label="Errors" value={validation.errors} variant="error" />
        </div>

        {validation.issues.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-2">Issues</p>
            <div className="rounded-md border max-h-60 overflow-y-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">Row</TableHead>
                    <TableHead className="w-40">Column</TableHead>
                    <TableHead>Message</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {validation.issues.map((issue, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-mono text-xs">
                        {issue.row}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {issue.column}
                      </TableCell>
                      <TableCell className="text-xs text-destructive">
                        {issue.message}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ImportResultCard({
  result,
  onDone,
}: {
  result: ImportResult;
  onDone: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-500" />
          Import Complete
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <Stat label="Imported" value={result.imported} variant="success" />
          <Stat label="Skipped" value={result.skipped} variant="warn" />
          <Stat label="Errors" value={result.errors} variant="error" />
        </div>
        {result.plate_ids.length > 0 && (
          <p className="text-sm text-muted-foreground">
            {result.plate_ids.length} plate(s) created or updated.
          </p>
        )}
        <Button onClick={onDone}>View Plates</Button>
      </CardContent>
    </Card>
  );
}

function Stat({
  label,
  value,
  variant,
}: {
  label: string;
  value: number;
  variant: "success" | "warn" | "error";
}) {
  const color =
    variant === "success"
      ? "text-green-500"
      : variant === "warn"
        ? "text-yellow-500"
        : "text-destructive";
  return (
    <div className="rounded-md border p-3 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-muted-foreground mt-0.5">{label}</div>
    </div>
  );
}
