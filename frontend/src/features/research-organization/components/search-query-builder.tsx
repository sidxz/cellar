"use client";

import { useState } from "react";
import { Plus, Trash2, Search, Pencil } from "lucide-react";
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
import type {
  SearchCriterion,
  SearchQuery,
  TextCriterion,
  PropertyCriterion,
  StructureCriterion,
  TextOperator,
  PropertyOperator,
  StructureSearchType,
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
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCriteria([...criteria, defaultTextCriterion()])}
          >
            <Plus className="mr-1 h-3 w-3" />
            Text
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCriteria([...criteria, defaultPropertyCriterion()])}
          >
            <Plus className="mr-1 h-3 w-3" />
            Property
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCriteria([...criteria, defaultStructureCriterion()])}
          >
            <Plus className="mr-1 h-3 w-3" />
            Structure
          </Button>
        </div>
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
          switch (criterion.type) {
            case "text":
              return (
                <TextCriterionRow
                  key={key}
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, c)}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "property":
              return (
                <PropertyCriterionRow
                  key={key}
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, c)}
                  onRemove={() => removeCriterion(index)}
                />
              );
            case "structure":
              return (
                <StructureCriterionRow
                  key={key}
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, c)}
                  onRemove={() => removeCriterion(index)}
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
