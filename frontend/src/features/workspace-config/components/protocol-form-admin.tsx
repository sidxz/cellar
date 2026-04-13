"use client";

import { useEffect, useState } from "react";
import { FileText, Pencil, Plus, Trash2 } from "lucide-react";
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
import { Textarea } from "@/shared/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import {
  PROTOCOL_TYPE_LABELS,
  READOUT_DATA_TYPE_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_NORMALIZATION_LABELS,
} from "@/features/screening-assay/types";
import {
  useProtocolForms,
  useCreateProtocolForm,
  useDeleteProtocolForm,
  useUpdateProtocolForm,
  type CreateProtocolFormInput,
  type ProtocolForm,
  type UpdateProtocolFormInput,
} from "../hooks/use-protocol-forms";

// ---------------------------------------------------------------------------
// Readout / Condition template row types
// ---------------------------------------------------------------------------

interface ReadoutRow {
  name: string;
  data_type: string;
  unit: string;
  aggregation: string;
  normalization: string;
}

interface ConditionRow {
  name: string;
  data_type: string;
  unit: string;
}

function emptyReadoutRow(): ReadoutRow {
  return { name: "", data_type: "numeric", unit: "", aggregation: "none", normalization: "none" };
}

function emptyConditionRow(): ConditionRow {
  return { name: "", data_type: "text", unit: "" };
}

// ---------------------------------------------------------------------------
// ProtocolForm dialog (create / edit)
// ---------------------------------------------------------------------------

interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: ProtocolForm | null;
}

function FormDialog({ open, onOpenChange, editing }: FormDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [protocolType, setProtocolType] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [readoutRows, setReadoutRows] = useState<ReadoutRow[]>([emptyReadoutRow()]);
  const [conditionRows, setConditionRows] = useState<ConditionRow[]>([]);

  const isEdit = editing !== null;
  const create = useCreateProtocolForm();
  const update = useUpdateProtocolForm(editing?.id ?? "");

  useEffect(() => {
    if (editing) {
      setName(editing.name);
      setDescription(editing.description ?? "");
      setProtocolType(editing.protocol_type ?? "");
      setIsDefault(editing.is_default);
      setReadoutRows(
        editing.readout_templates.length > 0
          ? editing.readout_templates.map((t) => ({
              name: (t.name as string) ?? "",
              data_type: (t.data_type as string) ?? "numeric",
              unit: (t.unit as string) ?? "",
              aggregation: (t.aggregation as string) ?? "none",
              normalization: (t.normalization as string) ?? "none",
            }))
          : [emptyReadoutRow()],
      );
      setConditionRows(
        editing.condition_templates
          ? editing.condition_templates.map((t) => ({
              name: (t.name as string) ?? "",
              data_type: (t.data_type as string) ?? "text",
              unit: (t.unit as string) ?? "",
            }))
          : [],
      );
    } else {
      setName("");
      setDescription("");
      setProtocolType("");
      setIsDefault(false);
      setReadoutRows([emptyReadoutRow()]);
      setConditionRows([]);
    }
  }, [editing, open]);

  const handleSubmit = async () => {
    const validReadouts = readoutRows.filter((r) => r.name.trim());
    if (validReadouts.length === 0) return;

    const readout_templates = validReadouts.map((r) => ({
      name: r.name.trim(),
      data_type: r.data_type,
      unit: r.unit || null,
      aggregation: r.aggregation,
      normalization: r.normalization,
    }));

    const validConditions = conditionRows.filter((c) => c.name.trim());
    const condition_templates =
      validConditions.length > 0
        ? validConditions.map((c) => ({
            name: c.name.trim(),
            data_type: c.data_type,
            unit: c.unit || null,
          }))
        : null;

    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      protocol_type: protocolType && protocolType !== "__none__" ? protocolType : null,
      is_default: isDefault,
      readout_templates,
      condition_templates,
      ontology_defaults: null,
    };

    if (isEdit) {
      await update.mutateAsync(payload as UpdateProtocolFormInput);
    } else {
      await create.mutateAsync(payload as CreateProtocolFormInput);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;
  const validReadouts = readoutRows.filter((r) => r.name.trim());
  const canSubmit = name.trim() && validReadouts.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit Protocol Form" : "New Protocol Form"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="form-name">Name</Label>
            <Input
              id="form-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Standard IC50 Assay"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="form-description">Description</Label>
            <Textarea
              id="form-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              rows={2}
            />
          </div>

          <div className="grid gap-2">
            <Label>Protocol Type (optional)</Label>
            <Select value={protocolType} onValueChange={setProtocolType}>
              <SelectTrigger>
                <SelectValue placeholder="Any type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Any type</SelectItem>
                {Object.entries(PROTOCOL_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="form-default" className="cursor-pointer">
              Default Form
            </Label>
            <Switch
              id="form-default"
              checked={isDefault}
              onCheckedChange={setIsDefault}
            />
          </div>

          {/* Readout Templates */}
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-semibold">Readout Templates</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setReadoutRows((prev) => [...prev, emptyReadoutRow()])}
              >
                <Plus className="mr-1 h-3 w-3" />
                Add
              </Button>
            </div>
            <div className="space-y-2">
              {readoutRows.map((row, idx) => (
                <div key={idx} className="flex items-end gap-2 rounded-md border p-2">
                  <div className="grid gap-1 flex-1">
                    <Label className="text-[11px]">Name</Label>
                    <Input
                      value={row.name}
                      onChange={(e) =>
                        setReadoutRows((prev) =>
                          prev.map((r, i) => (i === idx ? { ...r, name: e.target.value } : r))
                        )
                      }
                      placeholder="e.g., % Inhibition"
                      className="h-8 text-sm"
                    />
                  </div>
                  <div className="grid gap-1 w-[130px]">
                    <Label className="text-[11px]">Type</Label>
                    <Select
                      value={row.data_type}
                      onValueChange={(v) =>
                        setReadoutRows((prev) =>
                          prev.map((r, i) => (i === idx ? { ...r, data_type: v } : r))
                        )
                      }
                    >
                      <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(READOUT_DATA_TYPE_LABELS).map(([v, l]) => (
                          <SelectItem key={v} value={v}>{l}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-1 w-[80px]">
                    <Label className="text-[11px]">Unit</Label>
                    <Input
                      value={row.unit}
                      onChange={(e) =>
                        setReadoutRows((prev) =>
                          prev.map((r, i) => (i === idx ? { ...r, unit: e.target.value } : r))
                        )
                      }
                      placeholder="nM"
                      className="h-8 text-sm"
                    />
                  </div>
                  <div className="grid gap-1 w-[110px]">
                    <Label className="text-[11px]">Aggregation</Label>
                    <Select
                      value={row.aggregation}
                      onValueChange={(v) =>
                        setReadoutRows((prev) =>
                          prev.map((r, i) => (i === idx ? { ...r, aggregation: v } : r))
                        )
                      }
                    >
                      <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(READOUT_AGGREGATION_LABELS).map(([v, l]) => (
                          <SelectItem key={v} value={v}>{l}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-1 w-[120px]">
                    <Label className="text-[11px]">Normalization</Label>
                    <Select
                      value={row.normalization}
                      onValueChange={(v) =>
                        setReadoutRows((prev) =>
                          prev.map((r, i) => (i === idx ? { ...r, normalization: v } : r))
                        )
                      }
                    >
                      <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(READOUT_NORMALIZATION_LABELS).map(([v, l]) => (
                          <SelectItem key={v} value={v}>{l}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {readoutRows.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0 shrink-0"
                      onClick={() => setReadoutRows((prev) => prev.filter((_, i) => i !== idx))}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Condition Templates */}
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-semibold">
                Conditions <span className="text-xs font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setConditionRows((prev) => [...prev, emptyConditionRow()])}
              >
                <Plus className="mr-1 h-3 w-3" />
                Add
              </Button>
            </div>
            {conditionRows.length > 0 && (
              <div className="space-y-2">
                {conditionRows.map((row, idx) => (
                  <div key={idx} className="flex items-end gap-2">
                    <div className="grid gap-1 flex-1">
                      <Label className="text-[11px]">Name</Label>
                      <Input
                        value={row.name}
                        onChange={(e) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, name: e.target.value } : r))
                          )
                        }
                        placeholder="e.g., Cell Line"
                        className="h-8 text-sm"
                      />
                    </div>
                    <div className="grid gap-1 w-[120px]">
                      <Label className="text-[11px]">Type</Label>
                      <Select
                        value={row.data_type}
                        onValueChange={(v) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, data_type: v } : r))
                          )
                        }
                      >
                        <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="text">Text</SelectItem>
                          <SelectItem value="numeric">Numeric</SelectItem>
                          <SelectItem value="pick_list">Pick List</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid gap-1 w-[80px]">
                      <Label className="text-[11px]">Unit</Label>
                      <Input
                        value={row.unit}
                        onChange={(e) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, unit: e.target.value } : r))
                          )
                        }
                        placeholder="optional"
                        className="h-8 text-sm"
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0 shrink-0"
                      onClick={() => setConditionRows((prev) => prev.filter((_, i) => i !== idx))}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
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
  form: ProtocolForm | null;
  onClose: () => void;
}

function DeleteDialog({ form, onClose }: DeleteDialogProps) {
  const deleteMutation = useDeleteProtocolForm();

  const handleConfirm = async () => {
    if (!form) return;
    await deleteMutation.mutateAsync(form.id);
    onClose();
  };

  return (
    <Dialog open={form !== null} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Protocol Form?</DialogTitle>
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
// Protocol Form table
// ---------------------------------------------------------------------------

interface FormTableProps {
  entries: ProtocolForm[];
  onEdit: (form: ProtocolForm) => void;
  onDelete: (form: ProtocolForm) => void;
}

function FormTable({ entries, onEdit, onDelete }: FormTableProps) {
  if (entries.length === 0) {
    return (
      <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
        <FileText className="h-10 w-10" />
        <p>No protocol forms defined yet.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Protocol Type</TableHead>
            <TableHead>Readouts</TableHead>
            <TableHead>Default</TableHead>
            <TableHead className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell>
                <div>
                  <span className="font-medium">{entry.name}</span>
                  {entry.description && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {entry.description}
                    </p>
                  )}
                </div>
              </TableCell>
              <TableCell>
                {entry.protocol_type
                  ? PROTOCOL_TYPE_LABELS[
                      entry.protocol_type as keyof typeof PROTOCOL_TYPE_LABELS
                    ] ?? entry.protocol_type
                  : "\u2014"}
              </TableCell>
              <TableCell className="tabular-nums">
                {entry.readout_templates.length}
              </TableCell>
              <TableCell>
                {entry.is_default ? (
                  <Badge variant="secondary" className="text-xs">
                    Default
                  </Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">{"\u2014"}</span>
                )}
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(entry)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(entry)}
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
// ProtocolFormAdmin — main component
// ---------------------------------------------------------------------------

export function ProtocolFormAdmin() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ProtocolForm | null>(null);
  const [deleting, setDeleting] = useState<ProtocolForm | null>(null);

  const { data: entries, isLoading } = useProtocolForms();

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (form: ProtocolForm) => {
    setEditing(form);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Protocol Forms"
        subtitle="Pre-configured protocol templates with readout definitions, conditions, and ontology defaults."
      >
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add Form
        </Button>
      </PageHeader>

      <div className="mt-6">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <FormTable
            entries={entries ?? []}
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
