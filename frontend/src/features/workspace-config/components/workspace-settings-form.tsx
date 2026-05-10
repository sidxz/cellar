"use client";

import { useEffect, useState } from "react";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { PageHeader } from "@/shared/components/page-header";
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
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Switch } from "@/shared/components/ui/switch";
import { MOLECULE_TYPE_LABELS } from "@/features/chemical-registration/types";
import {
  useUpdateWorkspaceSettings,
  useWorkspaceSettings,
} from "../hooks/use-workspace-settings";
import type { AuditReasonPolicy, CustomFieldDefinition } from "../types";
import { CustomFieldBuilder } from "./custom-field-builder";

const AUDIT_REASON_OPTIONS: { value: AuditReasonPolicy; label: string }[] = [
  { value: "always", label: "Always require reason" },
  { value: "never", label: "Never require reason" },
  { value: "configurable", label: "Configurable per operation" },
];

const SIGNATURE_OPERATIONS = [
  "registration",
  "disclosure",
  "merge",
  "data_lock",
  "batch_creation",
  "sample_disposal",
];

export function WorkspaceSettingsForm() {
  const { data: settings, isLoading } = useWorkspaceSettings();
  const update = useUpdateWorkspaceSettings();

  const [defaultMolType, setDefaultMolType] = useState("");
  const [retentionDays, setRetentionDays] = useState("");
  const [auditReasonPolicy, setAuditReasonPolicy] =
    useState<AuditReasonPolicy>("never");
  const [sigRequired, setSigRequired] = useState<string[]>([]);
  const [formulationScheme, setFormulationScheme] = useState("");
  const [customFields, setCustomFields] = useState<CustomFieldDefinition[]>([]);
  const [createBatchOnDup, setCreateBatchOnDup] = useState(false);

  useEffect(() => {
    if (settings) {
      setDefaultMolType(settings.default_molecule_type ?? "");
      setRetentionDays(settings.audit_retention_days?.toString() ?? "");
      setAuditReasonPolicy(
        (settings.audit_reason_policy as AuditReasonPolicy) ?? "never"
      );
      setSigRequired(settings.signature_required_for ?? []);
      setFormulationScheme(settings.formulation_number_scheme ?? "");
      setCustomFields(
        Array.isArray(settings.custom_field_definitions)
          ? settings.custom_field_definitions
          : []
      );
      setCreateBatchOnDup(
        !!settings.registration_rules?.create_batch_on_duplicate
      );
    }
  }, [settings]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const handleSave = async () => {
    await update.mutateAsync({
      default_molecule_type: defaultMolType || null,
      audit_retention_days: retentionDays ? parseInt(retentionDays, 10) : null,
      audit_reason_policy: auditReasonPolicy,
      signature_required_for: sigRequired,
      formulation_number_scheme: formulationScheme || null,
      custom_field_definitions: customFields.filter((f) => f.name.trim()),
      registration_rules: {
        ...(settings?.registration_rules ?? {}),
        create_batch_on_duplicate: createBatchOnDup,
      },
    });
  };

  const toggleSigRequired = (op: string) => {
    setSigRequired((prev) =>
      prev.includes(op) ? prev.filter((o) => o !== op) : [...prev, op]
    );
  };

  return (
    <div>
      <PageHeader
        title="Workspace Settings"
        subtitle="Configure registration rules, audit policies, and workspace-level defaults."
      />

      <div className="mt-6 space-y-6">
        {/* General */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold">General</h2>
          <div className="mt-4 grid gap-6 max-w-lg">
            <div className="grid gap-2">
              <Label>Default Molecule Type</Label>
              <Select value={defaultMolType} onValueChange={setDefaultMolType}>
                <SelectTrigger>
                  <SelectValue placeholder="Select default type..." />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(MOLECULE_TYPE_LABELS).map(
                    ([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    )
                  )}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Default molecule type for new registrations.
              </p>
            </div>

            <div className="grid gap-2">
              <Label>Formulation Number Scheme</Label>
              <Input
                value={formulationScheme}
                onChange={(e) => setFormulationScheme(e.target.value)}
                placeholder="e.g., FRM-{YYYY}-{SEQ:4}"
              />
              <p className="text-xs text-muted-foreground">
                Pattern for auto-generated formulation numbers.
              </p>
            </div>
          </div>
        </Card>

        {/* Registration */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Registration</h2>
          <div className="mt-4 grid gap-6 max-w-lg">
            <div className="flex items-start justify-between gap-4">
              <div>
                <Label htmlFor="cbod">Create batch on re-registration</Label>
                <p className="text-xs text-muted-foreground mt-1">
                  When off, registering the same compound again only merges new
                  identifiers and synonyms — no new batch is created. Override
                  per-import in the bulk and CDD wizards.
                </p>
              </div>
              <Switch
                id="cbod"
                checked={createBatchOnDup}
                onCheckedChange={setCreateBatchOnDup}
              />
            </div>
          </div>
        </Card>

        {/* Integrations */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Integrations</h2>
          <div className="mt-4 grid gap-6 max-w-lg">
            <p className="text-sm text-muted-foreground">
              External data sources are managed in{" "}
              <a href="/admin/data-sources" className="underline text-primary">
                Data Sources
              </a>.
            </p>
          </div>
        </Card>

        {/* Audit & Compliance */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Audit & Compliance</h2>
          <div className="mt-4 grid gap-6 max-w-lg">
            <div className="grid gap-2">
              <Label>Audit Reason Policy</Label>
              <Select
                value={auditReasonPolicy}
                onValueChange={(v) =>
                  setAuditReasonPolicy(v as AuditReasonPolicy)
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AUDIT_REASON_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Whether users must provide a reason for audit-tracked
                operations.
              </p>
            </div>

            <div className="grid gap-2">
              <Label>Audit Retention (days)</Label>
              <Input
                type="number"
                value={retentionDays}
                onChange={(e) => setRetentionDays(e.target.value)}
                placeholder="Unlimited"
              />
              <p className="text-xs text-muted-foreground">
                Leave empty for unlimited retention.
              </p>
            </div>

            <div className="grid gap-2">
              <Label>Signature Required For</Label>
              <div className="flex flex-wrap gap-2">
                {SIGNATURE_OPERATIONS.map((op) => (
                  <Button
                    key={op}
                    type="button"
                    variant={sigRequired.includes(op) ? "default" : "outline"}
                    size="sm"
                    onClick={() => toggleSigRequired(op)}
                  >
                    {op.replace(/_/g, " ")}
                  </Button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Operations requiring electronic signature (21 CFR Part 11).
              </p>
            </div>
          </div>
        </Card>

        {/* Custom Fields */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Custom Field Definitions</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Define additional fields that appear on the compound registration
            form. Select-type fields can reference controlled vocabularies.
          </p>
          <Separator className="my-4" />
          <CustomFieldBuilder
            fields={customFields}
            onChange={setCustomFields}
          />
        </Card>

        {/* Save */}
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={update.isPending}>
            {update.isPending ? "Saving..." : "Save Settings"}
          </Button>
        </div>
      </div>
    </div>
  );
}
