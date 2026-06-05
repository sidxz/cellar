"use client";

import { PageHeader } from "@/shared/components/page-header";
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
import { zodResolver } from "@hookform/resolvers/zod";
import { BookOpen, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import {
  type CreateOntologySlotInput,
  type OntologySlotDefinition,
  type UpdateOntologySlotInput,
  useCreateOntologySlot,
  useDeleteOntologySlot,
  useOntologySlots,
  useUpdateOntologySlot,
} from "../hooks/use-ontology-slots";

// ---------------------------------------------------------------------------
// OntologySlot dialog (create / edit)
// ---------------------------------------------------------------------------

// ── Schema ──────────────────────────────────────────────────────────────────

const ONTOLOGY_OPTIONS = [
  { value: "BAO", label: "BAO — BioAssay Ontology" },
  { value: "GO", label: "GO — Gene Ontology" },
  { value: "CLO", label: "CLO — Cell Line Ontology" },
  { value: "DOID", label: "DOID — Disease Ontology" },
  { value: "CHEBI", label: "CHEBI — Chemical Entities" },
  { value: "OBI", label: "OBI — Biomedical Investigation" },
  { value: "NCBITAXON", label: "NCBI Taxonomy" },
  { value: "PATO", label: "PATO — Phenotype & Trait" },
] as const;

const formSchema = z.object({
  name: z.string().min(1, "Name is required"),
  label: z.string().min(1, "Label is required"),
  ontology_sources: z.array(z.string()).min(1, "Select at least one ontology"),
  root_concept_id: z.string().optional(),
  is_required: z.boolean(),
  allow_free_text: z.boolean(),
  display_order: z.number().int().min(0),
});

type FormValues = z.infer<typeof formSchema>;

const defaultValues: FormValues = {
  name: "",
  label: "",
  ontology_sources: [],
  root_concept_id: "",
  is_required: false,
  allow_free_text: false,
  display_order: 0,
};

function toFormValues(editing: OntologySlotDefinition): FormValues {
  return {
    name: editing.name,
    label: editing.label,
    ontology_sources: editing.ontology_sources,
    root_concept_id: editing.root_concept_id ?? "",
    is_required: editing.is_required,
    allow_free_text: editing.allow_free_text,
    display_order: editing.display_order,
  };
}

// ── Props ────────────────────────────────────────────────────────────────────

interface SlotDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: OntologySlotDefinition | null;
}

// ── Component ────────────────────────────────────────────────────────────────

function SlotDialog({ open, onOpenChange, editing }: SlotDialogProps) {
  const isEdit = editing !== null;
  const create = useCreateOntologySlot();
  const update = useUpdateOntologySlot(editing?.id ?? "");

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
    if (isEdit) {
      const data: UpdateOntologySlotInput = {
        label: values.label.trim(),
        ontology_sources: values.ontology_sources,
        root_concept_id: values.root_concept_id?.trim() || null,
        is_required: values.is_required,
        allow_free_text: values.allow_free_text,
        display_order: values.display_order,
      };
      await update.mutateAsync(data);
    } else {
      const data: CreateOntologySlotInput = {
        name: values.name.trim(),
        label: values.label.trim(),
        ontology_sources: values.ontology_sources,
        root_concept_id: values.root_concept_id?.trim() || null,
        is_required: values.is_required,
        allow_free_text: values.allow_free_text,
        display_order: values.display_order,
      };
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Ontology Slot" : "New Ontology Slot"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            {!isEdit ? (
              <div className="grid gap-2">
                <Label htmlFor="slot-name">Name</Label>
                <Input
                  id="slot-name"
                  {...form.register("name")}
                  placeholder="e.g., assay_type"
                  className="font-mono"
                />
                <p className="text-xs text-muted-foreground">
                  Machine identifier. Cannot be changed after creation.
                </p>
                {form.formState.errors.name && (
                  <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
                )}
              </div>
            ) : (
              <div className="grid gap-2">
                <Label>Name</Label>
                <Input value={editing?.name ?? ""} disabled className="font-mono" />
              </div>
            )}

            <div className="grid gap-2">
              <Label htmlFor="slot-label">Label</Label>
              <Input id="slot-label" {...form.register("label")} placeholder="e.g., Assay Type" />
              {form.formState.errors.label && (
                <p className="text-xs text-destructive">{form.formState.errors.label.message}</p>
              )}
            </div>

            <div className="grid gap-2">
              <Label>Ontology Sources</Label>
              <Controller
                name="ontology_sources"
                control={form.control}
                render={({ field }) => (
                  <div className="grid grid-cols-2 gap-2 rounded-md border p-3">
                    {ONTOLOGY_OPTIONS.map((ont) => {
                      const isChecked = field.value.includes(ont.value);
                      return (
                        <label
                          key={ont.value}
                          className="flex items-center gap-2 text-sm cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              const updated = e.target.checked
                                ? [...field.value, ont.value]
                                : field.value.filter((s) => s !== ont.value);
                              field.onChange(updated);
                            }}
                            className="rounded border-input"
                          />
                          <span>{ont.label}</span>
                        </label>
                      );
                    })}
                  </div>
                )}
              />
              <p className="text-xs text-muted-foreground">
                Select which ontologies to search for this slot.
              </p>
              {form.formState.errors.ontology_sources && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.ontology_sources.message}
                </p>
              )}
            </div>

            <div className="grid gap-2">
              <Label htmlFor="slot-root-concept">Root Concept ID (optional)</Label>
              <Input
                id="slot-root-concept"
                {...form.register("root_concept_id")}
                placeholder="e.g., http://www.bioassayontology.org/bao#BAO_0000008"
              />
              <p className="text-xs text-muted-foreground">
                Constrain search to a subtree. Use the full URI from BioPortal.
              </p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="slot-order">Display Order</Label>
              <Input
                id="slot-order"
                type="number"
                {...form.register("display_order", { valueAsNumber: true })}
                min={0}
              />
            </div>

            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <Label htmlFor="slot-required" className="cursor-pointer">
                Required
              </Label>
              <Controller
                name="is_required"
                control={form.control}
                render={({ field }) => (
                  <Switch
                    id="slot-required"
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                )}
              />
            </div>

            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <Label htmlFor="slot-freetext" className="cursor-pointer">
                Allow Free Text
              </Label>
              <Controller
                name="allow_free_text"
                control={form.control}
                render={({ field }) => (
                  <Switch
                    id="slot-freetext"
                    checked={field.value}
                    onCheckedChange={field.onChange}
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
  slot: OntologySlotDefinition | null;
  onClose: () => void;
}

function DeleteDialog({ slot, onClose }: DeleteDialogProps) {
  const deleteMutation = useDeleteOntologySlot();

  const handleConfirm = async () => {
    if (!slot) return;
    await deleteMutation.mutateAsync(slot.id);
    onClose();
  };

  return (
    <Dialog open={slot !== null} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Ontology Slot?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Permanently delete{" "}
          <span className="font-medium text-foreground">
            {slot?.label} ({slot?.name})
          </span>
          ? This action cannot be undone.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
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
// Ontology Slot table
// ---------------------------------------------------------------------------

interface SlotTableProps {
  entries: OntologySlotDefinition[];
  onEdit: (slot: OntologySlotDefinition) => void;
  onDelete: (slot: OntologySlotDefinition) => void;
}

function SlotTable({ entries, onEdit, onDelete }: SlotTableProps) {
  if (entries.length === 0) {
    return (
      <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
        <BookOpen className="h-10 w-10" />
        <p>No ontology slots defined yet.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Label</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Ontology Sources</TableHead>
            <TableHead>Required</TableHead>
            <TableHead>Free Text</TableHead>
            <TableHead>Order</TableHead>
            <TableHead className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell className="font-medium">{entry.label}</TableCell>
              <TableCell className="font-mono text-sm text-muted-foreground">
                {entry.name}
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {entry.ontology_sources.map((src) => (
                    <Badge key={src} variant="secondary" className="text-xs">
                      {src}
                    </Badge>
                  ))}
                </div>
              </TableCell>
              <TableCell>
                {entry.is_required ? (
                  <Badge variant="default" className="text-xs">
                    Required
                  </Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">{"—"}</span>
                )}
              </TableCell>
              <TableCell>
                {entry.allow_free_text ? (
                  <Badge variant="outline" className="text-xs">
                    Yes
                  </Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">{"—"}</span>
                )}
              </TableCell>
              <TableCell className="tabular-nums">{entry.display_order}</TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => onEdit(entry)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => onDelete(entry)}>
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
// OntologySlotAdmin — main component
// ---------------------------------------------------------------------------

export function OntologySlotAdmin() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<OntologySlotDefinition | null>(null);
  const [deleting, setDeleting] = useState<OntologySlotDefinition | null>(null);

  const { data: entries, isLoading } = useOntologySlots();

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (slot: OntologySlotDefinition) => {
    setEditing(slot);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Ontology Slots"
        subtitle="Define the annotation slots available for protocols (e.g., Assay Type, Cell Line Ontology)."
      >
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add Slot
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
          <SlotTable entries={entries ?? []} onEdit={openEdit} onDelete={setDeleting} />
        )}
      </div>

      <SlotDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} />

      <DeleteDialog slot={deleting} onClose={() => setDeleting(null)} />
    </>
  );
}
