"use client";

import { useState } from "react";
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
import { useVocabularies } from "@/features/workspace-config/hooks/use-vocabularies";
import { useWorkspaceSettings } from "@/features/workspace-config/hooks/use-workspace-settings";
import type { CustomFieldDefinition } from "@/features/workspace-config/types";
import { useRegisterMolecule } from "../hooks/use-molecules";
import { MOLECULE_TYPE_LABELS, type MoleculeType } from "../types";

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
  const { data: vocabularies } = useVocabularies();
  const registerMutation = useRegisterMolecule();

  const [name, setName] = useState("");
  const [smiles, setSmiles] = useState("");
  const [moleculeType, setMoleculeType] = useState<string>(
    settings?.default_molecule_type ?? "small_molecule"
  );
  const [orgId, setOrgId] = useState<string>("");
  const [isUndisclosed, setIsUndisclosed] = useState(false);
  const [extIdValue, setExtIdValue] = useState("");
  const [extIdType, setExtIdType] = useState<string>("vendor_id");
  const [customFieldValues, setCustomFieldValues] = useState<
    Record<string, string>
  >({});
  const [error, setError] = useState<string | null>(null);

  const customFields: CustomFieldDefinition[] = Array.isArray(
    settings?.custom_field_definitions
  )
    ? settings.custom_field_definitions
    : [];

  const reset = () => {
    setName("");
    setSmiles("");
    setMoleculeType(settings?.default_molecule_type ?? "small_molecule");
    setOrgId("");
    setIsUndisclosed(false);
    setExtIdValue("");
    setExtIdType("vendor_id");
    setCustomFieldValues({});
    setError(null);
  };

  const getVocabTerms = (vocabName: string | null | undefined): string[] => {
    if (!vocabName || !vocabularies) return [];
    return vocabularies.find((v) => v.name === vocabName)?.terms ?? [];
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

    // Validate required custom fields
    for (const field of customFields) {
      if (field.required && !customFieldValues[field.name]?.trim()) {
        setError(`${field.label} is required`);
        return;
      }
    }

    try {
      const external_ids = extIdValue.trim()
        ? [{ identifier: extIdValue.trim(), identifier_type: extIdType }]
        : [];
      await registerMutation.mutateAsync({
        name: name.trim(),
        smiles: isUndisclosed ? null : smiles.trim(),
        molecule_type: moleculeType,
        external_ids,
        originating_org_id: orgId,
        custom_fields: Object.keys(customFieldValues).length
          ? customFieldValues
          : undefined,
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
              <Label htmlFor="smiles">SMILES</Label>
              <Textarea
                id="smiles"
                placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
                value={smiles}
                onChange={(e) => setSmiles(e.target.value)}
                rows={2}
                className="font-mono text-sm"
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

          {/* Custom fields from workspace settings */}
          {customFields.map((field) => (
            <div key={field.name} className="grid gap-2">
              <Label>
                {field.label}
                {field.required && (
                  <span className="ml-1 text-destructive">*</span>
                )}
              </Label>
              {field.data_type === "select" ? (
                <Select
                  value={customFieldValues[field.name] ?? ""}
                  onValueChange={(v) =>
                    setCustomFieldValues((prev) => ({
                      ...prev,
                      [field.name]: v,
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder={`Select ${field.label}...`} />
                  </SelectTrigger>
                  <SelectContent>
                    {getVocabTerms(field.vocabulary_name).map((term) => (
                      <SelectItem key={term} value={term}>
                        {term}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  type={field.data_type === "number" ? "number" : field.data_type === "date" ? "date" : "text"}
                  value={customFieldValues[field.name] ?? ""}
                  onChange={(e) =>
                    setCustomFieldValues((prev) => ({
                      ...prev,
                      [field.name]: e.target.value,
                    }))
                  }
                />
              )}
            </div>
          ))}

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
