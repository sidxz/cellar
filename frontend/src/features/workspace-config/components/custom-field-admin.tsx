"use client";

import { useEffect, useState } from "react";
import { ListFilter, Plus, Trash2, Pencil } from "lucide-react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import {
  useCreateCustomField,
  useCustomFields,
  useDeleteCustomField,
  useUpdateCustomField,
  type CreateCustomFieldInput,
  type CustomFieldDefinition,
  type UpdateCustomFieldInput,
} from "../hooks/use-custom-fields";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DATA_TYPE_LABELS: Record<CustomFieldDefinition["data_type"], string> = {
  text: "Text",
  number: "Number",
  date: "Date",
  picklist: "Picklist",
  file: "File",
  batch_link: "Batch Link",
};

const APPLIES_TO_LABELS: Record<CustomFieldDefinition["applies_to"], string> = {
  molecule: "Molecule",
  batch: "Batch",
  sample: "Sample",
};

type TabValue = "all" | "molecule" | "batch" | "sample";

// ---------------------------------------------------------------------------
// Field dialog (create / edit)
// ---------------------------------------------------------------------------

interface FieldDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: CustomFieldDefinition | null;
}

function FieldDialog({ open, onOpenChange, editing }: FieldDialogProps) {
  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [dataType, setDataType] = useState<CustomFieldDefinition["data_type"]>("text");
  const [appliesTo, setAppliesTo] = useState<CustomFieldDefinition["applies_to"]>("molecule");
  const [isRequired, setIsRequired] = useState(false);
  const [defaultValue, setDefaultValue] = useState("");
  const [displayOrder, setDisplayOrder] = useState(0);
  const [pickListValues, setPickListValues] = useState<string[]>([]);
  const [newPickValue, setNewPickValue] = useState("");
  const [isActive, setIsActive] = useState(true);

  const isEdit = editing !== null;
  const create = useCreateCustomField();
  const update = useUpdateCustomField(editing?.id ?? "");

  useEffect(() => {
    if (editing) {
      setName(editing.name);
      setLabel(editing.label);
      setDataType(editing.data_type);
      setAppliesTo(editing.applies_to);
      setIsRequired(editing.is_required);
      setDefaultValue(editing.default_value != null ? String(editing.default_value) : "");
      setDisplayOrder(editing.display_order);
      setPickListValues(editing.pick_list_values ?? []);
      setIsActive(editing.is_active);
    } else {
      setName("");
      setLabel("");
      setDataType("text");
      setAppliesTo("molecule");
      setIsRequired(false);
      setDefaultValue("");
      setDisplayOrder(0);
      setPickListValues([]);
      setIsActive(true);
    }
    setNewPickValue("");
  }, [editing, open]);

  const addPickValue = () => {
    const trimmed = newPickValue.trim();
    if (trimmed && !pickListValues.includes(trimmed)) {
      setPickListValues([...pickListValues, trimmed]);
      setNewPickValue("");
    }
  };

  const removePickValue = (v: string) => {
    setPickListValues(pickListValues.filter((p) => p !== v));
  };

  const handleSubmit = async () => {
    if (isEdit) {
      const data: UpdateCustomFieldInput = {
        label,
        is_required: isRequired,
        display_order: displayOrder,
        pick_list_values: dataType === "picklist" ? pickListValues : null,
        is_active: isActive,
      };
      if (defaultValue.trim()) data.default_value = defaultValue.trim();
      await update.mutateAsync(data);
    } else {
      const data: CreateCustomFieldInput = {
        name,
        label,
        data_type: dataType,
        applies_to: appliesTo,
        is_required: isRequired,
        display_order: displayOrder,
        pick_list_values: dataType === "picklist" ? pickListValues : null,
      };
      if (defaultValue.trim()) data.default_value = defaultValue.trim();
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;
  const canSubmit = name.trim() && label.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Custom Field" : "New Custom Field"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {/* Name (key) — only for create */}
          {!isEdit && (
            <div className="grid gap-2">
              <Label htmlFor="cf-name">Field Name (key)</Label>
              <Input
                id="cf-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., ic50_shift"
              />
              <p className="text-xs text-muted-foreground">
                Lowercase, no spaces. Used as the storage key.
              </p>
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="cf-label">Display Label</Label>
            <Input
              id="cf-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g., IC50 Shift"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Data type — only for create */}
            {!isEdit ? (
              <div className="grid gap-2">
                <Label>Data Type</Label>
                <Select
                  value={dataType}
                  onValueChange={(v) => setDataType(v as CustomFieldDefinition["data_type"])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.entries(DATA_TYPE_LABELS) as [CustomFieldDefinition["data_type"], string][]).map(
                      ([val, lbl]) => (
                        <SelectItem key={val} value={val}>
                          {lbl}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div className="grid gap-2">
                <Label>Data Type</Label>
                <Input value={DATA_TYPE_LABELS[dataType]} disabled />
              </div>
            )}

            {/* Applies to — only for create */}
            {!isEdit ? (
              <div className="grid gap-2">
                <Label>Applies To</Label>
                <Select
                  value={appliesTo}
                  onValueChange={(v) => setAppliesTo(v as CustomFieldDefinition["applies_to"])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.entries(APPLIES_TO_LABELS) as [CustomFieldDefinition["applies_to"], string][]).map(
                      ([val, lbl]) => (
                        <SelectItem key={val} value={val}>
                          {lbl}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div className="grid gap-2">
                <Label>Applies To</Label>
                <Input value={APPLIES_TO_LABELS[appliesTo]} disabled />
              </div>
            )}
          </div>

          {/* Picklist values */}
          {dataType === "picklist" && (
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
              <Input
                id="cf-default"
                value={defaultValue}
                onChange={(e) => setDefaultValue(e.target.value)}
                placeholder="Optional"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cf-order">Display Order</Label>
              <Input
                id="cf-order"
                type="number"
                value={displayOrder}
                onChange={(e) => setDisplayOrder(Number(e.target.value))}
                min={0}
              />
            </div>
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="cf-required" className="cursor-pointer">
              Required field
            </Label>
            <Switch
              id="cf-required"
              checked={isRequired}
              onCheckedChange={setIsRequired}
            />
          </div>

          {isEdit && (
            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <Label htmlFor="cf-active" className="cursor-pointer">
                Active
              </Label>
              <Switch
                id="cf-active"
                checked={isActive}
                onCheckedChange={setIsActive}
              />
            </div>
          )}
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
  field: CustomFieldDefinition | null;
  onClose: () => void;
}

function DeleteDialog({ field, onClose }: DeleteDialogProps) {
  const deleteMutation = useDeleteCustomField();

  const handleConfirm = async () => {
    if (!field) return;
    await deleteMutation.mutateAsync(field.id);
    onClose();
  };

  return (
    <Dialog open={field !== null} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Custom Field?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Permanently delete{" "}
          <span className="font-medium text-foreground">{field?.label}</span>?
          Existing data stored under this key will not be removed but will no
          longer have a definition.
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
// Fields table
// ---------------------------------------------------------------------------

interface FieldsTableProps {
  fields: CustomFieldDefinition[];
  onEdit: (field: CustomFieldDefinition) => void;
  onDelete: (field: CustomFieldDefinition) => void;
}

function FieldsTable({ fields, onEdit, onDelete }: FieldsTableProps) {
  if (fields.length === 0) {
    return (
      <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
        <ListFilter className="h-10 w-10" />
        <p>No custom fields defined yet.</p>
      </div>
    );
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
                <Badge variant="outline">{DATA_TYPE_LABELS[field.data_type]}</Badge>
              </TableCell>
              <TableCell>
                <Badge variant="secondary">{APPLIES_TO_LABELS[field.applies_to]}</Badge>
              </TableCell>
              <TableCell>
                {field.is_required ? (
                  <Badge variant="destructive" className="text-xs">Required</Badge>
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
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(field)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(field)}
                  >
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
            <div className="mt-4 space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <>
              <TabsContent value="all">
                <FieldsTable
                  fields={fields ?? []}
                  onEdit={openEdit}
                  onDelete={setDeleting}
                />
              </TabsContent>
              <TabsContent value="molecule">
                <FieldsTable
                  fields={fields ?? []}
                  onEdit={openEdit}
                  onDelete={setDeleting}
                />
              </TabsContent>
              <TabsContent value="batch">
                <FieldsTable
                  fields={fields ?? []}
                  onEdit={openEdit}
                  onDelete={setDeleting}
                />
              </TabsContent>
              <TabsContent value="sample">
                <FieldsTable
                  fields={fields ?? []}
                  onEdit={openEdit}
                  onDelete={setDeleting}
                />
              </TabsContent>
            </>
          )}
        </Tabs>
      </div>

      <FieldDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
      />

      <DeleteDialog
        field={deleting}
        onClose={() => setDeleting(null)}
      />
    </>
  );
}
