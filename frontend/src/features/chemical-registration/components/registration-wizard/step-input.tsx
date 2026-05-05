"use client";

import { useState, useMemo, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import {
  FlaskConical,
  Upload,
  Pencil,
  Plus,
  Trash2,
  Download,
  FileSpreadsheet,
  FileText,
  Info,
} from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";
import { Switch } from "@/shared/components/ui/switch";
import { Separator } from "@/shared/components/ui/separator";
import { Badge } from "@/shared/components/ui/badge";
import { StructureEditorDialog } from "@/shared/components/chemistry";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useWorkspaceSettings } from "@/features/workspace-config/hooks/use-workspace-settings";
import { useRegistrationForms } from "@/features/workspace-config/hooks/use-registration-forms";
import { useCustomFields } from "@/features/workspace-config/hooks/use-custom-fields";
import { CustomFieldsRenderer } from "@/features/workspace-config/components/custom-fields-renderer";
import { useMolecule } from "../../hooks/use-molecules";
import { MOLECULE_TYPE_LABELS } from "../../types";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import type { ExternalIdentifierInput } from "../../types/registration-wizard";

// ─── CSV template ───────────────────────────────────────────────────────────

const CSV_TEMPLATE_HEADERS = [
  "name",
  "smiles",
  "molecule_type",
  "identifier",
  "identifier_type",
  "amount_value",
  "amount_unit",
  "salt_code",
  "purity",
  "batch_source",
  "appearance",
];

const CSV_TEMPLATE_ROWS = [
  [
    "Aspirin",
    "CC(=O)Oc1ccccc1C(=O)O",
    "small_molecule",
    "50-78-2",
    "cas_number",
    "100",
    "mg",
    "",
    "99.5",
    "purchased",
    "White crystalline powder",
  ],
  [
    "Ibuprofen",
    "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O",
    "small_molecule",
    "15687-27-1",
    "cas_number",
    "250",
    "mg",
    "",
    "98.0",
    "synthesized",
    "",
  ],
];

function downloadCsvTemplate() {
  const lines = [
    CSV_TEMPLATE_HEADERS.join(","),
    ...CSV_TEMPLATE_ROWS.map((row) =>
      row.map((cell) => (cell.includes(",") ? `"${cell}"` : cell)).join(",")
    ),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "compound_registration_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Simple CSV parser for preview ──────────────────────────────────────────

function parseCsvPreview(text: string, maxRows = 10): string[][] {
  const lines = text.split("\n").filter((line) => line.trim().length > 0);
  const rows: string[][] = [];
  for (let i = 0; i < Math.min(lines.length, maxRows + 1); i++) {
    // Simple split — handles basic CSV without quoted commas in values
    const cells: string[] = [];
    let current = "";
    let inQuotes = false;
    for (const ch of lines[i]) {
      if (ch === '"') {
        inQuotes = !inQuotes;
      } else if (ch === "," && !inQuotes) {
        cells.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
    cells.push(current.trim());
    rows.push(cells);
  }
  return rows;
}

// ─── Identifier type options ────────────────────────────────────────────────

const IDENTIFIER_TYPES = [
  { value: "vendor_id", label: "Vendor ID" },
  { value: "cas_number", label: "CAS Number" },
  { value: "chembl_id", label: "ChEMBL ID" },
  { value: "pubchem_cid", label: "PubChem CID" },
  { value: "custom", label: "Custom" },
] as const;

// ─── Mode Selection ─────────────────────────────────────────────────────────

function ModeSelection({ onSelect }: { onSelect: (mode: "single" | "bulk") => void }) {
  return (
    <div className="grid gap-6 sm:grid-cols-2 max-w-2xl mx-auto py-8">
      <Card
        className="cursor-pointer transition-all hover:border-primary hover:shadow-md"
        onClick={() => onSelect("single")}
      >
        <CardHeader className="text-center pb-2">
          <FlaskConical className="mx-auto h-10 w-10 text-primary mb-2" />
          <CardTitle className="text-lg">Register Single Compound</CardTitle>
        </CardHeader>
        <CardContent>
          <CardDescription className="text-center">
            Enter compound details, draw a structure, and register one compound
            at a time with full control over metadata.
          </CardDescription>
        </CardContent>
      </Card>

      <Card
        className="cursor-pointer transition-all hover:border-primary hover:shadow-md"
        onClick={() => onSelect("bulk")}
      >
        <CardHeader className="text-center pb-2">
          <Upload className="mx-auto h-10 w-10 text-primary mb-2" />
          <CardTitle className="text-lg">Bulk Upload</CardTitle>
        </CardHeader>
        <CardContent>
          <CardDescription className="text-center">
            Upload a CSV or SDF file to register multiple compounds in a single
            batch operation.
          </CardDescription>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Single mode form ───────────────────────────────────────────────────────

function SingleInputForm() {
  const singleInput = useRegistrationWizard((s) => s.singleInput);
  const updateSingleInput = useRegistrationWizard((s) => s.updateSingleInput);
  const nextStep = useRegistrationWizard((s) => s.nextStep);

  const { data: orgs } = useOrganizations();
  const { data: settings } = useWorkspaceSettings();
  const { data: registrationForms } = useRegistrationForms("molecule");
  const { data: customFieldDefs } = useCustomFields("molecule", true);

  const [selectedFormId, setSelectedFormId] = useState<string>("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Molecule data for disclosure mode
  const { data: disclosureMolecule } = useMolecule(
    singleInput.disclosureMode && singleInput.moleculeId
      ? singleInput.moleculeId
      : undefined
  );

  const defaultFormId = registrationForms?.find((f) => f.is_default)?.id ?? "";
  const activeFormOverrides = useMemo(
    () =>
      registrationForms?.find(
        (f) => f.id === (selectedFormId || defaultFormId)
      )?.field_overrides ?? [],
    [registrationForms, selectedFormId, defaultFormId]
  );

  // Set default molecule type from settings on first load
  const defaultMoleculeType = settings?.default_molecule_type ?? "small_molecule";

  const handleAddExternalId = () => {
    updateSingleInput({
      externalIds: [
        ...singleInput.externalIds,
        { identifier: "", identifier_type: "vendor_id" },
      ],
    });
  };

  const handleRemoveExternalId = (index: number) => {
    const updated = singleInput.externalIds.filter((_, i) => i !== index);
    updateSingleInput({ externalIds: updated });
  };

  const handleUpdateExternalId = (
    index: number,
    patch: Partial<ExternalIdentifierInput>
  ) => {
    const updated = singleInput.externalIds.map((id, i) =>
      i === index ? { ...id, ...patch } : id
    );
    updateSingleInput({ externalIds: updated });
  };

  const handleCustomFieldChange = (values: Record<string, unknown>) => {
    updateSingleInput({ customFields: values });
  };

  const handleNext = () => {
    setError(null);

    if (!singleInput.disclosureMode) {
      if (!singleInput.name.trim()) {
        setError("Name is required");
        return;
      }
      if (!singleInput.originatingOrgId) {
        setError("Originating organization is required");
        return;
      }
    } else {
      // Disclosure mode — SMILES required
      if (!singleInput.smiles?.trim()) {
        setError("SMILES is required for disclosure");
        return;
      }
    }

    // Non-disclosure disclosed compounds need SMILES
    if (!singleInput.disclosureMode && !singleInput.smiles?.trim()) {
      // Only required if not undisclosed
      // The undisclosed switch is handled by checking disclosureMode === false
      // and smiles being null is acceptable when registering as undisclosed
      // (which is when name+org are filled but no SMILES)
      // So we do nothing here — undisclosed is fine without SMILES
    }

    // Validate required custom fields
    for (const field of customFieldDefs ?? []) {
      const override = activeFormOverrides.find(
        (o) => o.field_definition_id === field.id
      );
      const isRequired = override?.is_required ?? field.is_required;
      if (
        isRequired &&
        !String(singleInput.customFields[field.name] ?? "").trim()
      ) {
        setError(`${field.label} is required`);
        return;
      }
    }

    nextStep();
  };

  const isUndisclosed = singleInput.smiles === null && !singleInput.disclosureMode;

  return (
    <div className="max-w-2xl space-y-6">
      {/* Disclosure mode banner */}
      {singleInput.disclosureMode && disclosureMolecule && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950/50">
          <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 shrink-0" />
          <div>
            <p className="font-medium text-blue-900 dark:text-blue-100">
              Disclosing: {disclosureMolecule.name}
            </p>
            <p className="text-sm text-blue-700 dark:text-blue-300">
              Provide the chemical structure (SMILES) to disclose this compound.
            </p>
          </div>
        </div>
      )}

      {/* Registration form selector */}
      {!singleInput.disclosureMode &&
        registrationForms &&
        registrationForms.length > 0 && (
          <div className="grid gap-2">
            <Label htmlFor="reg-form">Registration Form</Label>
            <Select
              value={selectedFormId || defaultFormId}
              onValueChange={setSelectedFormId}
            >
              <SelectTrigger id="reg-form">
                <SelectValue placeholder="Select a form..." />
              </SelectTrigger>
              <SelectContent>
                {registrationForms.map((form) => (
                  <SelectItem key={form.id} value={form.id}>
                    {form.name}
                    {form.is_default && (
                      <span className="ml-2 text-muted-foreground text-xs">
                        (default)
                      </span>
                    )}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

      {/* Name — hidden in disclosure mode */}
      {!singleInput.disclosureMode && (
        <div className="grid gap-2">
          <Label htmlFor="wiz-name">
            Name <span className="text-destructive">*</span>
          </Label>
          <Input
            id="wiz-name"
            placeholder="e.g. Aspirin"
            value={singleInput.name}
            onChange={(e) => updateSingleInput({ name: e.target.value })}
          />
        </div>
      )}

      {/* Undisclosed switch — hidden in disclosure mode */}
      {!singleInput.disclosureMode && (
        <div className="flex items-center gap-2">
          <Switch
            id="wiz-undisclosed"
            checked={isUndisclosed}
            onCheckedChange={(checked) =>
              updateSingleInput({ smiles: checked ? null : "" })
            }
          />
          <Label htmlFor="wiz-undisclosed">Register as undisclosed (no structure)</Label>
        </div>
      )}

      {/* SMILES editor — shown when not undisclosed, or in disclosure mode */}
      {(singleInput.disclosureMode || !isUndisclosed) && (
        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="wiz-smiles">
              SMILES{" "}
              {singleInput.disclosureMode && (
                <span className="text-destructive">*</span>
              )}
            </Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setEditorOpen(true)}
            >
              <Pencil className="mr-2 h-3.5 w-3.5" />
              Draw
            </Button>
          </div>
          <Textarea
            id="wiz-smiles"
            placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
            value={singleInput.smiles ?? ""}
            onChange={(e) => updateSingleInput({ smiles: e.target.value })}
            rows={2}
            className="font-mono text-sm"
          />
          <StructureEditorDialog
            open={editorOpen}
            onOpenChange={setEditorOpen}
            initialStructure={singleInput.smiles ?? undefined}
            onApply={(s) => updateSingleInput({ smiles: s })}
            outputFormat="smiles"
          />
        </div>
      )}

      {/* Disclosure provenance fields — only in disclosure mode */}
      {singleInput.disclosureMode && (
        <>
          <Separator />
          <div className="grid gap-2">
            <Label htmlFor="wiz-scientist">Scientist Name</Label>
            <Input
              id="wiz-scientist"
              placeholder="Name of disclosing scientist"
              value={singleInput.scientistName}
              onChange={(e) =>
                updateSingleInput({ scientistName: e.target.value })
              }
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wiz-disc-org">Disclosing Organization</Label>
            <Select
              value={singleInput.disclosingOrgId ?? ""}
              onValueChange={(v) =>
                updateSingleInput({ disclosingOrgId: v || null })
              }
            >
              <SelectTrigger id="wiz-disc-org">
                <SelectValue placeholder="Select organization" />
              </SelectTrigger>
              <SelectContent>
                {orgs?.map((org) => (
                  <SelectItem key={org.id} value={org.id}>
                    {org.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wiz-notes">Notes</Label>
            <Textarea
              id="wiz-notes"
              placeholder="Optional notes about this disclosure"
              value={singleInput.notes}
              onChange={(e) =>
                updateSingleInput({ notes: e.target.value })
              }
              rows={2}
            />
          </div>
        </>
      )}

      {/* Molecule type — hidden in disclosure mode */}
      {!singleInput.disclosureMode && (
        <div className="grid gap-2">
          <Label htmlFor="wiz-type">Molecule Type</Label>
          <Select
            value={singleInput.moleculeType || defaultMoleculeType}
            onValueChange={(v) => updateSingleInput({ moleculeType: v })}
          >
            <SelectTrigger id="wiz-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(MOLECULE_TYPE_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Originating organization — hidden in disclosure mode */}
      {!singleInput.disclosureMode && (
        <div className="grid gap-2">
          <Label htmlFor="wiz-org">
            Originating Organization <span className="text-destructive">*</span>
          </Label>
          <Select
            value={singleInput.originatingOrgId ?? ""}
            onValueChange={(v) => updateSingleInput({ originatingOrgId: v })}
          >
            <SelectTrigger id="wiz-org">
              <SelectValue placeholder="Select organization" />
            </SelectTrigger>
            <SelectContent>
              {orgs?.map((org) => (
                <SelectItem key={org.id} value={org.id}>
                  {org.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* External identifiers — hidden in disclosure mode */}
      {!singleInput.disclosureMode && (
        <div className="grid gap-3">
          <div className="flex items-center justify-between">
            <Label>External Identifiers</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddExternalId}
            >
              <Plus className="mr-1 h-3.5 w-3.5" />
              Add
            </Button>
          </div>

          {singleInput.externalIds.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No external identifiers added. Click &quot;Add&quot; to include vendor IDs, CAS
              numbers, etc.
            </p>
          )}

          {singleInput.externalIds.map((extId, index) => (
            <div key={index} className="flex items-center gap-2">
              <Select
                value={extId.identifier_type}
                onValueChange={(v) =>
                  handleUpdateExternalId(index, { identifier_type: v })
                }
              >
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {IDENTIFIER_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                placeholder="e.g. ABBVIE-002, 50-78-2"
                value={extId.identifier}
                onChange={(e) =>
                  handleUpdateExternalId(index, { identifier: e.target.value })
                }
                className="flex-1"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => handleRemoveExternalId(index)}
                aria-label="Remove identifier"
              >
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Custom fields — hidden in disclosure mode */}
      {!singleInput.disclosureMode &&
        customFieldDefs &&
        customFieldDefs.length > 0 && (
          <>
            <Separator />
            <div className="grid gap-2">
              <Label>Custom Fields</Label>
              <CustomFieldsRenderer
                definitions={customFieldDefs}
                formOverrides={activeFormOverrides}
                values={singleInput.customFields}
                onChange={handleCustomFieldChange}
              />
            </div>
          </>
        )}

      {/* Error */}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Next button */}
      <div className="flex justify-end pt-4">
        <Button onClick={handleNext}>Next</Button>
      </div>
    </div>
  );
}

// ─── Bulk mode form ─────────────────────────────────────────────────────────

function BulkInputForm() {
  const bulkInput = useRegistrationWizard((s) => s.bulkInput);
  const updateBulkInput = useRegistrationWizard((s) => s.updateBulkInput);
  const nextStep = useRegistrationWizard((s) => s.nextStep);

  const { data: orgs } = useOrganizations();
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string[][] | null>(null);

  const onDrop = useCallback(
    (accepted: File[]) => {
      const file = accepted[0];
      if (!file) return;

      updateBulkInput({ file });

      // Parse CSV preview
      if (file.name.endsWith(".csv") || bulkInput.fileFormat === "csv") {
        const reader = new FileReader();
        reader.onload = (e) => {
          const text = e.target?.result;
          if (typeof text === "string") {
            const rows = parseCsvPreview(text, 10);
            setPreview(rows);
          }
        };
        reader.readAsText(file);
      } else {
        // SDF — no preview for now
        setPreview(null);
      }
    },
    [bulkInput.fileFormat, updateBulkInput]
  );

  const accept = useMemo(() => {
    const map: Record<string, string[]> = {};
    if (bulkInput.fileFormat === "sdf") {
      map["chemical/x-mdl-sdfile"] = [".sdf", ".sd"];
    } else if (bulkInput.fileFormat === "xlsx") {
      map["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"] = [".xlsx"];
    } else {
      map["text/csv"] = [".csv"];
    }
    return map;
  }, [bulkInput.fileFormat]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    maxFiles: 1,
    multiple: false,
  });

  const handleNext = () => {
    setError(null);

    if (!bulkInput.file) {
      setError("Please select a file to upload");
      return;
    }
    if (!bulkInput.originatingOrgId) {
      setError("Originating organization is required");
      return;
    }
    nextStep();
  };

  return (
    <div className="max-w-2xl space-y-6">
      {/* File format selector */}
      <div className="grid gap-2">
        <Label>File Format</Label>
        <div className="flex gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="file-format"
              checked={bulkInput.fileFormat === "csv"}
              onChange={() => {
                updateBulkInput({ fileFormat: "csv", file: null });
                setPreview(null);
              }}
              className="accent-primary"
            />
            <FileSpreadsheet className="h-4 w-4" />
            <span className="text-sm">CSV</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="file-format"
              checked={bulkInput.fileFormat === "xlsx"}
              onChange={() => {
                updateBulkInput({ fileFormat: "xlsx", file: null });
                setPreview(null);
              }}
              className="accent-primary"
            />
            <FileSpreadsheet className="h-4 w-4" />
            <span className="text-sm">Excel (.xlsx)</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="file-format"
              checked={bulkInput.fileFormat === "sdf"}
              onChange={() => {
                updateBulkInput({ fileFormat: "sdf", file: null });
                setPreview(null);
              }}
              className="accent-primary"
            />
            <FileText className="h-4 w-4" />
            <span className="text-sm">SDF</span>
          </label>
        </div>
      </div>

      {/* Template download (CSV / XLSX share the same column layout) */}
      {(bulkInput.fileFormat === "csv" || bulkInput.fileFormat === "xlsx") && (
        <Button variant="outline" size="sm" onClick={downloadCsvTemplate}>
          <Download className="mr-2 h-3.5 w-3.5" />
          Download CSV Template
        </Button>
      )}

      {/* Organization selector */}
      <div className="grid gap-2">
        <Label htmlFor="bulk-org">
          Originating Organization <span className="text-destructive">*</span>
        </Label>
        <Select
          value={bulkInput.originatingOrgId ?? ""}
          onValueChange={(v) => updateBulkInput({ originatingOrgId: v })}
        >
          <SelectTrigger id="bulk-org">
            <SelectValue placeholder="Select organization" />
          </SelectTrigger>
          <SelectContent>
            {orgs?.map((org) => (
              <SelectItem key={org.id} value={org.id}>
                {org.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Applied to all compounds in the file.
        </p>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50"
        }`}
      >
        <input {...getInputProps()} />
        <Upload className="mb-3 h-10 w-10 text-muted-foreground" />
        {isDragActive ? (
          <p className="text-sm text-muted-foreground">Drop file here</p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Drag &amp; drop a {bulkInput.fileFormat.toUpperCase()} file here, or click
              to browse
            </p>
            <p className="mt-1 text-xs text-muted-foreground/60">
              {bulkInput.fileFormat === "csv"
                ? "Accepts .csv files"
                : bulkInput.fileFormat === "xlsx"
                  ? "Accepts .xlsx files"
                  : "Accepts .sdf / .sd files"}
            </p>
          </>
        )}
      </div>

      {/* Selected file info */}
      {bulkInput.file && (
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="flex items-center gap-2">
            {bulkInput.fileFormat === "csv" || bulkInput.fileFormat === "xlsx" ? (
              <FileSpreadsheet className="h-5 w-5 text-muted-foreground" />
            ) : (
              <FileText className="h-5 w-5 text-muted-foreground" />
            )}
            <div>
              <p className="text-sm font-medium">{bulkInput.file.name}</p>
              <p className="text-xs text-muted-foreground">
                {(bulkInput.file.size / 1024).toFixed(1)} KB
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              updateBulkInput({ file: null });
              setPreview(null);
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      )}

      {/* CSV preview table */}
      {preview && preview.length > 1 && (
        <div className="grid gap-2">
          <div className="flex items-center gap-2">
            <Label>Preview</Label>
            <Badge variant="secondary" className="text-xs">
              {preview.length - 1} row{preview.length - 1 !== 1 ? "s" : ""} shown
            </Badge>
          </div>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/50">
                  {preview[0].map((header, i) => (
                    <th
                      key={i}
                      className="whitespace-nowrap px-3 py-2 text-left font-medium"
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.slice(1).map((row, rowIdx) => (
                  <tr key={rowIdx} className="border-b last:border-b-0">
                    {row.map((cell, cellIdx) => (
                      <td
                        key={cellIdx}
                        className="whitespace-nowrap px-3 py-1.5 text-muted-foreground"
                      >
                        {cell || "\u2014"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Error */}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Next button */}
      <div className="flex justify-end pt-4">
        <Button onClick={handleNext}>Next</Button>
      </div>
    </div>
  );
}

// ─── StepInput (exported) ───────────────────────────────────────────────────

export function StepInput() {
  const mode = useRegistrationWizard((s) => s.mode);
  const setMode = useRegistrationWizard((s) => s.setMode);

  if (mode === null) {
    return <ModeSelection onSelect={setMode} />;
  }

  if (mode === "single") {
    return <SingleInputForm />;
  }

  return <BulkInputForm />;
}
