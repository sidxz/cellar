"use client";

import { useState } from "react";
import { Plus, Trash2, Search, Pencil, Group } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { StructureRenderer, StructureEditorDialog } from "@/shared/components/chemistry";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useProtocols, useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import { useCollections } from "../hooks/use-collections";
import { useProjects } from "../hooks/use-projects";
import { Badge } from "@/shared/components/ui/badge";
import type {
  SearchCriterion,
  SearchQuery,
  TextCriterion,
  PropertyCriterion,
  StructureCriterion,
  ActivityCriterion,
  CollectionCriterion,
  KeywordListCriterion,
  RunDateCriterion,
  BatchCriterion,
  ProjectCriterion,
  SelectivityCriterion,
  GroupCriterion,
  CustomFieldCriterion,
  CustomFieldMode,
  TextOperator,
  PropertyOperator,
  StructureSearchType,
  RefType,
  BatchFieldType,
} from "../types";

// ─── Field / operator options ───────────────────────────────────────────────

const TEXT_FIELDS = [
  { value: "name", label: "Name" },
  { value: "registration_number", label: "Registration Number" },
  { value: "molecular_formula", label: "Molecular Formula" },
  { value: "inchi_key", label: "InChI Key" },
] as const;

const TEXT_OPERATORS: { value: TextOperator; label: string }[] = [
  { value: "contains", label: "Contains" },
  { value: "equals", label: "Equals" },
  { value: "starts_with", label: "Starts With" },
];

const PROPERTY_FIELDS = [
  { value: "molecular_weight", label: "Molecular Weight" },
  { value: "logp", label: "LogP" },
  { value: "tpsa", label: "TPSA" },
  { value: "hbd", label: "HBD" },
  { value: "hba", label: "HBA" },
  { value: "rotatable_bonds", label: "Rotatable Bonds" },
  { value: "heavy_atom_count", label: "Heavy Atom Count" },
  { value: "aromatic_rings", label: "Aromatic Rings" },
  { value: "ring_count", label: "Ring Count" },
  { value: "ro5_violations", label: "Ro5 Violations" },
] as const;

const PROPERTY_OPERATORS: { value: PropertyOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
  { value: "between", label: "Between" },
];

const STRUCTURE_TYPES: { value: StructureSearchType; label: string }[] = [
  { value: "substructure", label: "Substructure (SMARTS)" },
  { value: "similarity", label: "Similarity (SMILES)" },
  { value: "exact", label: "Exact (InChIKey)" },
];

// ─── Default criterion factories ────────────────────────────────────────────

function defaultTextCriterion(): TextCriterion {
  return { type: "text", field: "name", operator: "contains", value: "" };
}

function defaultPropertyCriterion(): PropertyCriterion {
  return { type: "property", field: "molecular_weight", operator: "gte", value: undefined, min: undefined, max: undefined };
}

function defaultStructureCriterion(): StructureCriterion {
  return { type: "structure", search_type: "substructure", smarts: "", smiles: undefined, threshold: 0.7, inchi_key: undefined };
}

function defaultActivityCriterion(): ActivityCriterion {
  return { type: "activity", protocol_id: "", operator: "lt" as PropertyOperator, value: 0 };
}

function defaultCollectionCriterion(): CollectionCriterion {
  return { type: "collection", collection_id: "" };
}

function defaultKeywordListCriterion(): KeywordListCriterion {
  return { type: "keyword_list", values: [], ref_type: "registration_number" as RefType };
}

function defaultRunDateCriterion(): RunDateCriterion {
  return { type: "run_date" };
}

function defaultBatchCriterion(): BatchCriterion {
  return { type: "batch", field_type: "text", field: "batch_number", operator: "contains", value: "" };
}

function defaultProjectCriterion(): ProjectCriterion {
  return { type: "project", project_ids: [] };
}

function defaultGroupCriterion(): GroupCriterion {
  return { type: "group", logic: "or", criteria: [] };
}

function defaultCustomFieldCriterion(): CustomFieldCriterion {
  return { type: "custom_field", field: "", mode: "text", operator: "contains", value: "" };
}

function defaultSelectivityCriterion(): SelectivityCriterion {
  return {
    type: "selectivity",
    target_protocol_id: "",
    target_curve_type: "ic50",
    counter_protocol_id: "",
    counter_curve_type: "ic50",
    ratio_operator: "gte",
    ratio_value: 100,
  };
}

const BATCH_TEXT_FIELDS = [
  { value: "batch_number", label: "Batch Number" },
  { value: "source", label: "Source" },
  { value: "salt_name", label: "Salt Form" },
  { value: "vendor_catalog_number", label: "Vendor Catalog #" },
  { value: "notebook_reference", label: "Notebook Reference" },
] as const;

const BATCH_NUMERIC_FIELDS = [
  { value: "purity", label: "Purity (%)" },
  { value: "amount_value", label: "Amount" },
] as const;

const BATCH_FIELD_TYPE_OPTIONS: { value: BatchFieldType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "numeric", label: "Numeric" },
  { value: "date", label: "Synthesis Date" },
];

const CURVE_TYPE_OPTIONS = [
  { value: "ic50", label: "IC50" },
  { value: "ec50", label: "EC50" },
  { value: "ki", label: "Ki" },
  { value: "kd", label: "Kd" },
] as const;

const REF_TYPE_OPTIONS: { value: RefType; label: string }[] = [
  { value: "registration_number", label: "Registration Number" },
  { value: "name", label: "Name" },
  { value: "external_id", label: "External ID" },
  { value: "smiles", label: "SMILES" },
  { value: "inchi_key", label: "InChI Key" },
];

// ─── Criterion row components ───────────────────────────────────────────────

function TextCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: TextCriterion;
  onChange: (c: TextCriterion) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-end gap-2">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Field</Label>
        <Select
          value={criterion.field}
          onValueChange={(v) => onChange({ ...criterion, field: v })}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TEXT_FIELDS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="w-32">
        <Label className="text-xs text-muted-foreground">Operator</Label>
        <Select
          value={criterion.operator}
          onValueChange={(v) => onChange({ ...criterion, operator: v as TextOperator })}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TEXT_OPERATORS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex-1">
        <Label className="text-xs text-muted-foreground">Value</Label>
        <Input
          className="h-9"
          placeholder="Search text..."
          value={criterion.value}
          onChange={(e) => onChange({ ...criterion, value: e.target.value })}
        />
      </div>
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

function PropertyCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: PropertyCriterion;
  onChange: (c: PropertyCriterion) => void;
  onRemove: () => void;
}) {
  const isBetween = criterion.operator === "between";

  return (
    <div className="flex items-end gap-2">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Property</Label>
        <Select
          value={criterion.field}
          onValueChange={(v) => onChange({ ...criterion, field: v })}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROPERTY_FIELDS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="w-28">
        <Label className="text-xs text-muted-foreground">Operator</Label>
        <Select
          value={criterion.operator}
          onValueChange={(v) =>
            onChange({
              ...criterion,
              operator: v as PropertyOperator,
              // Reset value fields when switching to/from between
              ...(v === "between"
                ? { value: undefined, min: criterion.min, max: criterion.max }
                : { min: undefined, max: undefined, value: criterion.value }),
            })
          }
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROPERTY_OPERATORS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {isBetween ? (
        <>
          <div className="w-24">
            <Label className="text-xs text-muted-foreground">Min</Label>
            <Input
              className="h-9"
              type="number"
              placeholder="Min"
              value={criterion.min ?? ""}
              onChange={(e) =>
                onChange({ ...criterion, min: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </div>
          <div className="w-24">
            <Label className="text-xs text-muted-foreground">Max</Label>
            <Input
              className="h-9"
              type="number"
              placeholder="Max"
              value={criterion.max ?? ""}
              onChange={(e) =>
                onChange({ ...criterion, max: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </div>
        </>
      ) : (
        <div className="w-28">
          <Label className="text-xs text-muted-foreground">Value</Label>
          <Input
            className="h-9"
            type="number"
            placeholder="Value"
            value={criterion.value ?? ""}
            onChange={(e) =>
              onChange({ ...criterion, value: e.target.value ? Number(e.target.value) : undefined })
            }
          />
        </div>
      )}
      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

function StructureCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: StructureCriterion;
  onChange: (c: StructureCriterion) => void;
  onRemove: () => void;
}) {
  const [editorOpen, setEditorOpen] = useState(false);

  const previewSmiles =
    criterion.search_type === "substructure"
      ? criterion.smarts
      : criterion.search_type === "similarity"
        ? criterion.smiles
        : undefined;

  const isStructureMode =
    criterion.search_type === "substructure" ||
    criterion.search_type === "similarity";

  const editorOutputFormat =
    criterion.search_type === "substructure" ? "smarts" : "smiles";

  const handleEditorApply = (structure: string) => {
    if (criterion.search_type === "substructure") {
      onChange({ ...criterion, smarts: structure });
    } else {
      onChange({ ...criterion, smiles: structure });
    }
  };

  return (
    <div className="flex items-start gap-2">
      {previewSmiles && previewSmiles.length >= 2 && (
        <div className="shrink-0 rounded border border-border bg-muted/30 p-1">
          <StructureRenderer
            smiles={previewSmiles}
            width={100}
            height={80}
          />
        </div>
      )}

      <div className="flex flex-1 flex-wrap items-end gap-2">
        <div className="w-48">
          <Label className="text-xs text-muted-foreground">Search Type</Label>
          <Select
            value={criterion.search_type}
            onValueChange={(v) =>
              onChange({ ...criterion, search_type: v as StructureSearchType })
            }
          >
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STRUCTURE_TYPES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {criterion.search_type === "substructure" && (
          <div className="flex-1 min-w-[200px]">
            <Label className="text-xs text-muted-foreground">SMARTS</Label>
            <div className="flex gap-1">
              <Input
                className="h-9 font-mono text-xs"
                placeholder="e.g. c1ccccc1"
                value={criterion.smarts ?? ""}
                onChange={(e) => onChange({ ...criterion, smarts: e.target.value })}
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={() => setEditorOpen(true)}
                title="Draw structure"
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
        {criterion.search_type === "similarity" && (
          <>
            <div className="flex-1 min-w-[200px]">
              <Label className="text-xs text-muted-foreground">SMILES</Label>
              <div className="flex gap-1">
                <Input
                  className="h-9 font-mono text-xs"
                  placeholder="e.g. CCO"
                  value={criterion.smiles ?? ""}
                  onChange={(e) => onChange({ ...criterion, smiles: e.target.value })}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="h-9 w-9 shrink-0"
                  onClick={() => setEditorOpen(true)}
                  title="Draw structure"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            <div className="w-28">
              <Label className="text-xs text-muted-foreground">
                Threshold ({criterion.threshold?.toFixed(2) ?? "0.70"})
              </Label>
              <Input
                className="h-9"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={criterion.threshold ?? 0.7}
                onChange={(e) => onChange({ ...criterion, threshold: Number(e.target.value) })}
              />
            </div>
          </>
        )}
        {criterion.search_type === "exact" && (
          <div className="flex-1 min-w-[200px]">
            <Label className="text-xs text-muted-foreground">InChI Key</Label>
            <Input
              className="h-9 font-mono text-xs"
              placeholder="e.g. BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
              value={criterion.inchi_key ?? ""}
              onChange={(e) => onChange({ ...criterion, inchi_key: e.target.value })}
            />
          </div>
        )}
        <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
          <Trash2 className="h-4 w-4 text-muted-foreground" />
        </Button>
      </div>

      {isStructureMode && (
        <StructureEditorDialog
          open={editorOpen}
          onOpenChange={setEditorOpen}
          initialStructure={previewSmiles ?? ""}
          onApply={handleEditorApply}
          outputFormat={editorOutputFormat}
        />
      )}
    </div>
  );
}

function ActivityCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: ActivityCriterion;
  onChange: (c: ActivityCriterion) => void;
  onRemove: () => void;
}) {
  const { data: protocols } = useProtocols();
  const { data: protocol } = useProtocol(criterion.protocol_id || undefined);

  return (
    <div className="flex items-end gap-2 flex-wrap">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Protocol</Label>
        <Select
          value={criterion.protocol_id || undefined}
          onValueChange={(v) =>
            onChange({ ...criterion, protocol_id: v, readout_definition_id: undefined, curve_type: undefined })
          }
        >
          <SelectTrigger className="h-9">
            <SelectValue placeholder="Select protocol..." />
          </SelectTrigger>
          <SelectContent>
            {protocols
              ?.filter((p) => p.status === "active")
              .map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Readout / Curve</Label>
        <Select
          value={criterion.readout_definition_id ?? criterion.curve_type ?? undefined}
          onValueChange={(v) => {
            const isCurve = CURVE_TYPE_OPTIONS.some((ct) => ct.value === v);
            if (isCurve) {
              onChange({ ...criterion, curve_type: v, readout_definition_id: undefined });
            } else {
              onChange({ ...criterion, readout_definition_id: v, curve_type: undefined });
            }
          }}
        >
          <SelectTrigger className="h-9">
            <SelectValue placeholder="Select..." />
          </SelectTrigger>
          <SelectContent>
            {protocol?.readout_definitions
              ?.filter((rd) => rd.data_type === "numeric")
              .map((rd) => (
                <SelectItem key={rd.id} value={rd.id}>
                  {rd.name}{rd.unit ? ` (${rd.unit})` : ""}
                </SelectItem>
              ))}
            {CURVE_TYPE_OPTIONS.map((ct) => (
              <SelectItem key={ct.value} value={ct.value}>
                {ct.label} (curve)
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Operator</Label>
        <Select
          value={criterion.operator}
          onValueChange={(v) => onChange({ ...criterion, operator: v as PropertyOperator })}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROPERTY_OPERATORS.filter((o) => o.value !== "between").map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="w-28">
        <Label className="text-xs text-muted-foreground">Value</Label>
        <Input
          className="h-9"
          type="number"
          placeholder="Value"
          value={criterion.value ?? ""}
          onChange={(e) =>
            onChange({ ...criterion, value: e.target.value ? Number(e.target.value) : 0 })
          }
        />
      </div>
      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

function CollectionCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: CollectionCriterion;
  onChange: (c: CollectionCriterion) => void;
  onRemove: () => void;
}) {
  const { data: collections } = useCollections();

  return (
    <div className="flex items-end gap-2">
      <div className="w-64">
        <Label className="text-xs text-muted-foreground">In Collection</Label>
        <Select
          value={criterion.collection_id || undefined}
          onValueChange={(v) => onChange({ ...criterion, collection_id: v })}
        >
          <SelectTrigger className="h-9">
            <SelectValue placeholder="Select collection..." />
          </SelectTrigger>
          <SelectContent>
            {collections?.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name} ({c.molecule_count})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

function KeywordListCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: KeywordListCriterion;
  onChange: (c: KeywordListCriterion) => void;
  onRemove: () => void;
}) {
  const rawText = criterion.values.join("\n");

  function handleTextChange(text: string) {
    const parsed = text
      .split(/[,\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    onChange({ ...criterion, values: parsed });
  }

  return (
    <div className="flex items-start gap-2">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">Identifier Type</Label>
        <Select
          value={criterion.ref_type}
          onValueChange={(v) => onChange({ ...criterion, ref_type: v as RefType })}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {REF_TYPE_OPTIONS.map((r) => (
              <SelectItem key={r.value} value={r.value}>
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex-1">
        <Label className="text-xs text-muted-foreground">
          Values ({criterion.values.length} identifier{criterion.values.length !== 1 ? "s" : ""})
        </Label>
        <textarea
          className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring h-20 font-mono text-xs resize-y"
          placeholder="One per line, or comma-separated..."
          value={rawText}
          onChange={(e) => handleTextChange(e.target.value)}
        />
      </div>
      <Button variant="ghost" size="icon" className="mt-5 h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

function RunDateCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: RunDateCriterion;
  onChange: (c: RunDateCriterion) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-end gap-2">
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">From</Label>
        <Input
          className="h-9"
          type="date"
          value={criterion.date_from ?? ""}
          onChange={(e) => onChange({ ...criterion, date_from: e.target.value || undefined })}
        />
      </div>
      <div className="w-44">
        <Label className="text-xs text-muted-foreground">To</Label>
        <Input
          className="h-9"
          type="date"
          value={criterion.date_to ?? ""}
          onChange={(e) => onChange({ ...criterion, date_to: e.target.value || undefined })}
        />
      </div>
      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

function BatchCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: BatchCriterion;
  onChange: (c: BatchCriterion) => void;
  onRemove: () => void;
}) {
  const ft = criterion.field_type || "text";

  return (
    <div className="flex items-end gap-2 flex-wrap">
      <div className="w-32">
        <Label className="text-xs text-muted-foreground">Field Type</Label>
        <Select
          value={ft}
          onValueChange={(v) => {
            const newFt = v as BatchFieldType;
            if (newFt === "text") {
              onChange({ type: "batch", field_type: "text", field: "batch_number", operator: "contains", value: "" });
            } else if (newFt === "numeric") {
              onChange({ type: "batch", field_type: "numeric", field: "purity", operator: "gte", value: undefined });
            } else {
              onChange({ type: "batch", field_type: "date" });
            }
          }}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {BATCH_FIELD_TYPE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {ft === "text" && (
        <>
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">Field</Label>
            <Select
              value={criterion.field || "batch_number"}
              onValueChange={(v) => onChange({ ...criterion, field: v })}
            >
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {BATCH_TEXT_FIELDS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-32">
            <Label className="text-xs text-muted-foreground">Operator</Label>
            <Select
              value={(criterion.operator as string) || "contains"}
              onValueChange={(v) => onChange({ ...criterion, operator: v as TextOperator })}
            >
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {TEXT_OPERATORS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex-1 min-w-[120px]">
            <Label className="text-xs text-muted-foreground">Value</Label>
            <Input
              className="h-9"
              placeholder="Search..."
              value={(criterion.value as string) ?? ""}
              onChange={(e) => onChange({ ...criterion, value: e.target.value })}
            />
          </div>
        </>
      )}

      {ft === "numeric" && (
        <>
          <div className="w-36">
            <Label className="text-xs text-muted-foreground">Field</Label>
            <Select
              value={criterion.field || "purity"}
              onValueChange={(v) => onChange({ ...criterion, field: v })}
            >
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {BATCH_NUMERIC_FIELDS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-24">
            <Label className="text-xs text-muted-foreground">Operator</Label>
            <Select
              value={(criterion.operator as string) || "gte"}
              onValueChange={(v) => onChange({ ...criterion, operator: v as PropertyOperator })}
            >
              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PROPERTY_OPERATORS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {criterion.operator === "between" ? (
            <>
              <div className="w-24">
                <Label className="text-xs text-muted-foreground">Min</Label>
                <Input
                  className="h-9" type="number" placeholder="Min"
                  value={criterion.min ?? ""}
                  onChange={(e) => onChange({ ...criterion, min: e.target.value ? Number(e.target.value) : undefined })}
                />
              </div>
              <div className="w-24">
                <Label className="text-xs text-muted-foreground">Max</Label>
                <Input
                  className="h-9" type="number" placeholder="Max"
                  value={criterion.max ?? ""}
                  onChange={(e) => onChange({ ...criterion, max: e.target.value ? Number(e.target.value) : undefined })}
                />
              </div>
            </>
          ) : (
            <div className="w-28">
              <Label className="text-xs text-muted-foreground">Value</Label>
              <Input
                className="h-9" type="number" placeholder="Value"
                value={(criterion.value as number) ?? ""}
                onChange={(e) => onChange({ ...criterion, value: e.target.value ? Number(e.target.value) : undefined })}
              />
            </div>
          )}
        </>
      )}

      {ft === "date" && (
        <>
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">From</Label>
            <Input
              className="h-9" type="date"
              value={criterion.date_from ?? ""}
              onChange={(e) => onChange({ ...criterion, date_from: e.target.value || undefined })}
            />
          </div>
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">To</Label>
            <Input
              className="h-9" type="date"
              value={criterion.date_to ?? ""}
              onChange={(e) => onChange({ ...criterion, date_to: e.target.value || undefined })}
            />
          </div>
        </>
      )}

      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

function ProjectCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: ProjectCriterion;
  onChange: (c: ProjectCriterion) => void;
  onRemove: () => void;
}) {
  const { data: projects } = useProjects();

  return (
    <div className="flex items-start gap-2 flex-wrap">
      <div className="flex items-end gap-2 flex-1 flex-wrap">
        <div className="w-56">
          <Label className="text-xs text-muted-foreground">Add Project</Label>
          <Select
            value=""
            onValueChange={(val) => {
              const current = criterion.project_ids ?? [];
              const updated = current.includes(val)
                ? current.filter((id) => id !== val)
                : [...current, val];
              onChange({ ...criterion, project_ids: updated });
            }}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Add project..." />
            </SelectTrigger>
            <SelectContent>
              {projects?.filter((p) => p.status === "active").map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-wrap gap-1 items-center min-h-9">
          {(criterion.project_ids ?? []).map((id) => {
            const proj = projects?.find((p) => p.id === id);
            return proj ? (
              <Badge key={id} variant="secondary" className="text-xs">
                {proj.name}
              </Badge>
            ) : null;
          })}
        </div>
      </div>
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0 self-end" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

const CUSTOM_FIELD_MODE_OPTIONS: { value: CustomFieldMode; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "numeric", label: "Numeric" },
];

function CustomFieldCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: CustomFieldCriterion;
  onChange: (c: CustomFieldCriterion) => void;
  onRemove: () => void;
}) {
  const isNumeric = criterion.mode === "numeric";
  const isBetween = criterion.operator === "between";

  return (
    <div className="flex items-end gap-2 flex-wrap">
      <div className="w-36">
        <Label className="text-xs text-muted-foreground">Field Name</Label>
        <Input
          className="h-9"
          placeholder="e.g. solubility"
          value={criterion.field}
          onChange={(e) => onChange({ ...criterion, field: e.target.value })}
        />
      </div>
      <div className="w-28">
        <Label className="text-xs text-muted-foreground">Mode</Label>
        <Select
          value={criterion.mode}
          onValueChange={(v) => {
            const m = v as CustomFieldMode;
            if (m === "text") {
              onChange({ ...criterion, mode: m, operator: "contains", value: "", min: undefined, max: undefined });
            } else {
              onChange({ ...criterion, mode: m, operator: "gte", value: undefined, min: undefined, max: undefined });
            }
          }}
        >
          <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
          <SelectContent>
            {CUSTOM_FIELD_MODE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="w-28">
        <Label className="text-xs text-muted-foreground">Operator</Label>
        <Select
          value={(criterion.operator as string) || (isNumeric ? "gte" : "contains")}
          onValueChange={(v) => onChange({ ...criterion, operator: v as TextOperator | PropertyOperator })}
        >
          <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
          <SelectContent>
            {isNumeric
              ? PROPERTY_OPERATORS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))
              : TEXT_OPERATORS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
          </SelectContent>
        </Select>
      </div>
      {isNumeric && isBetween ? (
        <>
          <div className="w-24">
            <Label className="text-xs text-muted-foreground">Min</Label>
            <Input
              className="h-9" type="number" placeholder="Min"
              value={criterion.min ?? ""}
              onChange={(e) => onChange({ ...criterion, min: e.target.value ? Number(e.target.value) : undefined })}
            />
          </div>
          <div className="w-24">
            <Label className="text-xs text-muted-foreground">Max</Label>
            <Input
              className="h-9" type="number" placeholder="Max"
              value={criterion.max ?? ""}
              onChange={(e) => onChange({ ...criterion, max: e.target.value ? Number(e.target.value) : undefined })}
            />
          </div>
        </>
      ) : (
        <div className="flex-1 min-w-[120px]">
          <Label className="text-xs text-muted-foreground">Value</Label>
          <Input
            className="h-9"
            type={isNumeric ? "number" : "text"}
            placeholder={isNumeric ? "Value" : "Search text..."}
            value={criterion.value ?? ""}
            onChange={(e) =>
              onChange({
                ...criterion,
                value: isNumeric ? (e.target.value ? Number(e.target.value) : undefined) : e.target.value,
              })
            }
          />
        </div>
      )}
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

function GroupCriterionRow({
  criterion,
  onChange,
  onRemove,
  depth,
}: {
  criterion: GroupCriterion;
  onChange: (c: GroupCriterion) => void;
  onRemove: () => void;
  depth: number;
}) {
  const borderColors = ["border-blue-500/40", "border-amber-500/40", "border-emerald-500/40", "border-purple-500/40"];
  const borderColor = borderColors[depth % borderColors.length];

  function addSubCriterion(c: SearchCriterion) {
    onChange({ ...criterion, criteria: [...criterion.criteria, c] });
  }

  function updateSubCriterion(index: number, updated: SearchCriterion) {
    onChange({
      ...criterion,
      criteria: criterion.criteria.map((c, i) => (i === index ? updated : c)),
    });
  }

  function removeSubCriterion(index: number) {
    onChange({
      ...criterion,
      criteria: criterion.criteria.filter((_, i) => i !== index),
    });
  }

  return (
    <div className={`space-y-2 rounded-lg border-2 border-dashed ${borderColor} p-3`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Group className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">Group</span>
          <Select
            value={criterion.logic}
            onValueChange={(v) => onChange({ ...criterion, logic: v as "and" | "or" })}
          >
            <SelectTrigger className="h-7 w-16 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="and">AND</SelectItem>
              <SelectItem value="or">OR</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-1">
          <Select
            value=""
            onValueChange={(v) => {
              const factories: Record<string, () => SearchCriterion> = {
                text: defaultTextCriterion,
                property: defaultPropertyCriterion,
                structure: defaultStructureCriterion,
                activity: defaultActivityCriterion,
                collection: defaultCollectionCriterion,
                custom_field: defaultCustomFieldCriterion,
              };
              const factory = factories[v];
              if (factory) addSubCriterion(factory());
            }}
          >
            <SelectTrigger className="h-7 w-24 text-xs">
              <SelectValue placeholder="+ Add..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="text">Text</SelectItem>
              <SelectItem value="property">Property</SelectItem>
              <SelectItem value="structure">Structure</SelectItem>
              <SelectItem value="activity">Activity</SelectItem>
              <SelectItem value="collection">Collection</SelectItem>
              <SelectItem value="custom_field">Custom Field</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onRemove}>
            <Trash2 className="h-4 w-4 text-muted-foreground" />
          </Button>
        </div>
      </div>
      {criterion.criteria.length === 0 && (
        <p className="text-xs text-muted-foreground text-center py-2">
          Add criteria to this group
        </p>
      )}
      <div className="space-y-2">
        {criterion.criteria.map((sub, i) => {
          const key = `group-${depth}-${sub.type}-${i}`;
          // Render sub-criteria (simplified — no NOT toggle inside groups for now, use negate on the sub directly)
          if (sub.type === "text") return <TextCriterionRow key={key} criterion={sub} onChange={(c) => updateSubCriterion(i, c)} onRemove={() => removeSubCriterion(i)} />;
          if (sub.type === "property") return <PropertyCriterionRow key={key} criterion={sub} onChange={(c) => updateSubCriterion(i, c)} onRemove={() => removeSubCriterion(i)} />;
          if (sub.type === "structure") return <StructureCriterionRow key={key} criterion={sub} onChange={(c) => updateSubCriterion(i, c)} onRemove={() => removeSubCriterion(i)} />;
          if (sub.type === "activity") return <ActivityCriterionRow key={key} criterion={sub} onChange={(c) => updateSubCriterion(i, c)} onRemove={() => removeSubCriterion(i)} />;
          if (sub.type === "collection") return <CollectionCriterionRow key={key} criterion={sub} onChange={(c) => updateSubCriterion(i, c)} onRemove={() => removeSubCriterion(i)} />;
          if (sub.type === "custom_field") return <CustomFieldCriterionRow key={key} criterion={sub} onChange={(c) => updateSubCriterion(i, c)} onRemove={() => removeSubCriterion(i)} />;
          if (sub.type === "group" && depth < 3) return <GroupCriterionRow key={key} criterion={sub} onChange={(c) => updateSubCriterion(i, c)} onRemove={() => removeSubCriterion(i)} depth={depth + 1} />;
          return null;
        })}
      </div>
    </div>
  );
}

function NegateToggle({
  negate,
  onToggle,
}: {
  negate: boolean;
  onToggle: (v: boolean) => void;
}) {
  return (
    <Button
      type="button"
      variant={negate ? "destructive" : "outline"}
      size="sm"
      className="h-7 px-2 text-xs shrink-0 self-end mb-0.5"
      onClick={() => onToggle(!negate)}
      title={negate ? "Click to remove NOT" : "Click to negate this criterion"}
    >
      {negate ? "NOT" : "IS"}
    </Button>
  );
}

function SelectivityCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: SelectivityCriterion;
  onChange: (c: SelectivityCriterion) => void;
  onRemove: () => void;
}) {
  const { data: protocols } = useProtocols();
  const activeProtocols = protocols?.filter((p) => p.status === "active");

  return (
    <div className="space-y-2 rounded border border-dashed border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          Selectivity — counter / target ratio
        </span>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onRemove}>
          <Trash2 className="h-4 w-4 text-muted-foreground" />
        </Button>
      </div>
      <div className="flex items-end gap-2 flex-wrap">
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Target Protocol</Label>
          <Select
            value={criterion.target_protocol_id || undefined}
            onValueChange={(v) => onChange({ ...criterion, target_protocol_id: v })}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {activeProtocols?.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-28">
          <Label className="text-xs text-muted-foreground">Curve</Label>
          <Select
            value={criterion.target_curve_type}
            onValueChange={(v) => onChange({ ...criterion, target_curve_type: v })}
          >
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              {CURVE_TYPE_OPTIONS.map((ct) => (
                <SelectItem key={ct.value} value={ct.value}>{ct.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex items-end gap-2 flex-wrap">
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Counter Protocol</Label>
          <Select
            value={criterion.counter_protocol_id || undefined}
            onValueChange={(v) => onChange({ ...criterion, counter_protocol_id: v })}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {activeProtocols?.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-28">
          <Label className="text-xs text-muted-foreground">Curve</Label>
          <Select
            value={criterion.counter_curve_type}
            onValueChange={(v) => onChange({ ...criterion, counter_curve_type: v })}
          >
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              {CURVE_TYPE_OPTIONS.map((ct) => (
                <SelectItem key={ct.value} value={ct.value}>{ct.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-20">
          <Label className="text-xs text-muted-foreground">Ratio</Label>
          <Select
            value={criterion.ratio_operator}
            onValueChange={(v) => onChange({ ...criterion, ratio_operator: v as PropertyOperator })}
          >
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              {PROPERTY_OPERATORS.filter((o) => o.value !== "between").map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-24">
          <Label className="text-xs text-muted-foreground">Value</Label>
          <Input
            className="h-9"
            type="number"
            placeholder="e.g. 100"
            value={criterion.ratio_value ?? ""}
            onChange={(e) =>
              onChange({ ...criterion, ratio_value: e.target.value ? Number(e.target.value) : 0 })
            }
          />
        </div>
      </div>
    </div>
  );
}

// ─── Main component ─────────────────────────────────────────────────────────

interface SearchQueryBuilderProps {
  initialQuery?: SearchQuery;
  onSearch: (query: SearchQuery) => void;
  isLoading?: boolean;
}

export function SearchQueryBuilder({
  initialQuery,
  onSearch,
  isLoading,
}: SearchQueryBuilderProps) {
  const [criteria, setCriteria] = useState<SearchCriterion[]>(
    initialQuery?.criteria ?? []
  );
  const [logic, setLogic] = useState<"and" | "or">(
    initialQuery?.logic ?? "and"
  );

  function updateCriterion(index: number, updated: SearchCriterion) {
    setCriteria((prev) => prev.map((c, i) => (i === index ? updated : c)));
  }

  function removeCriterion(index: number) {
    setCriteria((prev) => prev.filter((_, i) => i !== index));
  }

  function handleSearch() {
    onSearch({ criteria, logic });
  }

  return (
    <div className="space-y-4 rounded-lg border p-4">
      {/* Logic toggle + add buttons */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Label className="text-sm text-muted-foreground">Match</Label>
          <Select value={logic} onValueChange={(v) => setLogic(v as "and" | "or")}>
            <SelectTrigger className="h-8 w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="and">AND</SelectItem>
              <SelectItem value="or">OR</SelectItem>
            </SelectContent>
          </Select>
          <Label className="text-sm text-muted-foreground">of the following criteria</Label>
        </div>
        <Select
          value=""
          onValueChange={(v) => {
            const factories: Record<string, () => SearchCriterion> = {
              text: defaultTextCriterion,
              property: defaultPropertyCriterion,
              structure: defaultStructureCriterion,
              activity: defaultActivityCriterion,
              collection: defaultCollectionCriterion,
              keyword_list: defaultKeywordListCriterion,
              run_date: defaultRunDateCriterion,
              batch: defaultBatchCriterion,
              project: defaultProjectCriterion,
              selectivity: defaultSelectivityCriterion,
              custom_field: defaultCustomFieldCriterion,
              group: defaultGroupCriterion,
            };
            const factory = factories[v];
            if (factory) setCriteria([...criteria, factory()]);
          }}
        >
          <SelectTrigger className="h-8 w-44">
            <Plus className="mr-1 h-3.5 w-3.5" />
            <SelectValue placeholder="Add criterion..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="text">Text</SelectItem>
            <SelectItem value="property">Property</SelectItem>
            <SelectItem value="structure">Structure</SelectItem>
            <SelectItem value="activity">Activity</SelectItem>
            <SelectItem value="batch">Batch</SelectItem>
            <SelectItem value="collection">Collection</SelectItem>
            <SelectItem value="project">Project</SelectItem>
            <SelectItem value="keyword_list">Keyword List</SelectItem>
            <SelectItem value="run_date">Run Date</SelectItem>
            <SelectItem value="selectivity">Selectivity</SelectItem>
            <SelectItem value="custom_field">Custom Field</SelectItem>
            <SelectItem value="group">Group (nested)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Criteria rows */}
      {criteria.length === 0 && (
        <p className="py-4 text-center text-sm text-muted-foreground">
          Add criteria to build your search query.
        </p>
      )}

      <div className="space-y-3">
        {criteria.map((criterion, index) => {
          const key = `${criterion.type}-${index}`;
          const negate = criterion.negate ?? false;
          const toggleNegate = (v: boolean) =>
            updateCriterion(index, { ...criterion, negate: v || undefined });

          const wrapWithNegate = (row: React.ReactNode) => (
            <div key={key} className={`flex items-start gap-2 ${negate ? "ring-1 ring-destructive/30 rounded-md p-1" : ""}`}>
              <NegateToggle negate={negate} onToggle={toggleNegate} />
              <div className="flex-1">{row}</div>
            </div>
          );

          switch (criterion.type) {
            case "text":
              return wrapWithNegate(
                <TextCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "property":
              return wrapWithNegate(
                <PropertyCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "structure":
              return wrapWithNegate(
                <StructureCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "activity":
              return wrapWithNegate(
                <ActivityCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "collection":
              return wrapWithNegate(
                <CollectionCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "keyword_list":
              return wrapWithNegate(
                <KeywordListCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "run_date":
              return wrapWithNegate(
                <RunDateCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "batch":
              return wrapWithNegate(
                <BatchCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "project":
              return wrapWithNegate(
                <ProjectCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "selectivity":
              return wrapWithNegate(
                <SelectivityCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "custom_field":
              return wrapWithNegate(
                <CustomFieldCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "group":
              return wrapWithNegate(
                <GroupCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                  depth={0}
                />
              );
          }
        })}
      </div>

      {/* Search button */}
      <div className="flex justify-end">
        <Button
          onClick={handleSearch}
          disabled={criteria.length === 0 || isLoading}
        >
          <Search className="mr-2 h-4 w-4" />
          {isLoading ? "Searching..." : "Search"}
        </Button>
      </div>
    </div>
  );
}
