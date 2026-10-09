"use client";

import { useProtocolFacetSlots } from "@/features/screening-assay/hooks/use-protocol-facet-slots";
import {
  PROTOCOL_TYPE_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  READOUT_NORMALIZATION_LABELS,
} from "@/features/screening-assay/types";
import { EmptyState } from "@/shared/components/empty-state";
import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { UnitPicker } from "@/shared/components/unit-picker";
import type {
  ProtocolFormConditionTemplate,
  ProtocolFormReadoutTemplate,
} from "@/shared/lib/api/model";
import { FileText, Pencil, Plus, Trash2 } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { useProtocolCategories } from "../hooks/use-protocol-categories";
import {
  type ProtocolForm,
  useCreateProtocolForm,
  useDeleteProtocolForm,
  useProtocolForms,
  useSeedDefaultProtocolForms,
  useUpdateProtocolForm,
} from "../hooks/use-protocol-forms";
import type { ProtocolCategory } from "../types";

// ---------------------------------------------------------------------------
// Readout / Condition template row types
// ---------------------------------------------------------------------------

interface ReadoutRow {
  /** Stable client-side key so React reconciles rows across add/remove. Not sent to the API. */
  _key: string;
  name: string;
  data_type: string;
  unit: string;
  aggregation: string;
  normalization: string;
  /** The loaded template; spread into the payload so fields this editor does not show survive a save. */
  _source?: ProtocolFormReadoutTemplate;
}

interface ConditionRow {
  /** Stable client-side key so React reconciles rows across add/remove. Not sent to the API. */
  _key: string;
  name: string;
  data_type: string;
  unit: string;
  /** The loaded template; spread into the payload so fields this editor does not show survive a save. */
  _source?: ProtocolFormConditionTemplate;
}

const ANY_CATEGORY = "__any__";
const ANY_CATEGORY_LABEL = "Any category";

function emptyReadoutRow(): ReadoutRow {
  return {
    _key: crypto.randomUUID(),
    name: "",
    data_type: "numeric",
    unit: "",
    aggregation: "none",
    normalization: "none",
  };
}

function emptyConditionRow(): ConditionRow {
  return { _key: crypto.randomUUID(), name: "", data_type: "text", unit: "" };
}

/** A form's facet defaults as the picker's per-slot terms. */
function termsBySlot(form: ProtocolForm | null): Record<string, OntologyTerm[]> {
  const out: Record<string, OntologyTerm[]> = {};
  for (const d of form?.ontology_defaults ?? []) {
    out[d.slot_name] = (d.terms ?? []).map((t) => ({
      term_id: String(t.term_id ?? ""),
      label: String(t.label ?? ""),
      ontology_source: String(t.ontology_source ?? ""),
      uri: (t.uri as string | null) ?? null,
    }));
  }
  return out;
}

// ---------------------------------------------------------------------------
// ProtocolForm dialog (create / edit)
// ---------------------------------------------------------------------------

interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: ProtocolForm | null;
  categories: ProtocolCategory[];
}

function FormDialog({ open, onOpenChange, editing, categories }: FormDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [protocolType, setProtocolType] = useState("");
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [assayFormatFromTarget, setAssayFormatFromTarget] = useState(false);
  const [isDefault, setIsDefault] = useState(false);
  const [ontologyDefaults, setOntologyDefaults] = useState<Record<string, OntologyTerm[]>>({});
  const [readoutRows, setReadoutRows] = useState<ReadoutRow[]>([emptyReadoutRow()]);
  const [conditionRows, setConditionRows] = useState<ConditionRow[]>([]);

  const isEdit = editing !== null;
  const create = useCreateProtocolForm();
  const update = useUpdateProtocolForm(editing?.id ?? "");
  const facetSlots = useProtocolFacetSlots();

  useEffect(() => {
    if (editing) {
      setName(editing.name);
      setDescription(editing.description ?? "");
      setProtocolType(editing.protocol_type ?? "");
      setCategoryId(editing.category_id ?? null);
      setAssayFormatFromTarget(editing.assay_format_from_target ?? false);
      setIsDefault(editing.is_default);
      setOntologyDefaults(termsBySlot(editing));
      setReadoutRows(
        editing.readout_templates.length > 0
          ? editing.readout_templates.map((t) => ({
              _key: crypto.randomUUID(),
              name: t.name,
              data_type: t.data_type,
              unit: t.unit ?? "",
              aggregation: t.aggregation ?? "none",
              normalization: t.normalization ?? "none",
              _source: t,
            }))
          : [emptyReadoutRow()],
      );
      setConditionRows(
        (editing.condition_templates ?? []).map((t) => ({
          _key: crypto.randomUUID(),
          name: t.name,
          data_type: t.data_type,
          unit: t.unit ?? "",
          _source: t,
        })),
      );
    } else {
      setName("");
      setDescription("");
      setProtocolType("");
      setCategoryId(null);
      setAssayFormatFromTarget(false);
      setIsDefault(false);
      setOntologyDefaults({});
      setReadoutRows([emptyReadoutRow()]);
      setConditionRows([]);
    }
  }, [editing, open]);

  const handleSubmit = async () => {
    const validReadouts = readoutRows.filter((r) => r.name.trim());
    if (validReadouts.length === 0) return;

    const readout_templates = validReadouts.map((r) => ({
      ...r._source,
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
            ...c._source,
            name: c.name.trim(),
            data_type: c.data_type,
            unit: c.unit || null,
          }))
        : null;

    const facetDefaults = Object.entries(ontologyDefaults)
      .filter(([, terms]) => terms.length)
      .map(([slot_name, terms]) => ({ slot_name, terms: terms.map((t) => ({ ...t })) }));

    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      protocol_type: protocolType && protocolType !== "__none__" ? protocolType : null,
      category_id: categoryId,
      assay_format_from_target: assayFormatFromTarget,
      is_default: isDefault,
      readout_templates,
      condition_templates,
      ontology_defaults: facetDefaults.length > 0 ? facetDefaults : null,
    };

    if (isEdit) {
      await update.mutateAsync(payload);
    } else {
      await create.mutateAsync(payload);
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
          <DialogTitle>{isEdit ? "Edit Protocol Form" : "New Protocol Form"}</DialogTitle>
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

          <div className="grid gap-2">
            <Label>Category</Label>
            <Select
              value={categoryId ?? ANY_CATEGORY}
              onValueChange={(v) => setCategoryId(v === ANY_CATEGORY ? null : v)}
            >
              <SelectTrigger>
                <SelectValue placeholder={ANY_CATEGORY_LABEL} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY_CATEGORY}>{ANY_CATEGORY_LABEL}</SelectItem>
                {[...categories]
                  .sort((a, b) => a.label.localeCompare(b.label))
                  .map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.label}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="form-default" className="cursor-pointer">
              Default for this category
            </Label>
            <Switch id="form-default" checked={isDefault} onCheckedChange={setIsDefault} />
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="form-assay-format" className="cursor-pointer">
              Assay format follows the target
            </Label>
            <Switch
              id="form-assay-format"
              checked={assayFormatFromTarget}
              onCheckedChange={setAssayFormatFromTarget}
            />
          </div>

          {/* Facet defaults */}
          <div className="grid gap-2">
            <Label className="text-sm font-semibold">
              Facet defaults{" "}
              <span className="text-xs font-normal text-muted-foreground">(optional)</span>
            </Label>
            {facetSlots.map((slot) => (
              <div key={slot.name} className="grid gap-1">
                <Label className="text-[11px]">{slot.label}</Label>
                <OntologySearchInput
                  ontologySources={slot.ontology_sources}
                  rootConceptId={slot.root_concept_id}
                  slot={slot.name}
                  value={ontologyDefaults[slot.name] ?? []}
                  onChange={(terms) =>
                    setOntologyDefaults((prev) => ({ ...prev, [slot.name]: terms }))
                  }
                  allowFreeText={slot.allow_free_text}
                  placeholder={
                    slot.ontology_sources.length
                      ? `Search ${slot.ontology_sources.join(", ")}...`
                      : undefined
                  }
                />
                {slot.name === "assay_format" && assayFormatFromTarget && (
                  <p className="text-xs text-muted-foreground">
                    Not used while the assay format follows the target.
                  </p>
                )}
              </div>
            ))}
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
                <div key={row._key} className="flex items-end gap-2 rounded-md border p-2">
                  <div className="grid gap-1 flex-1">
                    <Label className="text-[11px]">Name</Label>
                    <Input
                      value={row.name}
                      onChange={(e) =>
                        setReadoutRows((prev) =>
                          prev.map((r, i) => (i === idx ? { ...r, name: e.target.value } : r)),
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
                          prev.map((r, i) => (i === idx ? { ...r, data_type: v } : r)),
                        )
                      }
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(READOUT_DATA_TYPE_LABELS).map(([v, l]) => (
                          <SelectItem key={v} value={v}>
                            {l}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-1 w-[110px]">
                    <Label className="text-[11px]">Unit</Label>
                    <UnitPicker
                      value={row.unit}
                      onChange={(v) =>
                        setReadoutRows((prev) =>
                          prev.map((r, i) => (i === idx ? { ...r, unit: v } : r)),
                        )
                      }
                      placeholder="nM"
                    />
                  </div>
                  <div className="grid gap-1 w-[110px]">
                    <Label className="text-[11px]">Aggregation</Label>
                    <Select
                      value={row.aggregation}
                      onValueChange={(v) =>
                        setReadoutRows((prev) =>
                          prev.map((r, i) => (i === idx ? { ...r, aggregation: v } : r)),
                        )
                      }
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(READOUT_AGGREGATION_LABELS).map(([v, l]) => (
                          <SelectItem key={v} value={v}>
                            {l}
                          </SelectItem>
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
                          prev.map((r, i) => (i === idx ? { ...r, normalization: v } : r)),
                        )
                      }
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(READOUT_NORMALIZATION_LABELS).map(([v, l]) => (
                          <SelectItem key={v} value={v}>
                            {l}
                          </SelectItem>
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
                Conditions{" "}
                <span className="text-xs font-normal text-muted-foreground">(optional)</span>
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
                  <div key={row._key} className="flex items-end gap-2">
                    <div className="grid gap-1 flex-1">
                      <Label className="text-[11px]">Name</Label>
                      <Input
                        value={row.name}
                        onChange={(e) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, name: e.target.value } : r)),
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
                            prev.map((r, i) => (i === idx ? { ...r, data_type: v } : r)),
                          )
                        }
                      >
                        <SelectTrigger className="h-8 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="text">Text</SelectItem>
                          <SelectItem value="numeric">Numeric</SelectItem>
                          <SelectItem value="pick_list">Pick List</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid gap-1 w-[110px]">
                      <Label className="text-[11px]">Unit</Label>
                      <UnitPicker
                        value={row.unit}
                        onChange={(v) =>
                          setConditionRows((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, unit: v } : r)),
                          )
                        }
                        placeholder="optional"
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
  onOpenChange: (open: boolean) => void;
}

function DeleteDialog({ form, onOpenChange }: DeleteDialogProps) {
  const deleteMutation = useDeleteProtocolForm();

  const handleConfirm = async () => {
    if (!form) return;
    await deleteMutation.mutateAsync(form.id);
    onOpenChange(false);
  };

  return (
    <Dialog open={form !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Protocol Form?</DialogTitle>
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
// Protocol Form table
// ---------------------------------------------------------------------------

interface FormTableProps {
  entries: ProtocolForm[];
  categories: ProtocolCategory[];
  onEdit: (form: ProtocolForm) => void;
  onDelete: (form: ProtocolForm) => void;
}

/** Forms under their category heading, sorted by category label; generic forms ("Any category") last. */
function groupByCategory(entries: ProtocolForm[], categories: ProtocolCategory[]) {
  const labels = new Map(categories.map((c) => [c.id, c.label]));
  const groups = new Map<string, ProtocolForm[]>();
  for (const entry of entries) {
    const label = (entry.category_id && labels.get(entry.category_id)) || ANY_CATEGORY_LABEL;
    groups.set(label, [...(groups.get(label) ?? []), entry]);
  }
  return [...groups.entries()].sort(([a], [b]) =>
    a === ANY_CATEGORY_LABEL ? 1 : b === ANY_CATEGORY_LABEL ? -1 : a.localeCompare(b),
  );
}

function FormTable({ entries, categories, onEdit, onDelete }: FormTableProps) {
  if (entries.length === 0) {
    return <EmptyState variant="inline" icon={FileText} title="No protocol forms defined yet." />;
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
          {groupByCategory(entries, categories).map(([label, forms]) => (
            <Fragment key={label}>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableCell
                  colSpan={5}
                  className="py-1.5 text-xs font-semibold text-muted-foreground"
                >
                  {label}
                </TableCell>
              </TableRow>
              {forms.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>
                    <div>
                      <span className="font-medium">{entry.name}</span>
                      {entry.description && (
                        <p className="text-xs text-muted-foreground mt-0.5">{entry.description}</p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {entry.protocol_type
                      ? (PROTOCOL_TYPE_LABELS[
                          entry.protocol_type as keyof typeof PROTOCOL_TYPE_LABELS
                        ] ?? entry.protocol_type)
                      : "\u2014"}
                  </TableCell>
                  <TableCell className="tabular-nums">{entry.readout_templates.length}</TableCell>
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
                        aria-label={`Edit ${entry.name}`}
                        onClick={() => onEdit(entry)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Delete ${entry.name}`}
                        onClick={() => onDelete(entry)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </Fragment>
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
  const { data: categories } = useProtocolCategories();
  const seed = useSeedDefaultProtocolForms();

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
        <Button variant="outline" onClick={() => seed.mutate()} disabled={seed.isPending}>
          Add default forms
        </Button>
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add Form
        </Button>
      </PageHeader>

      <div className="mt-6">
        {isLoading ? (
          <SkeletonList />
        ) : (
          <FormTable
            entries={entries ?? []}
            categories={categories ?? []}
            onEdit={openEdit}
            onDelete={setDeleting}
          />
        )}
      </div>

      <FormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        categories={categories ?? []}
      />

      <DeleteDialog form={deleting} onOpenChange={(open) => !open && setDeleting(null)} />
    </>
  );
}
