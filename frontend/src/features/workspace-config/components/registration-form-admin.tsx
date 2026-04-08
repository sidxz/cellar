"use client";

import { useEffect, useState } from "react";
import { ClipboardList, Pencil, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/page-header";
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
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Switch } from "@/shared/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { useCustomFields } from "../hooks/use-custom-fields";
import {
  useCreateRegistrationForm,
  useDeleteRegistrationForm,
  useRegistrationForms,
  useUpdateRegistrationForm,
  type FieldOverride,
  type RegistrationForm,
  type CreateRegistrationFormInput,
  type UpdateRegistrationFormInput,
} from "../hooks/use-registration-forms";

// ---------------------------------------------------------------------------
// Field overrides editor sub-component
// ---------------------------------------------------------------------------

interface FieldOverridesEditorProps {
  appliesTo: "molecule" | "batch";
  overrides: FieldOverride[];
  onChange: (overrides: FieldOverride[]) => void;
}

function FieldOverridesEditor({
  appliesTo,
  overrides,
  onChange,
}: FieldOverridesEditorProps) {
  const { data: fields, isLoading } = useCustomFields(appliesTo, true);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (!fields || fields.length === 0) {
    return (
      <p className="py-3 text-sm text-muted-foreground">
        No custom fields defined for {appliesTo}. Add custom fields in the
        Custom Fields admin page.
      </p>
    );
  }

  const getOverride = (fieldId: string): FieldOverride | undefined =>
    overrides.find((o) => o.field_definition_id === fieldId);

  const setOverrideField = <K extends keyof FieldOverride>(
    fieldId: string,
    key: K,
    value: FieldOverride[K]
  ) => {
    const existing = overrides.find((o) => o.field_definition_id === fieldId);
    if (existing) {
      onChange(
        overrides.map((o) =>
          o.field_definition_id === fieldId ? { ...o, [key]: value } : o
        )
      );
    } else {
      onChange([
        ...overrides,
        { field_definition_id: fieldId, [key]: value } as FieldOverride,
      ]);
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
              override?.default_value != null
                ? String(override.default_value)
                : "";

            return (
              <TableRow key={field.id}>
                <TableCell>
                  <div>
                    <span className="font-medium text-sm">{field.label}</span>
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {field.name}
                    </span>
                    {field.is_required && (
                      <Badge
                        variant="secondary"
                        className="ml-2 text-xs"
                      >
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
                      setOverrideField(
                        field.id,
                        "default_value",
                        e.target.value || undefined
                      )
                    }
                    placeholder="Override default..."
                    className="h-7 text-xs"
                  />
                </TableCell>
                <TableCell className="text-center">
                  <Switch
                    checked={isLocked}
                    onCheckedChange={(checked) =>
                      setOverrideField(field.id, "is_locked", checked)
                    }
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

interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: RegistrationForm | null;
}

function FormDialog({ open, onOpenChange, editing }: FormDialogProps) {
  const [name, setName] = useState("");
  const [appliesTo, setAppliesTo] = useState<"molecule" | "batch">("molecule");
  const [isDefault, setIsDefault] = useState(false);
  const [fieldOverrides, setFieldOverrides] = useState<FieldOverride[]>([]);

  const isEdit = editing !== null;
  const create = useCreateRegistrationForm();
  const update = useUpdateRegistrationForm(editing?.id ?? "");

  useEffect(() => {
    if (editing) {
      setName(editing.name);
      setAppliesTo(editing.applies_to);
      setIsDefault(editing.is_default);
      setFieldOverrides(editing.field_overrides ?? []);
    } else {
      setName("");
      setAppliesTo("molecule");
      setIsDefault(false);
      setFieldOverrides([]);
    }
  }, [editing, open]);

  const handleSubmit = async () => {
    if (isEdit) {
      const data: UpdateRegistrationFormInput = {
        name: name.trim(),
        is_default: isDefault,
        field_overrides: fieldOverrides,
      };
      await update.mutateAsync(data);
    } else {
      const data: CreateRegistrationFormInput = {
        name: name.trim(),
        applies_to: appliesTo,
        is_default: isDefault,
        field_overrides: fieldOverrides,
      };
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;
  const canSubmit = name.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit Registration Form" : "New Registration Form"}
          </DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="rf-name">Form Name</Label>
            <Input
              id="rf-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Standard Molecule Registration"
            />
          </div>

          {/* Applies to — only for create */}
          {!isEdit ? (
            <div className="grid gap-2">
              <Label>Applies To</Label>
              <Select
                value={appliesTo}
                onValueChange={(v) =>
                  setAppliesTo(v as "molecule" | "batch")
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="molecule">Molecule</SelectItem>
                  <SelectItem value="batch">Batch</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className="grid gap-2">
              <Label>Applies To</Label>
              <Input
                value={appliesTo === "molecule" ? "Molecule" : "Batch"}
                disabled
              />
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
            <Switch
              id="rf-default"
              checked={isDefault}
              onCheckedChange={setIsDefault}
            />
          </div>

          {/* Field overrides */}
          <div className="grid gap-2">
            <Label>Field Overrides</Label>
            <p className="text-xs text-muted-foreground">
              Override required/default/locked behaviour for individual custom
              fields when this form is selected.
            </p>
            <FieldOverridesEditor
              appliesTo={isEdit ? editing!.applies_to : appliesTo}
              overrides={fieldOverrides}
              onChange={setFieldOverrides}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || isPending}>
            {isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Delete confirmation dialog
// ---------------------------------------------------------------------------

interface DeleteDialogProps {
  form: RegistrationForm | null;
  onClose: () => void;
}

function DeleteDialog({ form, onClose }: DeleteDialogProps) {
  const deleteMutation = useDeleteRegistrationForm();

  const handleConfirm = async () => {
    if (!form) return;
    await deleteMutation.mutateAsync(form.id);
    onClose();
  };

  return (
    <Dialog open={form !== null} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Registration Form?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Permanently delete{" "}
          <span className="font-medium text-foreground">{form?.name}</span>?
          This action cannot be undone.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={deleteMutation.isPending}
          >
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
      <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
        <ClipboardList className="h-10 w-10" />
        <p>No registration forms defined yet.</p>
      </div>
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
                <span className="text-sm tabular-nums">
                  {form.field_overrides?.length ?? 0}
                </span>
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(form)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  {!form.is_default && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDelete(form)}
                    >
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
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <FormsTable
            forms={forms ?? []}
            onEdit={openEdit}
            onDelete={setDeleting}
          />
        )}
      </div>

      <FormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
      />

      <DeleteDialog form={deleting} onClose={() => setDeleting(null)} />
    </>
  );
}
