"use client";

import { useProtocol, useProtocols } from "@/features/screening-assay/hooks/use-protocols";
import { CURVE_TYPE_LABELS } from "@/features/screening-assay/types";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { Collapsible } from "radix-ui";
import { useEffect, useState } from "react";
import type {
  BatchCriterion,
  BatchFieldType,
  CustomFieldCriterion,
  CustomFieldMode,
  KeywordListCriterion,
  PropertyOperator,
  RefType,
  RunDateCriterion,
  SelectivityCriterion,
  TextOperator,
} from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const PROPERTY_OPERATORS: { value: PropertyOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
  { value: "between", label: "Between" },
];

const TEXT_OPERATORS: { value: TextOperator; label: string }[] = [
  { value: "contains", label: "Contains" },
  { value: "equals", label: "Equals" },
  { value: "starts_with", label: "Starts With" },
];

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

const REF_TYPE_OPTIONS: { value: RefType; label: string }[] = [
  { value: "registration_number", label: "Registration Number" },
  { value: "name", label: "Name" },
  { value: "external_id", label: "External ID" },
  { value: "smiles", label: "SMILES" },
  { value: "inchi_key", label: "InChI Key" },
];

const CUSTOM_FIELD_MODE_OPTIONS: { value: CustomFieldMode; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "numeric", label: "Numeric" },
];

// ─── Default factories ──────────────────────────────────────────────────────

function defaultSelectivity(): SelectivityCriterion {
  return {
    type: "selectivity",
    target_readout_definition_id: "",
    counter_readout_definition_id: "",
    ratio_operator: "gte",
    ratio_value: 100,
  };
}

function defaultBatch(): BatchCriterion {
  return {
    type: "batch",
    field_type: "text",
    field: "batch_number",
    operator: "contains",
    value: "",
  };
}

function defaultRunDate(): RunDateCriterion {
  return { type: "run_date" };
}

function defaultCustomField(): CustomFieldCriterion {
  return { type: "custom_field", field: "", mode: "text", operator: "contains", value: "" };
}

function defaultKeywordList(): KeywordListCriterion {
  return { type: "keyword_list", values: [], ref_type: "registration_number" };
}

// ─── Selectivity sub-component ──────────────────────────────────────────────

function SelectivityTerm({
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

  // The selectivity criterion stores readout-def UUIDs (post-033), but the
  // user picks Protocol -> Readout. Two transient picker-state values let
  // us scope the readout-def dropdown to a chosen protocol without
  // mutating the criterion until both halves are selected.
  const [targetProtocolId, setTargetProtocolId] = useState<string>("");
  const [counterProtocolId, setCounterProtocolId] = useState<string>("");
  const { data: targetProtocol } = useProtocol(targetProtocolId);
  const { data: counterProtocol } = useProtocol(counterProtocolId);

  const targetDrReadouts =
    targetProtocol?.readout_definitions?.filter((rd) => rd.dose_response_config) ?? [];
  const counterDrReadouts =
    counterProtocol?.readout_definitions?.filter((rd) => rd.dose_response_config) ?? [];

  return (
    <div className="space-y-2 rounded border border-dashed border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          Selectivity -- counter / target ratio
        </span>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onRemove}>
          <Trash2 className="h-4 w-4 text-muted-foreground" />
        </Button>
      </div>
      <div className="flex items-end gap-2 flex-wrap">
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Target Protocol</Label>
          <Select
            value={targetProtocolId || undefined}
            onValueChange={(v) => {
              setTargetProtocolId(v);
              onChange({ ...criterion, target_readout_definition_id: "" });
            }}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {activeProtocols?.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Readout</Label>
          <Select
            value={criterion.target_readout_definition_id || undefined}
            onValueChange={(v) => onChange({ ...criterion, target_readout_definition_id: v })}
            disabled={!targetProtocolId}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {targetDrReadouts.map((rd) => {
                const ct = rd.dose_response_config?.curve_type;
                const suffix = ct ? ` (${CURVE_TYPE_LABELS[ct] ?? ct.toUpperCase()})` : "";
                return (
                  <SelectItem key={rd.id} value={rd.id}>
                    {rd.name}
                    {suffix}
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex items-end gap-2 flex-wrap">
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Counter Protocol</Label>
          <Select
            value={counterProtocolId || undefined}
            onValueChange={(v) => {
              setCounterProtocolId(v);
              onChange({ ...criterion, counter_readout_definition_id: "" });
            }}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {activeProtocols?.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Readout</Label>
          <Select
            value={criterion.counter_readout_definition_id || undefined}
            onValueChange={(v) => onChange({ ...criterion, counter_readout_definition_id: v })}
            disabled={!counterProtocolId}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {counterDrReadouts.map((rd) => {
                const ct = rd.dose_response_config?.curve_type;
                const suffix = ct ? ` (${CURVE_TYPE_LABELS[ct] ?? ct.toUpperCase()})` : "";
                return (
                  <SelectItem key={rd.id} value={rd.id}>
                    {rd.name}
                    {suffix}
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
        <div className="w-20">
          <Label className="text-xs text-muted-foreground">Ratio</Label>
          <Select
            value={criterion.ratio_operator}
            onValueChange={(v) => onChange({ ...criterion, ratio_operator: v as PropertyOperator })}
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

// ─── Batch sub-component ────────────────────────────────────────────────────

function BatchTerm({
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
              onChange({
                type: "batch",
                field_type: "text",
                field: "batch_number",
                operator: "contains",
                value: "",
              });
            } else if (newFt === "numeric") {
              onChange({
                type: "batch",
                field_type: "numeric",
                field: "purity",
                operator: "gte",
                value: undefined,
              });
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
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
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
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BATCH_TEXT_FIELDS.map((f) => (
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
              value={(criterion.operator as string) || "contains"}
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
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BATCH_NUMERIC_FIELDS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>
                    {f.label}
                  </SelectItem>
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
          {criterion.operator === "between" ? (
            <>
              <div className="w-24">
                <Label className="text-xs text-muted-foreground">Min</Label>
                <Input
                  className="h-9"
                  type="number"
                  placeholder="Min"
                  value={criterion.min ?? ""}
                  onChange={(e) =>
                    onChange({
                      ...criterion,
                      min: e.target.value ? Number(e.target.value) : undefined,
                    })
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
                    onChange({
                      ...criterion,
                      max: e.target.value ? Number(e.target.value) : undefined,
                    })
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
                value={(criterion.value as number) ?? ""}
                onChange={(e) =>
                  onChange({
                    ...criterion,
                    value: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
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
        </>
      )}

      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

// ─── Run date sub-component ─────────────────────────────────────────────────

function RunDateTerm({
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

// ─── Custom field sub-component ─────────────────────────────────────────────

function CustomFieldTerm({
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
              onChange({
                ...criterion,
                mode: m,
                operator: "contains",
                value: "",
                min: undefined,
                max: undefined,
              });
            } else {
              onChange({
                ...criterion,
                mode: m,
                operator: "gte",
                value: undefined,
                min: undefined,
                max: undefined,
              });
            }
          }}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CUSTOM_FIELD_MODE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="w-28">
        <Label className="text-xs text-muted-foreground">Operator</Label>
        <Select
          value={(criterion.operator as string) || (isNumeric ? "gte" : "contains")}
          onValueChange={(v) =>
            onChange({ ...criterion, operator: v as TextOperator | PropertyOperator })
          }
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {isNumeric
              ? PROPERTY_OPERATORS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))
              : TEXT_OPERATORS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
          </SelectContent>
        </Select>
      </div>
      {isNumeric && isBetween ? (
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
                value: isNumeric
                  ? e.target.value
                    ? Number(e.target.value)
                    : undefined
                  : e.target.value,
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

// ─── Keyword list sub-component ─────────────────────────────────────────────

function KeywordListTerm({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: KeywordListCriterion;
  onChange: (c: KeywordListCriterion) => void;
  onRemove: () => void;
}) {
  // Local state prevents cursor jumps from round-tripping through
  // criterion.values on every keystroke. Sync to parent only on blur.
  const [rawText, setRawText] = useState(criterion.values.join("\n"));

  // Re-sync local text when criterion changes externally (e.g. loading saved search)
  const canonicalValues = criterion.values.join(",");
  useEffect(() => {
    setRawText(criterion.values.join("\n"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canonicalValues]);

  function handleBlur() {
    const parsed = rawText
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
          onChange={(e) => setRawText(e.target.value)}
          onBlur={handleBlur}
        />
      </div>
      <Button variant="ghost" size="icon" className="mt-5 h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

// ─── Main advanced filters section ──────────────────────────────────────────

export interface AdvancedFiltersState {
  selectivity: SelectivityCriterion[];
  batch: BatchCriterion[];
  runDate: RunDateCriterion[];
  customFields: CustomFieldCriterion[];
  keywordLists: KeywordListCriterion[];
}

export function emptyAdvancedFilters(): AdvancedFiltersState {
  return {
    selectivity: [],
    batch: [],
    runDate: [],
    customFields: [],
    keywordLists: [],
  };
}

interface AdvancedFiltersProps {
  state: AdvancedFiltersState;
  onChange: (state: AdvancedFiltersState) => void;
}

export function AdvancedFilters({ state, onChange }: AdvancedFiltersProps) {
  const [open, setOpen] = useState(false);

  const totalTerms =
    state.selectivity.length +
    state.batch.length +
    state.runDate.length +
    state.customFields.length +
    state.keywordLists.length;

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <Collapsible.Trigger asChild>
        <Button
          type="button"
          variant="ghost"
          className="flex w-full items-center justify-between h-9 px-2"
        >
          <span className="flex items-center gap-2 text-sm font-medium">
            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            More Filters
            {totalTerms > 0 && (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                {totalTerms}
              </span>
            )}
          </span>
        </Button>
      </Collapsible.Trigger>

      <Collapsible.Content>
        <div className="space-y-4 pt-2">
          {/* Selectivity */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium text-muted-foreground">Selectivity</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-xs"
                onClick={() =>
                  onChange({ ...state, selectivity: [...state.selectivity, defaultSelectivity()] })
                }
              >
                <Plus className="mr-1 h-3 w-3" /> Add
              </Button>
            </div>
            {state.selectivity.map((c, i) => (
              <SelectivityTerm
                key={`sel-${i}`}
                criterion={c}
                onChange={(updated) =>
                  onChange({
                    ...state,
                    selectivity: state.selectivity.map((s, j) => (j === i ? updated : s)),
                  })
                }
                onRemove={() =>
                  onChange({ ...state, selectivity: state.selectivity.filter((_, j) => j !== i) })
                }
              />
            ))}
          </div>

          {/* Batch */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium text-muted-foreground">Batch Fields</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-xs"
                onClick={() => onChange({ ...state, batch: [...state.batch, defaultBatch()] })}
              >
                <Plus className="mr-1 h-3 w-3" /> Add
              </Button>
            </div>
            {state.batch.map((c, i) => (
              <BatchTerm
                key={`batch-${i}`}
                criterion={c}
                onChange={(updated) =>
                  onChange({ ...state, batch: state.batch.map((s, j) => (j === i ? updated : s)) })
                }
                onRemove={() =>
                  onChange({ ...state, batch: state.batch.filter((_, j) => j !== i) })
                }
              />
            ))}
          </div>

          {/* Run Date */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium text-muted-foreground">Run Date</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-xs"
                onClick={() =>
                  onChange({ ...state, runDate: [...state.runDate, defaultRunDate()] })
                }
              >
                <Plus className="mr-1 h-3 w-3" /> Add
              </Button>
            </div>
            {state.runDate.map((c, i) => (
              <RunDateTerm
                key={`rundate-${i}`}
                criterion={c}
                onChange={(updated) =>
                  onChange({
                    ...state,
                    runDate: state.runDate.map((s, j) => (j === i ? updated : s)),
                  })
                }
                onRemove={() =>
                  onChange({ ...state, runDate: state.runDate.filter((_, j) => j !== i) })
                }
              />
            ))}
          </div>

          {/* Custom Fields */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium text-muted-foreground">Custom Fields</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-xs"
                onClick={() =>
                  onChange({
                    ...state,
                    customFields: [...state.customFields, defaultCustomField()],
                  })
                }
              >
                <Plus className="mr-1 h-3 w-3" /> Add
              </Button>
            </div>
            {state.customFields.map((c, i) => (
              <CustomFieldTerm
                key={`cf-${i}`}
                criterion={c}
                onChange={(updated) =>
                  onChange({
                    ...state,
                    customFields: state.customFields.map((s, j) => (j === i ? updated : s)),
                  })
                }
                onRemove={() =>
                  onChange({ ...state, customFields: state.customFields.filter((_, j) => j !== i) })
                }
              />
            ))}
          </div>

          {/* Keyword List */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium text-muted-foreground">Keyword List</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-xs"
                onClick={() =>
                  onChange({
                    ...state,
                    keywordLists: [...state.keywordLists, defaultKeywordList()],
                  })
                }
              >
                <Plus className="mr-1 h-3 w-3" /> Add
              </Button>
            </div>
            {state.keywordLists.map((c, i) => (
              <KeywordListTerm
                key={`kwl-${i}`}
                criterion={c}
                onChange={(updated) =>
                  onChange({
                    ...state,
                    keywordLists: state.keywordLists.map((s, j) => (j === i ? updated : s)),
                  })
                }
                onRemove={() =>
                  onChange({ ...state, keywordLists: state.keywordLists.filter((_, j) => j !== i) })
                }
              />
            ))}
          </div>
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
