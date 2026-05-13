"use client";

import { useProtocol, useProtocols } from "@/features/screening-assay/hooks/use-protocols";
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
import { Group, Trash2 } from "lucide-react";
import {
  BATCH_FIELD_TYPE_OPTIONS,
  BATCH_NUMERIC_FIELDS,
  BATCH_TEXT_FIELDS,
  CURVE_TYPE_OPTIONS,
  CUSTOM_FIELD_MODE_OPTIONS,
  PROPERTY_OPERATORS,
  TEXT_OPERATORS,
  defaultActivityCriterion,
  defaultCollectionCriterion,
  defaultCustomFieldCriterion,
  defaultPropertyCriterion,
  defaultStructureCriterion,
  defaultTextCriterion,
} from "../../lib/search-query-config";
import type {
  ActivityCriterion,
  BatchCriterion,
  BatchFieldType,
  CustomFieldCriterion,
  CustomFieldMode,
  GroupCriterion,
  PropertyOperator,
  SearchCriterion,
  TextOperator,
} from "../../types";
import { CollectionCriterionRow } from "./resource-rows";
import { TextCriterionRow } from "./simple-rows";
import { PropertyCriterionRow } from "./simple-rows";
import { StructureCriterionRow } from "./structure-rows";

export function ActivityCriterionRow({
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
            onChange({
              ...criterion,
              protocol_id: v,
              readout_definition_id: undefined,
              curve_type: undefined,
            })
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
                  {rd.name}
                  {rd.unit ? ` (${rd.unit})` : ""}
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

export function BatchCriterionRow({
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

export function CustomFieldCriterionRow({
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

export function GroupCriterionRow({
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
  const borderColors = [
    "border-primary/40",
    "border-warning/40",
    "border-success/40",
    "border-info/40",
  ];
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
        <p className="text-xs text-muted-foreground text-center py-2">Add criteria to this group</p>
      )}
      <div className="space-y-2">
        {criterion.criteria.map((sub, i) => {
          const key = `group-${depth}-${sub.type}-${i}`;
          // Render sub-criteria (simplified — no NOT toggle inside groups for now, use negate on the sub directly)
          if (sub.type === "text")
            return (
              <TextCriterionRow
                key={key}
                criterion={sub}
                onChange={(c) => updateSubCriterion(i, c)}
                onRemove={() => removeSubCriterion(i)}
              />
            );
          if (sub.type === "property")
            return (
              <PropertyCriterionRow
                key={key}
                criterion={sub}
                onChange={(c) => updateSubCriterion(i, c)}
                onRemove={() => removeSubCriterion(i)}
              />
            );
          if (sub.type === "structure")
            return (
              <StructureCriterionRow
                key={key}
                criterion={sub}
                onChange={(c) => updateSubCriterion(i, c)}
                onRemove={() => removeSubCriterion(i)}
              />
            );
          if (sub.type === "activity")
            return (
              <ActivityCriterionRow
                key={key}
                criterion={sub}
                onChange={(c) => updateSubCriterion(i, c)}
                onRemove={() => removeSubCriterion(i)}
              />
            );
          if (sub.type === "collection")
            return (
              <CollectionCriterionRow
                key={key}
                criterion={sub}
                onChange={(c) => updateSubCriterion(i, c)}
                onRemove={() => removeSubCriterion(i)}
              />
            );
          if (sub.type === "custom_field")
            return (
              <CustomFieldCriterionRow
                key={key}
                criterion={sub}
                onChange={(c) => updateSubCriterion(i, c)}
                onRemove={() => removeSubCriterion(i)}
              />
            );
          if (sub.type === "group" && depth < 3)
            return (
              <GroupCriterionRow
                key={key}
                criterion={sub}
                onChange={(c) => updateSubCriterion(i, c)}
                onRemove={() => removeSubCriterion(i)}
                depth={depth + 1}
              />
            );
          return null;
        })}
      </div>
    </div>
  );
}
