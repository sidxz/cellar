"use client";

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  CURVE_TYPE_LABELS,
  HILL_SLOPE_CONSTRAINT_LABELS,
  NORMALIZATION_SCOPE_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  type CurveType,
  type HillSlopeConstraint,
  type NormalizationScope,
  type ReadoutAggregation,
  type ReadoutDataType,
  type ReadoutDefinition,
} from "../types";
import { NormalizationCheckboxGroup } from "./readout-normalization-checkboxes";

interface ReadoutDefinitionViewerDialogProps {
  readoutDef: ReadoutDefinition | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Read-only modal showing the full configuration for a readout definition,
 * styled like CDD's "View Readout Definition" dialog. All inputs are
 * `disabled` (greyed but visually preserved), so the viewer feels like an
 * Edit dialog the user just isn't editing — preserving the spatial mental
 * model when comparing to the writable form.
 */
export function ReadoutDefinitionViewerDialog({
  readoutDef,
  open,
  onOpenChange,
}: ReadoutDefinitionViewerDialogProps) {
  if (!readoutDef) return null;
  const cfg = readoutDef.dose_response_config;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(95vw,1000px)] max-w-[1000px] sm:max-w-[1000px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>View Readout Definition: {readoutDef.name}</DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* ── Basic ────────────────────────────────────────────── */}
          <Section title="Basic">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name" value={readoutDef.name} />
              <Field
                label="Data Type"
                value={
                  READOUT_DATA_TYPE_LABELS[
                    readoutDef.data_type as ReadoutDataType
                  ] ?? readoutDef.data_type
                }
              />
              <Field label="Unit" value={readoutDef.unit ?? ""} />
              <Field
                label="Aggregation"
                value={
                  READOUT_AGGREGATION_LABELS[
                    readoutDef.aggregation as ReadoutAggregation
                  ] ?? readoutDef.aggregation
                }
              />
            </div>
            <div className="mt-3 grid gap-1">
              <Label className="text-xs">Normalization</Label>
              <div className="rounded-md border bg-background p-2">
                <NormalizationCheckboxGroup
                  value={
                    readoutDef.normalizations ??
                    (readoutDef.normalization && readoutDef.normalization !== "none"
                      ? [readoutDef.normalization]
                      : [])
                  }
                  disabled
                />
              </div>
            </div>
            {readoutDef.is_calculated && readoutDef.calculation_formula && (
              <div className="mt-3">
                <Field
                  label="Calculation Formula"
                  value={readoutDef.calculation_formula}
                  monospace
                />
              </div>
            )}
            {readoutDef.pick_list_values &&
              readoutDef.pick_list_values.length > 0 && (
                <div className="mt-3">
                  <Field
                    label="Pick List Values"
                    value={readoutDef.pick_list_values.join(", ")}
                  />
                </div>
              )}
          </Section>

          {/* ── Dose-Response sections (only when configured) ─────── */}
          {cfg && (
            <>
              <Section title="Axes (dose-response)">
                <div className="grid grid-cols-2 gap-3">
                  <Field
                    label="Curve Type"
                    value={
                      CURVE_TYPE_LABELS[cfg.curve_type as CurveType] ??
                      cfg.curve_type
                    }
                  />
                  <Field
                    label="X readout"
                    value={cfg.x_readout_name ?? "(use well concentration)"}
                  />
                  <Field label="Y readout" value={cfg.y_readout_name} />
                  <Field
                    label="Normalization Scope"
                    value={
                      NORMALIZATION_SCOPE_LABELS[
                        cfg.normalization_scope as NormalizationScope
                      ] ?? cfg.normalization_scope
                    }
                  />
                </div>
              </Section>

              <Section title="Fit Parameters">
                <div className="space-y-3">
                  <ParamRow
                    label="Top (upper plateau)"
                    lock={cfg.top_constraint}
                    min={cfg.top_constraint_min}
                    max={cfg.top_constraint_max}
                  />
                  <ParamRow
                    label="Bottom (lower plateau)"
                    lock={cfg.bottom_constraint}
                    min={cfg.bottom_constraint_min}
                    max={cfg.bottom_constraint_max}
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <Field
                      label="Hill Slope"
                      value={
                        HILL_SLOPE_CONSTRAINT_LABELS[
                          cfg.hill_slope_constraint as HillSlopeConstraint
                        ] ?? cfg.hill_slope_constraint
                      }
                    />
                    {(cfg.hill_slope_min != null ||
                      cfg.hill_slope_max != null) && (
                      <RangeField
                        label="Hill custom range"
                        min={cfg.hill_slope_min}
                        max={cfg.hill_slope_max}
                      />
                    )}
                  </div>
                  {cfg.activity_threshold != null && (
                    <Field
                      label="Activity Threshold (%)"
                      value={String(cfg.activity_threshold)}
                    />
                  )}
                </div>
              </Section>

              <Section title="Outlier Detection">
                <div className="grid grid-cols-2 gap-3">
                  <Field
                    label="Auto-remove outliers"
                    value={cfg.outlier_sigma != null ? "Enabled" : "Disabled"}
                  />
                  {cfg.outlier_sigma != null && (
                    <Field
                      label="Threshold (× SD)"
                      value={String(cfg.outlier_sigma)}
                    />
                  )}
                </div>
              </Section>

              <Section title="Classification thresholds">
                <p className="text-xs text-muted-foreground mb-3 leading-tight">
                  Defaults are calibrated for % readouts. Raw-signal assays
                  may have these overridden per-protocol.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <ClassificationThresholdField
                    label="Inactive cutoff (max response)"
                    value={cfg.inactive_threshold}
                    defaultValue={30}
                  />
                  <ClassificationThresholdField
                    label="Full curve · min R²"
                    value={cfg.full_r2_min}
                    defaultValue={0.8}
                  />
                  <ClassificationThresholdField
                    label="Full curve · min Top"
                    value={cfg.full_top_min}
                    defaultValue={80}
                  />
                  <ClassificationThresholdField
                    label="Full curve · max Bottom"
                    value={cfg.full_bottom_max}
                    defaultValue={20}
                  />
                  <ClassificationThresholdField
                    label="Partial curve · min R²"
                    value={cfg.partial_r2_min}
                    defaultValue={0.6}
                  />
                </div>
              </Section>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
        {title}
      </h3>
      <div className="rounded-lg border bg-muted/20 p-3">{children}</div>
    </div>
  );
}

function Field({
  label,
  value,
  monospace,
}: {
  label: string;
  value: string;
  monospace?: boolean;
}) {
  return (
    <div className="grid gap-1">
      <Label className="text-xs">{label}</Label>
      <Input
        readOnly
        aria-readonly="true"
        value={value}
        className={
          "bg-muted cursor-not-allowed " + (monospace ? "font-mono text-xs" : "")
        }
      />
    </div>
  );
}

function ParamRow({
  label,
  lock,
  min,
  max,
}: {
  label: string;
  lock: number | null;
  min: number | null;
  max: number | null;
}) {
  const mode: "free" | "range" | "lock" =
    lock != null ? "lock" : min != null || max != null ? "range" : "free";
  return (
    <div className="rounded-md border bg-background p-2 space-y-1.5">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-medium">{label}</Label>
        <span className="inline-flex rounded-md border text-xs">
          {(["free", "range", "lock"] as const).map((m) => (
            <span
              key={m}
              className={
                "px-2.5 py-1 capitalize first:rounded-l-md last:rounded-r-md " +
                (m === mode
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground")
              }
            >
              {m}
            </span>
          ))}
        </span>
      </div>
      {mode === "lock" && (
        <Input
          readOnly
          aria-readonly="true"
          value={String(lock)}
          className="max-w-xs bg-muted cursor-not-allowed"
        />
      )}
      {mode === "range" && (
        <div className="flex items-center gap-2 max-w-md">
          <span className="text-xs text-muted-foreground">from</span>
          <Input
            readOnly
            aria-readonly="true"
            value={min != null ? String(min) : "—"}
            className="bg-muted cursor-not-allowed"
          />
          <span className="text-xs text-muted-foreground">to</span>
          <Input
            readOnly
            aria-readonly="true"
            value={max != null ? String(max) : "—"}
            className="bg-muted cursor-not-allowed"
          />
        </div>
      )}
      {mode === "free" && (
        <p className="text-xs text-muted-foreground">
          Optimizer chooses freely from the data.
        </p>
      )}
    </div>
  );
}

/** Read-only numeric field that falls back to a backend default when the
 *  protocol hasn't overridden it. The label gets a "(default)" suffix so
 *  the analyst can tell at a glance whether they configured this or are
 *  inheriting the calibration. */
function ClassificationThresholdField({
  label,
  value,
  defaultValue,
}: {
  label: string;
  value: number | undefined | null;
  defaultValue: number;
}) {
  const isDefault = value == null;
  const displayed = isDefault ? defaultValue : value;
  return (
    <div className="grid gap-1">
      <Label className="text-xs">
        {label}
        {isDefault && (
          <span className="ml-1 font-normal text-muted-foreground">
            (default)
          </span>
        )}
      </Label>
      <Input
        readOnly
        aria-readonly="true"
        value={String(displayed)}
        className="bg-muted cursor-not-allowed"
      />
    </div>
  );
}

function RangeField({
  label,
  min,
  max,
}: {
  label: string;
  min: number | null;
  max: number | null;
}) {
  return (
    <div className="grid gap-1">
      <Label className="text-xs">{label}</Label>
      <div className="flex items-center gap-2">
        <Input
          readOnly
          aria-readonly="true"
          value={min != null ? String(min) : "—"}
          className="bg-muted cursor-not-allowed"
        />
        <span className="text-xs text-muted-foreground">to</span>
        <Input
          readOnly
          aria-readonly="true"
          value={max != null ? String(max) : "—"}
          className="bg-muted cursor-not-allowed"
        />
      </div>
    </div>
  );
}
