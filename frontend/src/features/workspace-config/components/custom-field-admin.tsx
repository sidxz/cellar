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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { zodResolver } from "@hookform/resolvers/zod";
import { ListFilter, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import {
  type CreateCustomFieldInput,
  type CustomFieldAppliesTo,
  type CustomFieldDataType,
  type CustomFieldDefinition,
  type UpdateCustomFieldInput,
  useCreateCustomField,
  useCustomFields,
  useDeleteCustomField,
  useUpdateCustomField,
} from "../hooks/use-custom-fields";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DATA_TYPE_LABELS: Record<CustomFieldDataType, string> = {
  text: "Text",
  number: "Number",
  date: "Date",
  picklist: "Picklist",
  file: "File",
  batch_link: "Batch Link",
};

const APPLIES_TO_LABELS: Record<CustomFieldAppliesTo, string> = {
  molecule: "Molecule",
  batch: "Batch",
  sample: "Sample",
};

type TabValue = "all" | "molecule" | "batch" | "sample";

// ---------------------------------------------------------------------------
// Field dialog (create / edit)
// ---------------------------------------------------------------------------

// ── Schema ──────────────────────────────────────────────────────────────────

const formSchema = z.object({
  name: z.string().min(1, "Name is required"),
  label: z.string().min(1, "Label is required"),
  data_type: z.enum(["text", "number", "date", "picklist", "file", "batch_link"]),
  applies_to: z.enum(["molecule", "batch", "sample"]),
  is_required: z.boolean(),
  default_value: z.string().optional(),
  display_order: z.number().int().min(0),
  pick_list_values: z.array(z.string()),
  is_active: z.boolean(),
});

type FormValues = z.infer<typeof formSchema>;

const defaultValues: FormValues = {
  name: "",
  label: "",
  data_type: "text",
  applies_to: "molecule",
  is_required: false,
  default_value: "",
  display_order: 0,
  pick_list_values: [],
  is_active: true,
};

function toFormValues(editing: CustomFieldDefinition): FormValues {
  return {
    name: editing.name,
    label: editing.label,
    // Backend types these as bare `str`; narrow to the form's allowed values.
    data_type: editing.data_type as CustomFieldDataType,
    applies_to: editing.applies_to as CustomFieldAppliesTo,
    is_required: editing.is_required,
    default_value: editing.default_value != null ? String(editing.default_value) : "",
    display_order: editing.display_order,
    pick_list_values: editing.pick_list_values ?? [],
    is_active: editing.is_active,
  };
}

// ── Props ────────────────────────────────────────────────────────────────────

interface FieldDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: CustomFieldDefinition | null;
}

// ── Component ────────────────────────────────────────────────────────────────

function FieldDialog({ open, onOpenChange, editing }: FieldDialogProps) {
  const isEdit = editing !== null;
  const create = useCreateCustomField();
  const update = useUpdateCustomField(editing?.id ?? "");

  // Transient local state — not part of form data
  const [newPickValue, setNewPickValue] = useState("");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  useEffect(() => {
    if (open) {
      form.reset(editing ? toFormValues(editing) : defaultValues);
      setNewPickValue("");
    }
  }, [open, editing, form]);

  const watchedDataType = form.watch("data_type");
  const pickListValues = form.watch("pick_list_values");

  const addPickValue = () => {
    const trimmed = newPickValue.trim();
    if (trimmed && !pickListValues.includes(trimmed)) {
      form.setValue("pick_list_values", [...pickListValues, trimmed]);
      setNewPickValue("");
    }
  };

  const removePickValue = (v: string) => {
    form.setValue(
      "pick_list_values",
      pickListValues.filter((p) => p !== v),
    );
  };

  const onSubmit = async (values: FormValues) => {
    if (isEdit) {
      const data: UpdateCustomFieldInput = {
        label: values.label,
        is_required: values.is_required,
        display_order: values.display_order,
        pick_list_values: values.data_type === "picklist" ? values.pick_list_values : null,
        is_active: values.is_active,
      };
      if (values.default_value?.trim()) data.default_value = values.default_value.trim();
      await update.mutateAsync(data);
    } else {
      const data: CreateCustomFieldInput = {
        name: values.name,
        label: values.label,
        data_type: values.data_type,
        applies_to: values.applies_to,
        is_required: values.is_required,
        display_order: values.display_order,
        pick_list_values: values.data_type === "picklist" ? values.pick_list_values : null,
      };
      if (values.default_value?.trim()) data.default_value = values.default_value.trim();
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Custom Field" : "New Custom Field"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            {/* Name (key) — only for create */}
            {!isEdit && (
              <div className="grid gap-2">
                <Label htmlFor="cf-name">Field Name (key)</Label>
                <Input id="cf-name" {...form.register("name")} placeholder="e.g., ic50_shift" />
                <p className="text-xs text-muted-foreground">
                  Lowercase, no spaces. Used as the storage key.
                </p>
                {form.formState.errors.name && (
                  <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
                )}
              </div>
            )}

            <div className="grid gap-2">
              <Label htmlFor="cf-label">Display Label</Label>
              <Input id="cf-label" {...form.register("label")} placeholder="e.g., IC50 Shift" />
              {form.formState.errors.label && (
                <p className="text-xs text-destructive">{form.formState.errors.label.message}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              {/* Data type — only for create */}
              {!isEdit ? (
                <div className="grid gap-2">
                  <Label>Data Type</Label>
                  <Controller
                    name="data_type"
                    control={form.control}
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(
                            Object.entries(DATA_TYPE_LABELS) as [CustomFieldDataType, string][]
                          ).map(([val, lbl]) => (
                            <SelectItem key={val} value={val}>
                              {lbl}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
              ) : (
                <div className="grid gap-2">
                  <Label>Data Type</Label>
                  <Input
                    value={DATA_TYPE_LABELS[editing!.data_type as CustomFieldDataType]}
                    disabled
                  />
                </div>
              )}

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
                          {(
                            Object.entries(APPLIES_TO_LABELS) as [CustomFieldAppliesTo, string][]
                          ).map(([val, lbl]) => (
                            <SelectItem key={val} value={val}>
                              {lbl}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
              ) : (
                <div className="grid gap-2">
                  <Label>Applies To</Label>
                  <Input
                    value={APPLIES_TO_LABELS[editing!.applies_to as CustomFieldAppliesTo]}
                    disabled
                  />
                </div>
              )}
            </div>

            {/* Picklist values */}
            {watchedDataType === "picklist" && (
              <div className="grid gap-2">
                <Label>Picklist Values</Label>
                <div className="flex gap-2">
                  <Input
                    value={newPickValue}
                    onChange={(e) => setNewPickValue(e.target.value)}
                    placeholder="Add a value..."
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addPickValue();
                      }
                    }}
                  />
                  <Button type="button" variant="outline" onClick={addPickValue}>
                    Add
                  </Button>
                </div>
                {pickListValues.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {pickListValues.map((v) => (
                      <Badge key={v} variant="secondary" className="gap-1">
                        {v}
                        <button
                          type="button"
                          onClick={() => removePickValue(v)}
                          className="ml-1 hover:text-destructive"
                        >
                          ×
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="cf-default">Default Value</Label>
                <Input id="cf-default" {...form.register("default_value")} placeholder="Optional" />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="cf-order">Display Order</Label>
                <Input
                  id="cf-order"
                  type="number"
                  {...form.register("display_order", { valueAsNumber: true })}
                  min={0}
                />
              </div>
            </div>

            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <Label htmlFor="cf-required" className="cursor-pointer">
                Required field
              </Label>
              <Controller
                name="is_required"
                control={form.control}
                render={({ field }) => (
                  <Switch id="cf-required" checked={field.value} onCheckedChange={field.onChange} />
                )}
              />
            </div>

            {isEdit && (
              <div className="flex items-center justify-between rounded-md border px-3 py-2">
                <Label htmlFor="cf-active" className="cursor-pointer">
                  Active
                </Label>
                <Controller
                  name="is_active"
                  control={form.control}
                  render={({ field }) => (
                    <Switch id="cf-active" checked={field.value} onCheckedChange={field.onChange} />
                  )}
                />
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

// ---------------------------------------------------------------------------
// Delete confirmation dialog
// ---------------------------------------------------------------------------

interface DeleteDialogProps {
  field: CustomFieldDefinition | null;
  onOpenChange: (open: boolean) => void;
}

function DeleteDialog({ field, onOpenChange }: DeleteDialogProps) {
  const deleteMutation = useDeleteCustomField();

  const handleConfirm = async () => {
    if (!field) return;
    await deleteMutation.mutateAsync(field.id);
    onOpenChange(false);
  };

  return (
    <Dialog open={field !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Custom Field?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Permanently delete <span className="font-medium text-foreground">{field?.label}</span>?
          Existing data stored under this key will not be removed but will no longer have a
          definition.
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
// Fields table
// ---------------------------------------------------------------------------

interface FieldsTableProps {
  fields: CustomFieldDefinition[];
  onEdit: (field: CustomFieldDefinition) => void;
  onDelete: (field: CustomFieldDefinition) => void;
}

function FieldsTable({ fields, onEdit, onDelete }: FieldsTableProps) {
  if (fields.length === 0) {
    return <EmptyState variant="inline" icon={ListFilter} title="No custom fields defined yet." />;
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Label</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Applies To</TableHead>
            <TableHead>Required</TableHead>
            <TableHead>Active</TableHead>
            <TableHead className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((field) => (
            <TableRow key={field.id}>
              <TableCell className="font-mono text-sm">{field.name}</TableCell>
              <TableCell className="font-medium">{field.label}</TableCell>
              <TableCell>
                <Badge variant="outline">
                  {DATA_TYPE_LABELS[field.data_type as CustomFieldDataType]}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant="secondary">
                  {APPLIES_TO_LABELS[field.applies_to as CustomFieldAppliesTo]}
                </Badge>
              </TableCell>
              <TableCell>
                {field.is_required ? (
                  <Badge variant="destructive" className="text-xs">
                    Required
                  </Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">Optional</span>
                )}
              </TableCell>
              <TableCell>
                <span
                  className={
                    field.is_active
                      ? "text-sm font-medium text-success"
                      : "text-sm text-muted-foreground"
                  }
                >
                  {field.is_active ? "Active" : "Inactive"}
                </span>
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => onEdit(field)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => onDelete(field)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
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
// CustomFieldAdmin — main component
// ---------------------------------------------------------------------------

export function CustomFieldAdmin() {
  const [tab, setTab] = useState<TabValue>("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<CustomFieldDefinition | null>(null);
  const [deleting, setDeleting] = useState<CustomFieldDefinition | null>(null);

  const appliesTo = tab === "all" ? undefined : tab;
  const { data: fields, isLoading } = useCustomFields(appliesTo, undefined);

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (field: CustomFieldDefinition) => {
    setEditing(field);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Custom Fields"
        subtitle="Define additional data fields for molecules, batches, and samples."
      >
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add Custom Field
        </Button>
      </PageHeader>

      <div className="mt-6">
        <Tabs value={tab} onValueChange={(v) => setTab(v as TabValue)}>
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="molecule">Molecule</TabsTrigger>
            <TabsTrigger value="batch">Batch</TabsTrigger>
            <TabsTrigger value="sample">Sample</TabsTrigger>
          </TabsList>

          {isLoading ? (
            <SkeletonList rows={4} className="mt-4 space-y-3" />
          ) : (
            <>
              <TabsContent value="all">
                <FieldsTable fields={fields ?? []} onEdit={openEdit} onDelete={setDeleting} />
              </TabsContent>
              <TabsContent value="molecule">
                <FieldsTable fields={fields ?? []} onEdit={openEdit} onDelete={setDeleting} />
              </TabsContent>
              <TabsContent value="batch">
                <FieldsTable fields={fields ?? []} onEdit={openEdit} onDelete={setDeleting} />
              </TabsContent>
              <TabsContent value="sample">
                <FieldsTable fields={fields ?? []} onEdit={openEdit} onDelete={setDeleting} />
              </TabsContent>
            </>
          )}
        </Tabs>
      </div>

      <FieldDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} />

      <DeleteDialog field={deleting} onOpenChange={(open) => !open && setDeleting(null)} />
    </>
  );
}
