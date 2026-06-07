"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { SkeletonList } from "@/shared/components/skeleton-list";
import { Badge } from "@/shared/components/ui/badge";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { zodResolver } from "@hookform/resolvers/zod";
import { ClipboardList, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { useCustomFields } from "../hooks/use-custom-fields";
import {
  type CreateRegistrationFormInput,
  type FieldOverride,
  type RegistrationForm,
  type UpdateRegistrationFormInput,
  useCreateRegistrationForm,
  useDeleteRegistrationForm,
  useRegistrationForms,
  useUpdateRegistrationForm,
} from "../hooks/use-registration-forms";

// ---------------------------------------------------------------------------
// Field overrides editor sub-component
// ---------------------------------------------------------------------------

interface FieldOverridesEditorProps {
  appliesTo: "molecule" | "batch";
  overrides: FieldOverride[];
  onChange: (overrides: FieldOverride[]) => void;
}

function FieldOverridesEditor({ appliesTo, overrides, onChange }: FieldOverridesEditorProps) {
  const { data: fields, isLoading } = useCustomFields(appliesTo, true);

  if (isLoading) {
    return <SkeletonList rowClassName="h-10 w-full" className="space-y-2" />;
  }

  if (!fields || fields.length === 0) {
    return (
      <p className="py-3 text-sm text-muted-foreground">
        No custom fields defined for {appliesTo}. Add custom fields in the Custom Fields admin page.
      </p>
    );
  }

  const getOverride = (fieldId: string): FieldOverride | undefined =>
    overrides.find((o) => o.field_definition_id === fieldId);

  const setOverrideField = <K extends keyof FieldOverride>(
    fieldId: string,
    key: K,
    value: FieldOverride[K],
  ) => {
    const existing = overrides.find((o) => o.field_definition_id === fieldId);
    if (existing) {
      onChange(
        overrides.map((o) => (o.field_definition_id === fieldId ? { ...o, [key]: value } : o)),
      );
    } else {
      onChange([...overrides, { field_definition_id: fieldId, [key]: value } as FieldOverride]);
    }
  };

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Field</TableHead>
            <TableHead className="w-[110px] text-center">Required</TableHead>
            <TableHead className="w-[150px]">Default Value</TableHead>
            <TableHead className="w-[90px] text-center">Locked</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((field) => {
            const override = getOverride(field.id);
            const isRequired = override?.is_required ?? null;
            const isLocked = override?.is_locked ?? false;
            const defaultVal =
              override?.default_value != null ? String(override.default_value) : "";

            return (
              <TableRow key={field.id}>
                <TableCell>
                  <div>
                    <span className="font-medium text-sm">{field.label}</span>
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {field.name}
                    </span>
                    {field.is_required && (
                      <Badge variant="secondary" className="ml-2 text-xs">
                        Required by default
                      </Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-center">
                  <Switch
                    checked={isRequired === true}
                    onCheckedChange={(checked) =>
                      setOverrideField(field.id, "is_required", checked || null)
                    }
                    aria-label={`Override required for ${field.label}`}
                  />
                </TableCell>
                <TableCell>
                  <Input
                    value={defaultVal}
                    onChange={(e) =>
                      setOverrideField(field.id, "default_value", e.target.value || undefined)
                    }
                    placeholder="Override default..."
                    className="h-7 text-xs"
                  />
                </TableCell>
                <TableCell className="text-center">
                  <Switch
                    checked={isLocked}
                    onCheckedChange={(checked) => setOverrideField(field.id, "is_locked", checked)}
                    aria-label={`Lock field ${field.label}`}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Form dialog (create / edit)
// ---------------------------------------------------------------------------

const formSchema = z.object({
  name: z.string().min(1, "Name is required"),
  applies_to: z.enum(["molecule", "batch"]),
  is_default: z.boolean(),
  field_overrides: z.array(z.custom<FieldOverride>()),
});

type FormValues = z.infer<typeof formSchema>;

const defaultValues: FormValues = {
  name: "",
  applies_to: "molecule",
  is_default: false,
  field_overrides: [],
};

function toFormValues(editing: RegistrationForm): FormValues {
  return {
    name: editing.name,
    // Backend types `applies_to` as bare `str`; narrow to the form's values.
    applies_to: editing.applies_to as "molecule" | "batch",
    is_default: editing.is_default,
    // `field_overrides` is an opaque `{ [key: string]: unknown }[]` from the
    // backend (typed `list[dict]`); read it as the FE's structured override view.
    field_overrides: (editing.field_overrides ?? []) as unknown as FieldOverride[],
  };
}

interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: RegistrationForm | null;
}

function FormDialog({ open, onOpenChange, editing }: FormDialogProps) {
  const isEdit = editing !== null;
  const create = useCreateRegistrationForm();
  const update = useUpdateRegistrationForm(editing?.id ?? "");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  useEffect(() => {
    if (open) {
      form.reset(editing ? toFormValues(editing) : defaultValues);
    }
  }, [open, editing, form]);

  const onSubmit = async (values: FormValues) => {
    // The backend `field_overrides` body field is an opaque `list[dict]`; widen
    // the FE's structured overrides back to that generated record-array shape.
    const fieldOverrides = values.field_overrides as unknown as Array<Record<string, unknown>>;
    if (isEdit) {
      const data: UpdateRegistrationFormInput = {
        name: values.name.trim(),
        is_default: values.is_default,
        field_overrides: fieldOverrides,
      };
      await update.mutateAsync(data);
    } else {
      const data: CreateRegistrationFormInput = {
        name: values.name.trim(),
        applies_to: values.applies_to,
        is_default: values.is_default,
        field_overrides: fieldOverrides,
      };
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;
  const watchedAppliesTo = form.watch("applies_to");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Registration Form" : "New Registration Form"}</DialogTitle>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="rf-name">Form Name</Label>
              <Input
                id="rf-name"
                {...form.register("name")}
                placeholder="e.g., Standard Molecule Registration"
              />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
              )}
            </div>

            {/* Applies to — only for create */}
            {!isEdit ? (
              <div className="grid gap-2">
                <Label>Applies To</Label>
                <Controller
                  name="applies_to"
                  control={form.control}
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="molecule">Molecule</SelectItem>
                        <SelectItem value="batch">Batch</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
            ) : (
              <div className="grid gap-2">
                <Label>Applies To</Label>
                <Input value={editing!.applies_to === "molecule" ? "Molecule" : "Batch"} disabled />
              </div>
            )}

            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <div>
                <Label htmlFor="rf-default" className="cursor-pointer">
                  Set as default form
                </Label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Default form is pre-selected in the registration dialog.
                </p>
              </div>
              <Controller
                name="is_default"
                control={form.control}
                render={({ field }) => (
                  <Switch id="rf-default" checked={field.value} onCheckedChange={field.onChange} />
                )}
              />
            </div>

            {/* Field overrides */}
            <div className="grid gap-2">
              <Label>Field Overrides</Label>
              <p className="text-xs text-muted-foreground">
                Override required/default/locked behaviour for individual custom fields when this
                form is selected.
              </p>
              <Controller
                name="field_overrides"
                control={form.control}
                render={({ field }) => (
                  <FieldOverridesEditor
                    appliesTo={
                      isEdit ? (editing!.applies_to as "molecule" | "batch") : watchedAppliesTo
                    }
                    overrides={field.value}
                    onChange={field.onChange}
                  />
                )}
              />
            </div>
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

// ---------------------------------------------------------------------------
// Delete confirmation dialog
// ---------------------------------------------------------------------------

interface DeleteDialogProps {
  form: RegistrationForm | null;
  onOpenChange: (open: boolean) => void;
}

function DeleteDialog({ form, onOpenChange }: DeleteDialogProps) {
  const deleteMutation = useDeleteRegistrationForm();

  const handleConfirm = async () => {
    if (!form) return;
    await deleteMutation.mutateAsync(form.id);
    onOpenChange(false);
  };

  return (
    <Dialog open={form !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Registration Form?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Permanently delete <span className="font-medium text-foreground">{form?.name}</span>? This
          action cannot be undone.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={deleteMutation.isPending}>
            {deleteMutation.isPending ? "Deleting..." : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Forms table
// ---------------------------------------------------------------------------

interface FormsTableProps {
  forms: RegistrationForm[];
  onEdit: (form: RegistrationForm) => void;
  onDelete: (form: RegistrationForm) => void;
}

function FormsTable({ forms, onEdit, onDelete }: FormsTableProps) {
  if (forms.length === 0) {
    return (
      <EmptyState
        variant="inline"
        icon={ClipboardList}
        title="No registration forms defined yet."
      />
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Applies To</TableHead>
            <TableHead>Default</TableHead>
            <TableHead>Field Overrides</TableHead>
            <TableHead className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {forms.map((form) => (
            <TableRow key={form.id}>
              <TableCell className="font-medium">{form.name}</TableCell>
              <TableCell>
                <Badge variant="outline" className="capitalize">
                  {form.applies_to}
                </Badge>
              </TableCell>
              <TableCell>
                {form.is_default ? (
                  <Badge variant="secondary" className="text-xs">
                    Default
                  </Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <span className="text-sm tabular-nums">{form.field_overrides?.length ?? 0}</span>
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => onEdit(form)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  {!form.is_default && (
                    <Button variant="ghost" size="sm" onClick={() => onDelete(form)}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RegistrationFormAdmin — main component
// ---------------------------------------------------------------------------

import { useState } from "react";

export function RegistrationFormAdmin() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<RegistrationForm | null>(null);
  const [deleting, setDeleting] = useState<RegistrationForm | null>(null);

  const { data: forms, isLoading } = useRegistrationForms();

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (form: RegistrationForm) => {
    setEditing(form);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Registration Forms"
        subtitle="Define registration form templates with custom field overrides for molecule and batch registration."
      >
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add Form
        </Button>
      </PageHeader>

      <div className="mt-6">
        {isLoading ? (
          <SkeletonList rows={4} />
        ) : (
          <FormsTable forms={forms ?? []} onEdit={openEdit} onDelete={setDeleting} />
        )}
      </div>

      <FormDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} />

      <DeleteDialog form={deleting} onOpenChange={(open) => !open && setDeleting(null)} />
    </>
  );
}
