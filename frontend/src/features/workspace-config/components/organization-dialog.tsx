"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
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
import { Switch } from "@/shared/components/ui/switch";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { useCreateOrganization, useUpdateOrganization } from "../hooks/use-organizations";
import { ORG_TYPE_LABELS, type Organization, type OrganizationType } from "../types";

// ── Schema ────────────────────────────────────────────────────────────────────

const ORG_TYPES = Object.entries(ORG_TYPE_LABELS) as [OrganizationType, string][];

const formSchema = z.object({
  name: z.string().min(1, "Name is required"),
  org_type: z.string().min(1, "Type is required"),
  contact_name: z.string().optional(),
  contact_email: z.string().optional(),
  notes: z.string().optional(),
  is_active: z.boolean(),
});

type FormValues = z.infer<typeof formSchema>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const defaultValues: FormValues = {
  name: "",
  org_type: "internal",
  contact_name: "",
  contact_email: "",
  notes: "",
  is_active: true,
};

function toFormValues(org: Organization): FormValues {
  return {
    name: org.name,
    org_type: org.org_type,
    contact_name: org.contact_name ?? "",
    contact_email: org.contact_email ?? "",
    notes: org.notes ?? "",
    is_active: org.is_active,
  };
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organization: Organization | null;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function OrganizationDialog({ open, onOpenChange, organization }: Props) {
  const create = useCreateOrganization();
  const update = useUpdateOrganization(organization?.id ?? "");
  const isEdit = organization !== null;

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  useEffect(() => {
    if (open) {
      form.reset(organization ? toFormValues(organization) : defaultValues);
    }
  }, [open, organization, form]);

  const onSubmit = async (values: FormValues) => {
    const data = {
      name: values.name,
      org_type: values.org_type as OrganizationType,
      contact_name: values.contact_name || null,
      contact_email: values.contact_email || null,
      notes: values.notes || null,
    };
    // NOTE: the backend UpdateOrganizationBody does not accept `is_active`
    // (model_config extra="forbid") — there is no activate/deactivate field on
    // this endpoint, so it is intentionally not sent here. See residual issues.
    if (isEdit) {
      await update.mutateAsync(data);
    } else {
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Organization" : "New Organization"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="org-name">Name</Label>
              <Input id="org-name" {...form.register("name")} placeholder="e.g., Eurofins Munich" />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
              )}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="org-type">Type</Label>
              <Controller
                name="org_type"
                control={form.control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ORG_TYPES.map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="contact-name">Contact Name</Label>
              <Input id="contact-name" {...form.register("contact_name")} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="contact-email">Contact Email</Label>
              <Input id="contact-email" type="email" {...form.register("contact_email")} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="notes">Notes</Label>
              <Input id="notes" {...form.register("notes")} />
            </div>

            {isEdit && (
              <div className="flex items-center gap-2">
                <Controller
                  name="is_active"
                  control={form.control}
                  render={({ field }) => (
                    <Switch id="is-active" checked={field.value} onCheckedChange={field.onChange} />
                  )}
                />
                <Label htmlFor="is-active">Active</Label>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={form.formState.isSubmitting || isPending}>
              {isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
