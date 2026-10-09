"use client";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
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
import { UnitPicker } from "@/shared/components/unit-picker";
import { ChevronDown, Trash2 } from "lucide-react";
import { Controller, type UseFormReturn } from "react-hook-form";
import {
  VISIBLE_READOUT_DATA_TYPES,
  WELL_CONC_X,
  isReservedReadoutName,
} from "../../lib/readout-constants";
import { moveTestConcentration, readoutTestConcentration } from "../../lib/test-concentration";
import {
  CURVE_TYPE_LABELS,
  type CurveType,
  HILL_SLOPE_CONSTRAINT_LABELS,
  type InterceptSpec,
  NORMALIZATION_SCOPE_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  type ReadoutDataType,
} from "../../types";
import { FormulaInput } from "../formula-input";
import { InterceptsEditor } from "../intercepts-editor";
import { PickListEditor } from "../pick-list-editor";
import { NormalizationCheckboxGroup } from "../readout-normalization-checkboxes";
import { VocabularyAutocomplete } from "../vocabulary-autocomplete";
import type { ProtocolFormValues } from "./form-values";

/** One readout: name and unit up front, everything else under "More options". */
export function ReadoutRow({
  form,
  index,
  readouts,
  crossProtocols,
  canRemove,
  onRemove,
}: {
  form: UseFormReturn<ProtocolFormValues>;
  index: number;
  readouts: ProtocolFormValues["readouts"];
  crossProtocols: { code: string; name: string }[];
  canRemove: boolean;
  onRemove: () => void;
}) {
  const rd = readouts[index];
  // Open when the data type cannot work until its own settings are filled in.
  const incomplete =
    (rd?.data_type === "pick_list" && rd.pick_list_values.length === 0) ||
    (rd?.data_type === "dose_response" && !rd.dr_y_readout);
  const concentration = rd ? readoutTestConcentration(rd.name) : null;
  const moveConcentration = () => {
    const moved = moveTestConcentration(rd?.name ?? "", form.getValues("conditions"));
    if (!moved) return;
    form.setValue(`readouts.${index}.name`, moved.name, { shouldDirty: true });
    form.setValue("conditions", moved.conditions as ProtocolFormValues["conditions"], {
      shouldDirty: true,
    });
  };
  const numericOthers = readouts.filter(
    (other, i) => i !== index && other.name.trim() && other.data_type === "numeric",
  );

  return (
    <Card>
      <CardContent className="pt-4">
        <Collapsible defaultOpen={incomplete}>
          <div className="flex items-start gap-3">
            <div className="grid flex-1 gap-1">
              <Label className="text-xs">Name</Label>
              <Controller
                control={form.control}
                name={`readouts.${index}.name`}
                render={({ field }) => (
                  <VocabularyAutocomplete
                    value={field.value ?? ""}
                    onChange={field.onChange}
                    placeholder="e.g., % Inhibition"
                    field="readout_name"
                  />
                )}
              />
              {concentration && (
                <p className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  Test concentration belongs in a condition
                  <Button
                    type="button"
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-[11px]"
                    onClick={moveConcentration}
                  >
                    Move
                  </Button>
                </p>
              )}
              {rd && isReservedReadoutName(rd.name) && (
                <p className="text-[11px] text-destructive">
                  Reserved well-metadata name — pick a different readout name (well concentration,
                  batch, and compound are tracked on the well, not as readouts).
                </p>
              )}
            </div>
            {rd?.data_type !== "pick_list" && (
              <div className="grid w-40 gap-1">
                <Label className="text-xs">Unit</Label>
                <Controller
                  control={form.control}
                  name={`readouts.${index}.unit`}
                  render={({ field }) => (
                    <UnitPicker value={field.value} onChange={field.onChange} />
                  )}
                />
              </div>
            )}
            <div className="mt-6 flex items-center gap-1">
              <span className="text-xs text-muted-foreground">
                {READOUT_DATA_TYPE_LABELS[rd?.data_type as ReadoutDataType] ?? rd?.data_type}
              </span>
              <CollapsibleTrigger asChild>
                <Button type="button" variant="ghost" size="sm" className="group">
                  More options
                  <ChevronDown className="ml-1 h-4 w-4 transition-transform group-data-[state=open]:rotate-180" />
                </Button>
              </CollapsibleTrigger>
              {canRemove && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Remove readout"
                  onClick={onRemove}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              )}
            </div>
          </div>

          <CollapsibleContent className="mt-3 grid gap-3">
            <div className="grid w-60 gap-1">
              <Label className="text-xs">Data Type</Label>
              <Controller
                control={form.control}
                name={`readouts.${index}.data_type`}
                render={({ field: f }) => (
                  <Select value={f.value} onValueChange={f.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VISIBLE_READOUT_DATA_TYPES.map((value) => (
                        <SelectItem key={value} value={value}>
                          {READOUT_DATA_TYPE_LABELS[value as keyof typeof READOUT_DATA_TYPE_LABELS]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            {/* Pick List Values */}
            {rd?.data_type === "pick_list" && (
              <div className="grid gap-1">
                <Label className="text-xs">Allowed Values</Label>
                <Controller
                  control={form.control}
                  name={`readouts.${index}.pick_list_values`}
                  render={({ field: f }) => (
                    <PickListEditor value={f.value} onChange={f.onChange} />
                  )}
                />
              </div>
            )}

            {/* Numeric measurement attributes */}
            {rd?.data_type !== "pick_list" && (
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1">
                  <Label className="text-xs">Aggregation</Label>
                  <Controller
                    control={form.control}
                    name={`readouts.${index}.aggregation`}
                    render={({ field: f }) => (
                      <Select value={f.value} onValueChange={f.onChange}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(READOUT_AGGREGATION_LABELS).map(([value, label]) => (
                            <SelectItem key={value} value={value}>
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Normalization</Label>
                  <Controller
                    control={form.control}
                    name={`readouts.${index}.normalizations`}
                    render={({ field: f }) => (
                      <NormalizationCheckboxGroup value={f.value} onChange={f.onChange} />
                    )}
                  />
                </div>
              </div>
            )}

            {/* Calculated readout toggle */}
            <div className="flex items-center gap-3">
              <Controller
                control={form.control}
                name={`readouts.${index}.is_calculated`}
                render={({ field: f }) => (
                  <Switch checked={f.value} onCheckedChange={f.onChange} size="sm" />
                )}
              />
              <Label className="text-xs">Calculated</Label>
            </div>
            {rd?.is_calculated && (
              <div className="grid gap-1">
                <Label className="text-xs">Formula</Label>
                <Controller
                  control={form.control}
                  name={`readouts.${index}.calculation_formula`}
                  render={({ field: f }) => (
                    <FormulaInput
                      value={f.value}
                      onChange={f.onChange}
                      availableReadoutNames={readouts
                        .filter((other, i) => i !== index && other.name.trim())
                        .map((r) => r.name.trim())}
                      protocols={crossProtocols}
                    />
                  )}
                />
                <p className="text-[11px] text-muted-foreground">
                  Use other readout names as variables. Type <code>@</code> for cross-protocol.
                </p>
              </div>
            )}

            {/* Dose-Response Config */}
            {rd?.data_type === "dose_response" && (
              <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
                <p className="text-xs font-medium">Dose-Response Configuration</p>
                <div className="grid grid-cols-3 gap-3">
                  <div className="grid gap-1">
                    <Label className="text-xs">Curve Type</Label>
                    <Controller
                      control={form.control}
                      name={`readouts.${index}.dr_curve_type`}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(CURVE_TYPE_LABELS).map(([v, l]) => (
                              <SelectItem key={v} value={v}>
                                {l}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">X-Axis Readout</Label>
                    <Controller
                      control={form.control}
                      name={`readouts.${index}.dr_x_readout`}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value={WELL_CONC_X}>(use well concentration)</SelectItem>
                            {numericOthers.map((other) => (
                              <SelectItem key={other.name} value={other.name.trim()}>
                                {other.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Y-Axis Readout</Label>
                    <Controller
                      control={form.control}
                      name={`readouts.${index}.dr_y_readout`}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select..." />
                          </SelectTrigger>
                          <SelectContent>
                            {numericOthers.map((other) => (
                              <SelectItem key={other.name} value={other.name.trim()}>
                                {other.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>
                </div>

                {/* Intercepts — chemist declares which intercepts the fit emits (EC50, EC90,
                    IC10, …). Empty list = single implicit 50% intercept seeded from the Curve
                    Type. Every downstream surface emits one column per row. */}
                <Controller
                  control={form.control}
                  name={`readouts.${index}.dr_intercepts`}
                  render={({ field: f }) => (
                    <div className="grid gap-2 rounded-md border bg-background p-3">
                      <div className="flex items-baseline justify-between">
                        <Label className="text-xs font-medium">Intercepts</Label>
                        <span className="text-[11px] text-muted-foreground">
                          One row per intercept (EC50, EC90, IC10, …) — all derived from the same
                          Hill fit
                        </span>
                      </div>
                      <InterceptsEditor
                        value={f.value as InterceptSpec[]}
                        onChange={f.onChange}
                        curveType={
                          (form.watch(`readouts.${index}.dr_curve_type`) as CurveType) ?? "ic50"
                        }
                      />
                    </div>
                  )}
                />

                <div className="grid grid-cols-3 gap-3">
                  <div className="grid gap-1">
                    <Label className="text-xs">Hill Slope</Label>
                    <Controller
                      control={form.control}
                      name={`readouts.${index}.dr_hill_constraint`}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(HILL_SLOPE_CONSTRAINT_LABELS).map(([v, l]) => (
                              <SelectItem key={v} value={v}>
                                {l}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Normalization</Label>
                    <Controller
                      control={form.control}
                      name={`readouts.${index}.dr_normalization_scope`}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(NORMALIZATION_SCOPE_LABELS).map(([v, l]) => (
                              <SelectItem key={v} value={v}>
                                {l}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Activity Threshold (%)</Label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      placeholder="e.g., 30"
                      {...form.register(`readouts.${index}.dr_activity_threshold`)}
                    />
                  </div>
                </div>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
