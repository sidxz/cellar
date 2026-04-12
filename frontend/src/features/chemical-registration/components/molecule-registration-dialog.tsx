"use client";

import { useState, useMemo } from "react";
import { Pencil } from "lucide-react";
import { StructureEditorDialog } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { Switch } from "@/shared/components/ui/switch";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useWorkspaceSettings } from "@/features/workspace-config/hooks/use-workspace-settings";
import { useRegistrationForms } from "@/features/workspace-config/hooks/use-registration-forms";
import { CustomFieldsRenderer } from "@/features/workspace-config/components/custom-fields-renderer";
import { useCustomFields } from "@/features/workspace-config/hooks/use-custom-fields";
import { useSaltCatalog } from "@/features/workspace-config/hooks/use-salt-catalog";
import { useRegisterMolecule } from "../hooks/use-molecules";
import { MOLECULE_TYPE_LABELS } from "../types";

interface MoleculeRegistrationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MoleculeRegistrationDialog({
  open,
  onOpenChange,
}: MoleculeRegistrationDialogProps) {
  const { data: orgs } = useOrganizations();
  const { data: settings } = useWorkspaceSettings();
  const { data: registrationForms } = useRegistrationForms("molecule");
  const { data: customFieldDefs } = useCustomFields("molecule", true);
  const registerMutation = useRegisterMolecule();
  const { data: saltEntries } = useSaltCatalog(true);

  const defaultFormId =
    registrationForms?.find((f) => f.is_default)?.id ?? "";
  const [selectedFormId, setSelectedFormId] = useState<string>("");

  // Derive active form overrides from selected form
  const activeFormOverrides =
    registrationForms?.find(
      (f) => f.id === (selectedFormId || defaultFormId)
    )?.field_overrides ?? [];

  const [name, setName] = useState("");
  const [smiles, setSmiles] = useState("");
  const [moleculeType, setMoleculeType] = useState<string>(
    settings?.default_molecule_type ?? "small_molecule"
  );
  const [orgId, setOrgId] = useState<string>("");
  const [isUndisclosed, setIsUndisclosed] = useState(false);
  const [extIdValue, setExtIdValue] = useState("");
  const [extIdType, setExtIdType] = useState<string>("vendor_id");
  const [includeBatch, setIncludeBatch] = useState(false);
  const [batchSource, setBatchSource] = useState("synthesized");
  const [batchAmount, setBatchAmount] = useState("");
  const [batchUnit, setBatchUnit] = useState("mg");
  const [batchPurity, setBatchPurity] = useState("");
  const [batchAppearance, setBatchAppearance] = useState("");
  const [batchSaltEntryId, setBatchSaltEntryId] = useState<string>("__none__");
  const [batchStoichiometry, setBatchStoichiometry] = useState<number>(1);
  const [customFieldValues, setCustomFieldValues] = useState<
    Record<string, string>
  >({});
  const selectedBatchSalt = useMemo(
    () =>
      batchSaltEntryId !== "__none__"
        ? saltEntries?.find((e) => e.id === batchSaltEntryId)
        : undefined,
    [batchSaltEntryId, saltEntries]
  );
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);

  const reset = () => {
    setSelectedFormId("");
    setName("");
    setSmiles("");
    setMoleculeType(settings?.default_molecule_type ?? "small_molecule");
    setOrgId("");
    setIsUndisclosed(false);
    setExtIdValue("");
    setExtIdType("vendor_id");
    setIncludeBatch(false);
    setBatchSource("synthesized");
    setBatchAmount("");
    setBatchUnit("mg");
    setBatchPurity("");
    setBatchAppearance("");
    setBatchSaltEntryId("__none__");
    setBatchStoichiometry(1);
    setCustomFieldValues({});
    setEditorOpen(false);
    setError(null);
  };

  const handleSubmit = async () => {
    setError(null);
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!orgId) {
      setError("Organization is required");
      return;
    }
    if (!isUndisclosed && !smiles.trim()) {
      setError("SMILES is required for disclosed compounds");
      return;
    }

    // Validate required custom fields (based on active form overrides or field definitions)
    for (const field of customFieldDefs ?? []) {
      const override = activeFormOverrides.find(
        (o) => o.field_definition_id === field.id
      );
      const isRequired = override?.is_required ?? field.is_required;
      if (isRequired && !String(customFieldValues[field.name] ?? "").trim()) {
        setError(`${field.label} is required`);
        return;
      }
    }

    try {
      const external_ids = extIdValue.trim()
        ? [{ identifier: extIdValue.trim(), identifier_type: extIdType }]
        : [];
      const batch =
        includeBatch && batchAmount
          ? {
              source: batchSource,
              amount_value: parseFloat(batchAmount),
              amount_unit: batchUnit,
              purity: batchPurity ? parseFloat(batchPurity) : null,
              appearance: batchAppearance || null,
              supplier_org_id: orgId || null,
              salt_entry_id: selectedBatchSalt?.id ?? null,
              salt_name: selectedBatchSalt?.name ?? null,
              salt_smiles: selectedBatchSalt?.smiles ?? null,
              salt_stoichiometry: selectedBatchSalt ? batchStoichiometry : 1,
            }
          : null;
      await registerMutation.mutateAsync({
        name: name.trim(),
        smiles: isUndisclosed ? null : smiles.trim(),
        molecule_type: moleculeType,
        external_ids,
        originating_org_id: orgId,
        custom_fields: Object.keys(customFieldValues).length
          ? customFieldValues
          : undefined,
        batch,
      });
      reset();
      onOpenChange(false);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Registration failed";
      setError(message);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Register Compound</DialogTitle>
          <DialogDescription>
            Register a new chemical compound in the workspace.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Registration form selector */}
          {registrationForms && registrationForms.length > 0 && (
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

          <div className="grid gap-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              placeholder="e.g. Aspirin"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-2">
            <Switch
              id="undisclosed"
              checked={isUndisclosed}
              onCheckedChange={setIsUndisclosed}
            />
            <Label htmlFor="undisclosed">Undisclosed (no structure)</Label>
          </div>

          {!isUndisclosed && (
            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="smiles">SMILES</Label>
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
                id="smiles"
                placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
                value={smiles}
                onChange={(e) => setSmiles(e.target.value)}
                rows={2}
                className="font-mono text-sm"
              />

              <StructureEditorDialog
                open={editorOpen}
                onOpenChange={setEditorOpen}
                initialStructure={smiles}
                onApply={(s) => setSmiles(s)}
                outputFormat="smiles"
              />
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="type">Molecule Type</Label>
            <Select value={moleculeType} onValueChange={setMoleculeType}>
              <SelectTrigger id="type">
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

          <div className="grid gap-2">
            <Label htmlFor="org">Originating Organization</Label>
            <Select value={orgId} onValueChange={setOrgId}>
              <SelectTrigger id="org">
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

          {/* External Identifier (optional) */}
          <div className="grid gap-2">
            <Label>External Identifier</Label>
            <div className="flex gap-2">
              <Select value={extIdType} onValueChange={setExtIdType}>
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="vendor_id">Vendor ID</SelectItem>
                  <SelectItem value="cas_number">CAS Number</SelectItem>
                  <SelectItem value="chembl_id">ChEMBL ID</SelectItem>
                  <SelectItem value="pubchem_cid">PubChem CID</SelectItem>
                  <SelectItem value="custom">Custom</SelectItem>
                </SelectContent>
              </Select>
              <Input
                placeholder="e.g. ABBVIE-002, 50-78-2"
                value={extIdValue}
                onChange={(e) => setExtIdValue(e.target.value)}
                className="flex-1"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Optional. If this structure already exists, the identifier will be
              added to the existing compound.
            </p>
          </div>

          {/* Optional Batch */}
          <div className="flex items-center gap-2">
            <Switch
              id="include-batch"
              checked={includeBatch}
              onCheckedChange={setIncludeBatch}
            />
            <Label htmlFor="include-batch">Include initial batch</Label>
          </div>

          {includeBatch && (
            <div className="grid gap-3 rounded-lg border border-dashed p-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1">
                  <Label className="text-xs">Amount</Label>
                  <Input
                    type="number"
                    placeholder="e.g. 100"
                    value={batchAmount}
                    onChange={(e) => setBatchAmount(e.target.value)}
                  />
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Unit</Label>
                  <Select value={batchUnit} onValueChange={setBatchUnit}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mg">mg</SelectItem>
                      <SelectItem value="g">g</SelectItem>
                      <SelectItem value="kg">kg</SelectItem>
                      <SelectItem value="uL">uL</SelectItem>
                      <SelectItem value="mL">mL</SelectItem>
                      <SelectItem value="L">L</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1">
                  <Label className="text-xs">Source</Label>
                  <Select value={batchSource} onValueChange={setBatchSource}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="synthesized">Synthesized</SelectItem>
                      <SelectItem value="purchased">Purchased</SelectItem>
                      <SelectItem value="donated">Donated</SelectItem>
                      <SelectItem value="natural_extract">Natural Extract</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Purity (%)</Label>
                  <Input
                    type="number"
                    placeholder="e.g. 99.5"
                    value={batchPurity}
                    onChange={(e) => setBatchPurity(e.target.value)}
                  />
                </div>
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Salt Form</Label>
                <Select value={batchSaltEntryId} onValueChange={setBatchSaltEntryId}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">None / Free base</SelectItem>
                    {saltEntries?.map((entry) => (
                      <SelectItem key={entry.id} value={entry.id}>
                        {entry.code} &mdash; {entry.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {selectedBatchSalt && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="grid gap-1">
                    <Label className="text-xs">Stoichiometry</Label>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      value={batchStoichiometry}
                      onChange={(e) =>
                        setBatchStoichiometry(Math.max(1, parseInt(e.target.value) || 1))
                      }
                    />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Salt MW</Label>
                    <Input
                      readOnly
                      value={selectedBatchSalt.molecular_weight.toFixed(2)}
                      className="bg-muted"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Custom fields — rendered via CustomFieldsRenderer with form overrides */}
          {customFieldDefs && customFieldDefs.length > 0 && (
            <div className="grid gap-2">
              <Label>Custom Fields</Label>
              <CustomFieldsRenderer
                definitions={customFieldDefs}
                formOverrides={activeFormOverrides}
                values={customFieldValues}
                onChange={(vals) =>
                  setCustomFieldValues(vals as Record<string, string>)
                }
              />
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={registerMutation.isPending}
          >
            {registerMutation.isPending ? "Registering..." : "Register"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
