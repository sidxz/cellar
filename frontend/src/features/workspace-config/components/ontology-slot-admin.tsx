"use client";

import { useEffect, useState } from "react";
import { BookOpen, Pencil, Plus, Trash2 } from "lucide-react";
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
import {
  useOntologySlots,
  useCreateOntologySlot,
  useDeleteOntologySlot,
  useUpdateOntologySlot,
  type CreateOntologySlotInput,
  type OntologySlotDefinition,
  type UpdateOntologySlotInput,
} from "../hooks/use-ontology-slots";

// ---------------------------------------------------------------------------
// OntologySlot dialog (create / edit)
// ---------------------------------------------------------------------------

interface SlotDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: OntologySlotDefinition | null;
}

function SlotDialog({ open, onOpenChange, editing }: SlotDialogProps) {
  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [ontologySources, setOntologySources] = useState("");
  const [rootConceptId, setRootConceptId] = useState("");
  const [isRequired, setIsRequired] = useState(false);
  const [allowFreeText, setAllowFreeText] = useState(false);
  const [displayOrder, setDisplayOrder] = useState("0");

  const isEdit = editing !== null;
  const create = useCreateOntologySlot();
  const update = useUpdateOntologySlot(editing?.id ?? "");

  useEffect(() => {
    if (editing) {
      setName(editing.name);
      setLabel(editing.label);
      setOntologySources(editing.ontology_sources.join(", "));
      setRootConceptId(editing.root_concept_id ?? "");
      setIsRequired(editing.is_required);
      setAllowFreeText(editing.allow_free_text);
      setDisplayOrder(String(editing.display_order));
    } else {
      setName("");
      setLabel("");
      setOntologySources("");
      setRootConceptId("");
      setIsRequired(false);
      setAllowFreeText(false);
      setDisplayOrder("0");
    }
  }, [editing, open]);

  const handleSubmit = async () => {
    const sources = ontologySources
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const order = parseInt(displayOrder, 10);

    if (isEdit) {
      const data: UpdateOntologySlotInput = {
        label: label.trim(),
        ontology_sources: sources,
        root_concept_id: rootConceptId.trim() || null,
        is_required: isRequired,
        allow_free_text: allowFreeText,
        display_order: isNaN(order) ? 0 : order,
      };
      await update.mutateAsync(data);
    } else {
      const data: CreateOntologySlotInput = {
        name: name.trim(),
        label: label.trim(),
        ontology_sources: sources,
        root_concept_id: rootConceptId.trim() || null,
        is_required: isRequired,
        allow_free_text: allowFreeText,
        display_order: isNaN(order) ? 0 : order,
      };
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;
  const canSubmit = label.trim() && ontologySources.trim() && (isEdit || name.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit Ontology Slot" : "New Ontology Slot"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {!isEdit ? (
            <div className="grid gap-2">
              <Label htmlFor="slot-name">Name</Label>
              <Input
                id="slot-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., assay_type"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Machine identifier. Cannot be changed after creation.
              </p>
            </div>
          ) : (
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                value={editing?.name ?? ""}
                disabled
                className="font-mono"
              />
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="slot-label">Label</Label>
            <Input
              id="slot-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g., Assay Type"
            />
          </div>

          <div className="grid gap-2">
            <Label>Ontology Sources</Label>
            <div className="grid grid-cols-2 gap-2 rounded-md border p-3">
              {[
                { value: "BAO", label: "BAO — BioAssay Ontology" },
                { value: "GO", label: "GO — Gene Ontology" },
                { value: "CLO", label: "CLO — Cell Line Ontology" },
                { value: "DOID", label: "DOID — Disease Ontology" },
                { value: "CHEBI", label: "CHEBI — Chemical Entities" },
                { value: "OBI", label: "OBI — Biomedical Investigation" },
                { value: "NCBITAXON", label: "NCBI Taxonomy" },
                { value: "PATO", label: "PATO — Phenotype & Trait" },
              ].map((ont) => {
                const selected = ontologySources
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean);
                const isChecked = selected.includes(ont.value);
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
                          ? [...selected, ont.value]
                          : selected.filter((s) => s !== ont.value);
                        setOntologySources(updated.join(", "));
                      }}
                      className="rounded border-input"
                    />
                    <span>{ont.label}</span>
                  </label>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              Select which ontologies to search for this slot.
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="slot-root-concept">Root Concept ID (optional)</Label>
            <Input
              id="slot-root-concept"
              value={rootConceptId}
              onChange={(e) => setRootConceptId(e.target.value)}
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
              value={displayOrder}
              onChange={(e) => setDisplayOrder(e.target.value)}
              min={0}
            />
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="slot-required" className="cursor-pointer">
              Required
            </Label>
            <Switch
              id="slot-required"
              checked={isRequired}
              onCheckedChange={setIsRequired}
            />
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="slot-freetext" className="cursor-pointer">
              Allow Free Text
            </Label>
            <Switch
              id="slot-freetext"
              checked={allowFreeText}
              onCheckedChange={setAllowFreeText}
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
                  <Badge variant="default" className="text-xs">Required</Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">{"\u2014"}</span>
                )}
              </TableCell>
              <TableCell>
                {entry.allow_free_text ? (
                  <Badge variant="outline" className="text-xs">Yes</Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">{"\u2014"}</span>
                )}
              </TableCell>
              <TableCell className="tabular-nums">{entry.display_order}</TableCell>
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
          <SlotTable
            entries={entries ?? []}
            onEdit={openEdit}
            onDelete={setDeleting}
          />
        )}
      </div>

      <SlotDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
      />

      <DeleteDialog slot={deleting} onClose={() => setDeleting(null)} />
    </>
  );
}
