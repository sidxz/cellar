"use client";

import { MOLECULE_TYPE_LABELS } from "@/features/chemical-registration/types";
import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
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
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { useUpdateWorkspaceSettings, useWorkspaceSettings } from "../hooks/use-workspace-settings";
import type { AuditReasonPolicy, CustomFieldDefinition } from "../types";
import { CustomFieldBuilder } from "./custom-field-builder";

// ── Schema ────────────────────────────────────────────────────────────────────

const schema = z.object({
  defaultMolType: z.string(),
  retentionDays: z.string(),
  auditReasonPolicy: z.enum(["always", "never", "configurable"]),
  sigRequired: z.array(z.string()),
  formulationScheme: z.string(),
  customFields: z.array(
    z.object({
      name: z.string(),
      label: z.string(),
      data_type: z.enum(["text", "number", "date", "select"]),
      required: z.boolean(),
      vocabulary_name: z.string().nullable().optional(),
    }),
  ),
  createBatchOnDup: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

// ── Constants ─────────────────────────────────────────────────────────────────

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

  const {
    register,
    handleSubmit,
    control,
    reset,
    setValue,
    formState: { isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      defaultMolType: "",
      retentionDays: "",
      auditReasonPolicy: "never",
      sigRequired: [],
      formulationScheme: "",
      customFields: [],
      createBatchOnDup: false,
    },
  });

  // Seed from server data on load / refresh
  useEffect(() => {
    if (settings) {
      reset({
        defaultMolType: settings.default_molecule_type ?? "",
        retentionDays: settings.audit_retention_days?.toString() ?? "",
        auditReasonPolicy: (settings.audit_reason_policy as AuditReasonPolicy) ?? "never",
        sigRequired: settings.signature_required_for ?? [],
        formulationScheme: settings.formulation_number_scheme ?? "",
        customFields: Array.isArray(settings.custom_field_definitions)
          ? (settings.custom_field_definitions as CustomFieldDefinition[])
          : [],
        createBatchOnDup: !!settings.registration_rules?.create_batch_on_duplicate,
      });
    }
  }, [settings, reset]);

  const sigRequired = useWatch({ control, name: "sigRequired" });

  const toggleSigRequired = (op: string) => {
    const next = sigRequired.includes(op)
      ? sigRequired.filter((o) => o !== op)
      : [...sigRequired, op];
    setValue("sigRequired", next, { shouldDirty: true });
  };

  const onSubmit = async (values: FormValues) => {
    await update.mutateAsync({
      default_molecule_type: values.defaultMolType || null,
      audit_retention_days: values.retentionDays ? Number.parseInt(values.retentionDays, 10) : null,
      audit_reason_policy: values.auditReasonPolicy,
      signature_required_for: values.sigRequired,
      formulation_number_scheme: values.formulationScheme || null,
      custom_field_definitions: values.customFields.filter((f) => f.name.trim()),
      registration_rules: {
        ...(settings?.registration_rules ?? {}),
        create_batch_on_duplicate: values.createBatchOnDup,
      },
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Workspace Settings"
        subtitle="Configure registration rules, audit policies, and workspace-level defaults."
      />

      <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-6">
        {/* General */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold">General</h2>
          <div className="mt-4 grid gap-6 max-w-lg">
            <div className="grid gap-2">
              <Label>Default Molecule Type</Label>
              <Controller
                name="defaultMolType"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select default type..." />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(MOLECULE_TYPE_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              <p className="text-xs text-muted-foreground">
                Default molecule type for new registrations.
              </p>
            </div>

            <div className="grid gap-2">
              <Label>Formulation Number Scheme</Label>
              <Input {...register("formulationScheme")} placeholder="e.g., FRM-{YYYY}-{SEQ:4}" />
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
                  When off, registering the same compound again only merges new identifiers and
                  synonyms — no new batch is created. Override per-import in the bulk and CDD
                  wizards.
                </p>
              </div>
              <Controller
                name="createBatchOnDup"
                control={control}
                render={({ field }) => (
                  <Switch id="cbod" checked={field.value} onCheckedChange={field.onChange} />
                )}
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
              </a>
              .
            </p>
          </div>
        </Card>

        {/* Audit & Compliance */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Audit & Compliance</h2>
          <div className="mt-4 grid gap-6 max-w-lg">
            <div className="grid gap-2">
              <Label>Audit Reason Policy</Label>
              <Controller
                name="auditReasonPolicy"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
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
                )}
              />
              <p className="text-xs text-muted-foreground">
                Whether users must provide a reason for audit-tracked operations.
              </p>
            </div>

            <div className="grid gap-2">
              <Label>Audit Retention (days)</Label>
              <Input type="number" {...register("retentionDays")} placeholder="Unlimited" />
              <p className="text-xs text-muted-foreground">Leave empty for unlimited retention.</p>
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
            Define additional fields that appear on the compound registration form. Select-type
            fields can reference controlled vocabularies.
          </p>
          <Separator className="my-4" />
          <Controller
            name="customFields"
            control={control}
            render={({ field }) => (
              <CustomFieldBuilder fields={field.value} onChange={field.onChange} />
            )}
          />
        </Card>

        {/* Save */}
        <div className="flex justify-end">
          <Button type="submit" disabled={isSubmitting || update.isPending}>
            {update.isPending ? "Saving..." : "Save Settings"}
          </Button>
        </div>
      </form>
    </div>
  );
}
