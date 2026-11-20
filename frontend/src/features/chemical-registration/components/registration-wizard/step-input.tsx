"use client";

import { ProjectFilter } from "@/features/research-organization/components/search/project-filter";
import { useCddEnabled } from "@/features/screening-assay/hooks/use-cdd-enabled";
import { CustomFieldsRenderer } from "@/features/workspace-config/components/custom-fields-renderer";
import { useCustomFields } from "@/features/workspace-config/hooks/use-custom-fields";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import {
  type FieldOverride,
  useRegistrationForms,
} from "@/features/workspace-config/hooks/use-registration-forms";
import { useWorkspaceSettings } from "@/features/workspace-config/hooks/use-workspace-settings";
import type { RegistrationRules } from "@/features/workspace-config/types";
import { StructureEditorDialog } from "@/shared/components/chemistry";
import { CsvDropzone } from "@/shared/components/csv-dropzone";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Separator } from "@/shared/components/ui/separator";
import { Switch } from "@/shared/components/ui/switch";
import { Textarea } from "@/shared/components/ui/textarea";
import { saveText } from "@/shared/lib/api/download";
import {
  CloudDownload,
  Download,
  FlaskConical,
  Info,
  Pencil,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMolecule } from "../../hooks/use-molecules";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { MOLECULE_TYPE_LABELS } from "../../types";
import type { BulkInput } from "../../types/registration-wizard";
import type { ExternalIdentifierInput } from "../../types/registration-wizard";
import { BulkUploadSummary } from "./bulk-upload-summary";

// ─── CSV template ───────────────────────────────────────────────────────────

// Headers the server's column suggestions recognise (bulk_column_mapping.py), so a
// filled-in template maps itself. One compound with two batches shows that each
// row is one batch.
const CSV_TEMPLATE_HEADERS = [
  "name",
  "smiles",
  "molecule_type",
  "synonym",
  "cas_number",
  "batch_id",
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
    "Acetylsalicylic acid",
    "50-78-2",
    "ASP-LOT-001",
    "100",
    "mg",
    "",
    "99.5",
    "purchased",
    "White crystalline powder",
  ],
  [
    "Aspirin",
    "CC(=O)Oc1ccccc1C(=O)O",
    "small_molecule",
    "Acetylsalicylic acid",
    "50-78-2",
    "ASP-LOT-002",
    "250",
    "mg",
    "",
    "98.7",
    "purchased",
    "White crystalline powder",
  ],
  [
    "Ibuprofen",
    "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O",
    "small_molecule",
    "",
    "15687-27-1",
    "IBU-LOT-001",
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
      row.map((cell) => (cell.includes(",") ? `"${cell}"` : cell)).join(","),
    ),
  ];
  saveText(lines.join("\n"), "compound_registration_template.csv");
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
  const { enabled: cddEnabled } = useCddEnabled();
  const cols = cddEnabled ? "sm:grid-cols-3" : "sm:grid-cols-2";
  const maxW = cddEnabled ? "max-w-4xl" : "max-w-2xl";

  return (
    <div className={`grid gap-6 ${cols} ${maxW} mx-auto py-8`}>
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
            Register one compound with a chemical structure or mark its structure as undisclosed.
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
            Upload a CSV, XLSX, or SDF file to register multiple compounds in a single batch
            operation.
          </CardDescription>
        </CardContent>
      </Card>

      {cddEnabled && (
        <Link
          href="/admin/data-import/cdd"
          className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-xl"
        >
          <Card className="cursor-pointer transition-all hover:border-primary hover:shadow-md h-full">
            <CardHeader className="text-center pb-2">
              <CloudDownload className="mx-auto h-10 w-10 text-primary mb-2" />
              <CardTitle className="text-lg">Import from CDD</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription className="text-center">
                Sync compounds from the configured CDD vault — full vault import or modified-since
                sync.
              </CardDescription>
            </CardContent>
          </Card>
        </Link>
      )}
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
    singleInput.disclosureMode && singleInput.moleculeId ? singleInput.moleculeId : undefined,
  );

  const defaultFormId = registrationForms?.find((f) => f.is_default)?.id ?? "";
  // Backend types `field_overrides` entries as opaque dicts; read them as the
  // FE's structured view at this consumption edge (same double-cast convention
  // as registration-form-admin — see FieldOverride in use-registration-forms).
  const activeFormOverrides = useMemo(
    () =>
      (registrationForms?.find((f) => f.id === (selectedFormId || defaultFormId))
        ?.field_overrides ?? []) as unknown as FieldOverride[],
    [registrationForms, selectedFormId, defaultFormId],
  );

  // Set default molecule type from settings on first load
  const defaultMoleculeType = settings?.default_molecule_type ?? "small_molecule";

  const handleAddExternalId = () => {
    updateSingleInput({
      externalIds: [...singleInput.externalIds, { identifier: "", identifier_type: "vendor_id" }],
    });
  };

  const handleRemoveExternalId = (index: number) => {
    const updated = singleInput.externalIds.filter((_, i) => i !== index);
    updateSingleInput({ externalIds: updated });
  };

  const handleUpdateExternalId = (index: number, patch: Partial<ExternalIdentifierInput>) => {
    const updated = singleInput.externalIds.map((id, i) =>
      i === index ? { ...id, ...patch } : id,
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
      const override = activeFormOverrides.find((o) => o.field_definition_id === field.id);
      const isRequired = override?.is_required ?? field.is_required;
      if (isRequired && !String(singleInput.customFields[field.name] ?? "").trim()) {
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
      {!singleInput.disclosureMode && registrationForms && registrationForms.length > 0 && (
        <div className="grid gap-2">
          <Label htmlFor="reg-form">Registration Form</Label>
          <Select value={selectedFormId || defaultFormId} onValueChange={setSelectedFormId}>
            <SelectTrigger id="reg-form">
              <SelectValue placeholder="Select a form..." />
            </SelectTrigger>
            <SelectContent>
              {registrationForms.map((form) => (
                <SelectItem key={form.id} value={form.id}>
                  {form.name}
                  {form.is_default && (
                    <span className="ml-2 text-muted-foreground text-xs">(default)</span>
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
            onCheckedChange={(checked) => updateSingleInput({ smiles: checked ? null : "" })}
          />
          <Label htmlFor="wiz-undisclosed">Register as undisclosed (no structure)</Label>
        </div>
      )}

      {/* SMILES editor — shown when not undisclosed, or in disclosure mode */}
      {(singleInput.disclosureMode || !isUndisclosed) && (
        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="wiz-smiles">
              SMILES {singleInput.disclosureMode && <span className="text-destructive">*</span>}
            </Label>
            <Button type="button" variant="outline" size="sm" onClick={() => setEditorOpen(true)}>
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
              onChange={(e) => updateSingleInput({ scientistName: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wiz-disc-org">Disclosing Organization</Label>
            <Select
              value={singleInput.disclosingOrgId ?? ""}
              onValueChange={(v) => updateSingleInput({ disclosingOrgId: v || null })}
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
              onChange={(e) => updateSingleInput({ notes: e.target.value })}
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

      {/* Projects — optional; hidden in disclosure mode */}
      {!singleInput.disclosureMode && (
        <div className="grid gap-2">
          <Label>
            Projects <span className="text-xs text-muted-foreground">(optional)</span>
          </Label>
          <ProjectFilter
            selectedIds={singleInput.projectIds}
            onChange={(ids) => updateSingleInput({ projectIds: ids })}
          />
        </div>
      )}

      {/* External identifiers — hidden in disclosure mode */}
      {!singleInput.disclosureMode && (
        <div className="grid gap-3">
          <div className="flex items-center justify-between">
            <Label>External Identifiers</Label>
            <Button type="button" variant="outline" size="sm" onClick={handleAddExternalId}>
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
                onValueChange={(v) => handleUpdateExternalId(index, { identifier_type: v })}
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
                onChange={(e) => handleUpdateExternalId(index, { identifier: e.target.value })}
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
      {!singleInput.disclosureMode && customFieldDefs && customFieldDefs.length > 0 && (
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

function detectFileFormat(filename: string): BulkInput["fileFormat"] | null {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (lower.endsWith(".xlsx")) return "xlsx";
  if (lower.endsWith(".sdf") || lower.endsWith(".sd")) return "sdf";
  return null;
}

function BulkInputForm() {
  const bulkInput = useRegistrationWizard((s) => s.bulkInput);
  const updateBulkInput = useRegistrationWizard((s) => s.updateBulkInput);
  const nextStep = useRegistrationWizard((s) => s.nextStep);
  const {
    data: orgs,
    isLoading: organizationsLoading,
    isError: organizationsError,
    refetch: retryOrganizations,
  } = useOrganizations();
  const { data: settings } = useWorkspaceSettings();
  const [error, setError] = useState<string | null>(null);
  const defaultApplied = useRef(false);
  useEffect(() => {
    if (!settings || defaultApplied.current || bulkInput.file) return;
    defaultApplied.current = true;
    const rules = (settings.registration_rules ?? {}) as RegistrationRules;
    updateBulkInput({ createBatchOnDuplicate: rules.create_batch_on_duplicate ?? false });
  }, [settings, bulkInput.file, updateBulkInput]);

  const handleFile = useCallback(
    (file: File) => {
      const format = detectFileFormat(file.name);
      if (!format) {
        setError("Choose a CSV, XLSX, SDF, or SD file.");
        return;
      }
      if (file.size === 0) {
        setError("This file is empty. Choose a file containing compound records.");
        return;
      }
      setError(null);
      updateBulkInput({ file, fileFormat: format });
    },
    [updateBulkInput],
  );
  const prerequisite = !bulkInput.file
    ? "Choose a file to continue."
    : !bulkInput.originatingOrgId
      ? "Choose an originating organization to continue."
      : null;

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <section
        className="min-w-0 rounded-lg border bg-background"
        aria-labelledby="bulk-upload-title"
      >
        <div className="flex flex-wrap items-start justify-between gap-3 border-b px-5 py-4">
          <div>
            <h2 id="bulk-upload-title" className="font-semibold">
              Upload file
            </h2>
            <p className="mt-1 text-sm text-foreground/70">
              Choose your file, then set the defaults for its compounds.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={downloadCsvTemplate}>
            <Download className="size-4" />
            Download CSV template
          </Button>
        </div>
        <div className="space-y-5 p-5">
          <CsvDropzone
            file={bulkInput.file}
            onFile={handleFile}
            compactSelected
            onRemove={() => {
              updateBulkInput({ file: null });
              setError(null);
            }}
            onRejected={setError}
            accept={{
              "text/csv": [".csv"],
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
              "chemical/x-mdl-sdfile": [".sdf", ".sd"],
            }}
            prompt="Drop a file here, or click to browse"
            hint="CSV, XLSX, SDF, or SD"
          />
          {error && (
            <p
              role="alert"
              className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
            >
              {error}
            </p>
          )}
          <div className="grid gap-5 md:grid-cols-2">
            <div className="grid content-start gap-2">
              <Label htmlFor="bulk-org">
                Originating organization{" "}
                <span className="font-normal text-foreground/70">(required)</span>
              </Label>
              <Select
                value={bulkInput.originatingOrgId ?? ""}
                onValueChange={(value) => updateBulkInput({ originatingOrgId: value })}
                disabled={organizationsLoading}
              >
                <SelectTrigger id="bulk-org" className="w-full" aria-describedby="bulk-org-help">
                  <SelectValue
                    placeholder={
                      organizationsLoading ? "Loading organizations…" : "Choose an organization"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {orgs?.map((org) => (
                    <SelectItem key={org.id} value={org.id}>
                      {org.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p id="bulk-org-help" className="text-sm text-foreground/70">
                The source organization for newly registered compounds.
              </p>
              {organizationsError && (
                <p role="alert" className="text-sm text-destructive">
                  Could not load organizations.{" "}
                  <Button variant="link" size="sm" onClick={() => retryOrganizations()}>
                    Try again
                  </Button>
                </p>
              )}
              {!organizationsLoading && orgs?.length === 0 && (
                <p className="text-sm text-destructive">
                  Ask an administrator to add an organization before registering compounds.
                </p>
              )}
            </div>
            <div className="grid content-start gap-2">
              <Label>
                Projects <span className="font-normal text-foreground/70">(optional)</span>
              </Label>
              <div className="min-h-9 rounded-md border p-2">
                <ProjectFilter
                  selectedIds={bulkInput.projectIds}
                  onChange={(ids) => updateBulkInput({ projectIds: ids })}
                  emptyLabel="No projects selected"
                  showScopeStats={false}
                />
              </div>
              <p className="text-sm text-foreground/70">
                New and matched compounds are added to the projects you select.
              </p>
            </div>
          </div>
          <details className="rounded-lg border p-4">
            <summary className="cursor-pointer text-sm font-medium">Batch options</summary>
            <div className="mt-3 flex items-start gap-3">
              <Checkbox
                id="bulk-cbod"
                checked={bulkInput.createBatchOnDuplicate}
                onCheckedChange={(checked) => {
                  defaultApplied.current = true;
                  updateBulkInput({ createBatchOnDuplicate: checked === true });
                }}
                className="mt-1"
                aria-describedby="bulk-batch-help"
              />
              <div className="space-y-2">
                <Label htmlFor="bulk-cbod" className="leading-relaxed">
                  Create batches for existing compounds when no batch ID is supplied
                </Label>
                <p id="bulk-batch-help" className="text-sm text-foreground/70">
                  Batch IDs in the file always create or match their specified batches. This option
                  only affects existing compounds on rows without batch IDs.
                </p>
              </div>
            </div>
          </details>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-4">
          <p id="bulk-upload-prerequisite" className="text-sm text-foreground/70">
            {prerequisite ?? "Next, match your file’s columns to ChemCellar fields."}
          </p>
          <Button
            onClick={nextStep}
            disabled={!!prerequisite}
            aria-describedby="bulk-upload-prerequisite"
          >
            Match columns
          </Button>
        </div>
      </section>
      <BulkUploadSummary />
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
