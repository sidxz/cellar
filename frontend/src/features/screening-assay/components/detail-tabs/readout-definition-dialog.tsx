"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Textarea } from "@/shared/components/ui/textarea";
import {
  PERCENT_FIT_RANGES,
  VISIBLE_READOUT_DATA_TYPES,
  WELL_CONC_X,
  isReservedReadoutName,
} from "../../lib/readout-constants";
import {
  CURVE_TYPE_LABELS,
  type CurveType,
  HILL_SLOPE_CONSTRAINT_LABELS,
  type HillSlopeConstraint,
  NORMALIZATION_SCOPE_LABELS,
  type NormalizationScope,
  type Protocol,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  type ReadoutDataType,
} from "../../types";
import { FormulaInput } from "../formula-input";
import { InterceptsEditor } from "../intercepts-editor";
import { PickListEditor } from "../pick-list-editor";
import { NormalizationCheckboxGroup } from "../readout-normalization-checkboxes";
import {
  PARAM_MODES,
  type ParamMode,
  type useReadoutDefinitionForm,
} from "./use-readout-definition-form";

// ---------------------------------------------------------------------------
// ParamModeToggle — tiny segmented control reused by Top and Bottom blocks.
// ---------------------------------------------------------------------------

function ParamModeToggle({
  mode,
  onChange,
  idPrefix,
}: {
  mode: ParamMode;
  onChange: (m: ParamMode) => void;
  idPrefix: string;
}) {
  return (
    <div className="inline-flex rounded-md border" role="radiogroup">
      {PARAM_MODES.map((opt) => (
        <button
          key={`${idPrefix}-${opt}`}
          type="button"
          role="radio"
          aria-checked={mode === opt}
          onClick={() => onChange(opt)}
          className={`px-2.5 py-1 text-xs capitalize first:rounded-l-md last:rounded-r-md ${
            mode === opt ? "bg-primary text-primary-foreground" : "bg-background hover:bg-muted"
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared dose-response fields renderer
// ---------------------------------------------------------------------------

interface DoseResponseFieldsProps {
  form: ReturnType<typeof useReadoutDefinitionForm>;
  protocol: Protocol;
  excludeId: string | null;
}

function DoseResponseFields({ form, protocol, excludeId }: DoseResponseFieldsProps) {
  const {
    rdDataType,
    drCurveType,
    setDrCurveType,
    drXReadout,
    setDrXReadout,
    drYReadout,
    drHillConstraint,
    setDrHillConstraint,
    drNormalizationScope,
    setDrNormalizationScope,
    drActivityThreshold,
    setDrActivityThreshold,
    drTopMode,
    setDrTopMode,
    drTopConstraint,
    setDrTopConstraint,
    drTopMin,
    setDrTopMin,
    drTopMax,
    setDrTopMax,
    drBottomMode,
    setDrBottomMode,
    drBottomConstraint,
    setDrBottomConstraint,
    drBottomMin,
    setDrBottomMin,
    drBottomMax,
    setDrBottomMax,
    drHillCustomRange,
    setDrHillCustomRange,
    drHillMin,
    setDrHillMin,
    drHillMax,
    setDrHillMax,
    drOutlierEnabled,
    setDrOutlierEnabled,
    drOutlierSigma,
    setDrOutlierSigma,
    drInactiveThreshold,
    setDrInactiveThreshold,
    drFullR2Min,
    setDrFullR2Min,
    drFullTopMin,
    setDrFullTopMin,
    drFullBottomMax,
    setDrFullBottomMax,
    drPartialR2Min,
    setDrPartialR2Min,
    drIntercepts,
    setDrIntercepts,
    handleDrYReadoutChange,
    applySuggestedRanges,
    validation,
  } = form;

  if (rdDataType !== "dose_response") return null;

  /** Numeric readouts available as X/Y axis candidates, optionally excluding one. */
  const candidates = protocol.readout_definitions
    .filter((rd) => rd.data_type === "numeric" && rd.id !== excludeId)
    .map((rd) => rd.name);

  const xIsAdvanced = drXReadout !== WELL_CONC_X;

  // Determine if there are suggested ranges for this Y readout for the banner
  const suggested = (() => {
    const y = protocol.readout_definitions.find((r) => r.name === drYReadout);
    if (!y) return null;
    const primary = y.normalizations?.find((n) => n !== "none") ?? "none";
    if (
      primary === "percent_inhibition" ||
      primary === "percent_activation" ||
      primary === "percent_control"
    ) {
      return PERCENT_FIT_RANGES;
    }
    return null;
  })();

  const {
    drTopRangeError,
    drBottomRangeError,
    drTopLockError,
    drBottomLockError,
    drHillRangeError,
    drInactiveThresholdError,
    drFullR2MinError,
    drPartialR2MinError,
    drFullTopMinError,
    drFullBottomMaxError,
    drFullPlateauOrderError,
  } = validation;

  return (
    <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
      <p className="text-xs font-medium">Dose-Response Configuration</p>
      {/* Curve Type + Y on the always-visible row. X axis defaults to
          well.dose (the experimental setpoint, stored on every well);
          chemists almost never need to change it. The rare case
          (log-transformed X computed by a calculated readout) lives
          behind the Advanced disclosure below. */}
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1">
          <Label className="text-xs">Curve Type</Label>
          <Select value={drCurveType} onValueChange={(v) => setDrCurveType(v as CurveType)}>
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
        </div>
        <div className="grid gap-1">
          <Label className="text-xs">Y-Axis Readout</Label>
          <Select value={drYReadout} onValueChange={(v) => handleDrYReadoutChange(v, protocol)}>
            <SelectTrigger>
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {candidates.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <Collapsible defaultOpen={xIsAdvanced}>
        <CollapsibleTrigger className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
          <span aria-hidden>▸</span>
          Advanced — X axis source
          {xIsAdvanced ? null : (
            <span className="ml-1 italic opacity-70">(default: well concentration)</span>
          )}
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2">
          <div className="grid gap-1 max-w-sm">
            <Label className="text-xs">X-Axis Readout</Label>
            <Select value={drXReadout} onValueChange={setDrXReadout}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={WELL_CONC_X}>(use well concentration — default)</SelectItem>
                {candidates.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Pick a different readout only when the X axis is a derivation (e.g. log-concentration
              computed by a calculated readout). 99% of dose-response fits use the well&apos;s
              recorded concentration.
            </p>
          </div>
        </CollapsibleContent>
      </Collapsible>
      <div className="grid grid-cols-3 gap-3">
        <div className="grid gap-1">
          <Label className="text-xs">Hill Slope</Label>
          <Select
            value={drHillConstraint}
            onValueChange={(v) => setDrHillConstraint(v as HillSlopeConstraint)}
          >
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
        </div>
        <div className="grid gap-1">
          <Label className="text-xs">Normalization Scope</Label>
          <Select
            value={drNormalizationScope}
            onValueChange={(v) => setDrNormalizationScope(v as NormalizationScope)}
          >
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
        </div>
        <div className="grid gap-1">
          <Label className="text-xs">Activity Threshold (%)</Label>
          <Input
            type="number"
            min="0"
            max="100"
            placeholder="e.g., 30"
            value={drActivityThreshold}
            onChange={(e) => setDrActivityThreshold(e.target.value)}
          />
        </div>
      </div>
      {/* Top fit-parameter controls (Free / Range / Lock). */}
      <div className="grid gap-2 rounded-md border bg-background p-3">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">Top (upper plateau)</Label>
          <ParamModeToggle mode={drTopMode} onChange={setDrTopMode} idPrefix="top" />
        </div>
        {drTopMode === "lock" && (
          <>
            <Input
              type="number"
              placeholder="exact value, e.g. 100"
              value={drTopConstraint}
              onChange={(e) => setDrTopConstraint(e.target.value)}
              className="max-w-xs"
            />
            {drTopLockError && <p className="text-xs text-destructive">Enter a numeric value.</p>}
          </>
        )}
        {drTopMode === "range" && (
          <>
            <div className="flex items-center gap-2 max-w-md">
              <span className="text-xs text-muted-foreground">from</span>
              <Input
                type="number"
                placeholder="85"
                value={drTopMin}
                onChange={(e) => setDrTopMin(e.target.value)}
              />
              <span className="text-xs text-muted-foreground">to</span>
              <Input
                type="number"
                placeholder="110"
                value={drTopMax}
                onChange={(e) => setDrTopMax(e.target.value)}
              />
            </div>
            {drTopRangeError && (
              <p className="text-xs text-destructive">Enter both min and max with min &lt; max.</p>
            )}
          </>
        )}
        {drTopMode === "free" && (
          <p className="text-xs text-muted-foreground">
            Optimizer chooses Top freely from the data.
          </p>
        )}
      </div>

      {/* Bottom fit-parameter controls. */}
      <div className="grid gap-2 rounded-md border bg-background p-3">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">Bottom (lower plateau)</Label>
          <ParamModeToggle mode={drBottomMode} onChange={setDrBottomMode} idPrefix="bottom" />
        </div>
        {drBottomMode === "lock" && (
          <>
            <Input
              type="number"
              placeholder="exact value, e.g. 0"
              value={drBottomConstraint}
              onChange={(e) => setDrBottomConstraint(e.target.value)}
              className="max-w-xs"
            />
            {drBottomLockError && (
              <p className="text-xs text-destructive">Enter a numeric value.</p>
            )}
          </>
        )}
        {drBottomMode === "range" && (
          <>
            <div className="flex items-center gap-2 max-w-md">
              <span className="text-xs text-muted-foreground">from</span>
              <Input
                type="number"
                placeholder="-10"
                value={drBottomMin}
                onChange={(e) => setDrBottomMin(e.target.value)}
              />
              <span className="text-xs text-muted-foreground">to</span>
              <Input
                type="number"
                placeholder="10"
                value={drBottomMax}
                onChange={(e) => setDrBottomMax(e.target.value)}
              />
            </div>
            {drBottomRangeError && (
              <p className="text-xs text-destructive">Enter both min and max with min &lt; max.</p>
            )}
          </>
        )}
        {drBottomMode === "free" && (
          <p className="text-xs text-muted-foreground">
            Optimizer chooses Bottom freely from the data.
          </p>
        )}
      </div>

      {/* Hill: explicit range overrides the enum's implicit bounds. */}
      <div className="grid gap-2 rounded-md border bg-background p-3">
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={drHillCustomRange}
            onChange={(e) => setDrHillCustomRange(e.target.checked)}
            className="h-4 w-4"
          />
          Custom Hill slope range (overrides the bounds set above)
        </label>
        {drHillCustomRange && (
          <>
            <div className="flex items-center gap-2 max-w-md">
              <span className="text-xs text-muted-foreground">from</span>
              <Input
                type="number"
                step="0.1"
                placeholder="0.9"
                value={drHillMin}
                onChange={(e) => setDrHillMin(e.target.value)}
              />
              <span className="text-xs text-muted-foreground">to</span>
              <Input
                type="number"
                step="0.1"
                placeholder="1.1"
                value={drHillMax}
                onChange={(e) => setDrHillMax(e.target.value)}
              />
            </div>
            {drHillRangeError && (
              <p className="text-xs text-destructive">Enter both min and max with min &lt; max.</p>
            )}
          </>
        )}
      </div>

      {/* Auto-outlier removal — protocol-level threshold. */}
      <div className="grid gap-2 rounded-md border bg-background p-3">
        <label className="flex items-center gap-2 text-xs font-medium">
          <input
            type="checkbox"
            checked={drOutlierEnabled}
            onChange={(e) => setDrOutlierEnabled(e.target.checked)}
            className="h-4 w-4"
          />
          Auto-remove outliers during fitting
        </label>
        {drOutlierEnabled && (
          <div className="flex items-center gap-2 max-w-md">
            <Label className="text-xs text-muted-foreground">Threshold</Label>
            <Input
              type="number"
              step="0.5"
              min="0.5"
              max="10"
              value={drOutlierSigma}
              onChange={(e) => setDrOutlierSigma(e.target.value)}
              className="max-w-[6rem]"
            />
            <span className="text-xs text-muted-foreground">× SD of residuals (default: 3)</span>
          </div>
        )}
        {!drOutlierEnabled && (
          <p className="text-xs text-muted-foreground">
            Disabled — fitter will not auto-flag points; manual exclusion still works.
          </p>
        )}
      </div>

      {/* Suggested-ranges banner. */}
      {!suggested ? (
        <p className="text-xs text-muted-foreground leading-tight">
          Lock and Range are mutually exclusive. Leave both at Free for raw-signal readouts; use
          Range for percent-normalized readouts.
        </p>
      ) : (
        <div className="flex items-start justify-between gap-3 rounded-md border border-dashed bg-muted/40 p-2">
          <p className="text-xs text-muted-foreground leading-tight">
            Suggested for this readout: Top ∈ [{suggested.topMin}, {suggested.topMax}], Bottom ∈ [
            {suggested.bottomMin}, {suggested.bottomMax}], Hill ∈ [{suggested.hillMin},{" "}
            {suggested.hillMax}].
          </p>
          <button
            type="button"
            title="Apply suggested ranges to Top, Bottom, and Hill"
            className="shrink-0 text-xs text-primary underline-offset-2 hover:underline"
            onClick={() => applySuggestedRanges(protocol)}
          >
            Use suggested
          </button>
        </div>
      )}

      {/* Classification thresholds — collapsed by default. Defaults match
          the backend (30 / 0.8 / 80 / 20 / 0.6) calibrated for % readouts.
          Override per-protocol for raw-signal assays. Intentionally NOT
          auto-touched by the suggestedRangesForY flow — these are a
          one-time per-protocol calibration, not a per-Y-readout suggestion. */}
      <details className="rounded-md border bg-background">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium select-none">
          Classification thresholds
          <span className="ml-2 font-normal text-muted-foreground">
            (advanced — defaults work for % readouts)
          </span>
        </summary>
        <div className="space-y-3 px-3 pb-3 pt-1">
          <p className="text-xs text-muted-foreground leading-tight">
            Defaults are calibrated for % readouts. Override for raw-signal assays (fluorescence,
            luminescence, HTRF, etc.).
          </p>
          <div className="grid gap-1">
            <Label className="text-xs">Inactive cutoff</Label>
            <div className="flex items-center gap-2 max-w-md">
              <Input
                type="number"
                placeholder="30"
                value={drInactiveThreshold}
                onChange={(e) => setDrInactiveThreshold(e.target.value)}
              />
              <span className="text-xs text-muted-foreground whitespace-nowrap">max response</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Compounds with max response below this are flagged INACTIVE without fitting.
            </p>
            {drInactiveThresholdError && (
              <p className="text-xs text-destructive">
                Enter a numeric value or leave blank for default (30).
              </p>
            )}
          </div>
          <div className="grid gap-1">
            <Label className="text-xs">Full curve · min R²</Label>
            <Input
              type="number"
              step="0.01"
              min="0"
              max="1"
              placeholder="0.8"
              value={drFullR2Min}
              onChange={(e) => setDrFullR2Min(e.target.value)}
              className="max-w-[8rem]"
            />
            <p className="text-[11px] text-muted-foreground">
              R² required to qualify as a FULL curve.
            </p>
            {drFullR2MinError && (
              <p className="text-xs text-destructive">
                Enter a value in (0, 1] or leave blank for default (0.8).
              </p>
            )}
          </div>
          <div className="grid gap-1">
            <Label className="text-xs">Full curve · min Top</Label>
            <Input
              type="number"
              placeholder="80"
              value={drFullTopMin}
              onChange={(e) => setDrFullTopMin(e.target.value)}
              className="max-w-[8rem]"
            />
            <p className="text-[11px] text-muted-foreground">
              Fitted top plateau must reach this for FULL classification.
            </p>
            {drFullTopMinError && (
              <p className="text-xs text-destructive">
                Enter a numeric value or leave blank for default (80).
              </p>
            )}
          </div>
          <div className="grid gap-1">
            <Label className="text-xs">Full curve · max Bottom</Label>
            <Input
              type="number"
              placeholder="20"
              value={drFullBottomMax}
              onChange={(e) => setDrFullBottomMax(e.target.value)}
              className="max-w-[8rem]"
            />
            <p className="text-[11px] text-muted-foreground">
              Fitted bottom plateau must be below this for FULL classification.
            </p>
            {drFullBottomMaxError && (
              <p className="text-xs text-destructive">
                Enter a numeric value or leave blank for default (20).
              </p>
            )}
          </div>
          {drFullPlateauOrderError && (
            <p className="text-xs text-destructive">
              Full curve · min Top must be greater than Full curve · max Bottom.
            </p>
          )}
          <div className="grid gap-1">
            <Label className="text-xs">Partial curve · min R²</Label>
            <Input
              type="number"
              step="0.01"
              min="0"
              max="1"
              placeholder="0.6"
              value={drPartialR2Min}
              onChange={(e) => setDrPartialR2Min(e.target.value)}
              className="max-w-[8rem]"
            />
            <p className="text-[11px] text-muted-foreground">
              R² required to qualify as a PARTIAL curve. Below this, classified INACTIVE.
            </p>
            {drPartialR2MinError && (
              <p className="text-xs text-destructive">
                Enter a value in (0, 1] or leave blank for default (0.6).
              </p>
            )}
          </div>
        </div>
      </details>

      <details className="rounded-md border bg-background/40 p-2">
        <summary className="cursor-pointer text-xs font-medium select-none">
          Data Calculations
        </summary>
        <div className="mt-3 space-y-2">
          <p className="text-[11px] text-muted-foreground">
            Each row is one intercept derived from the same Hill fit (e.g. IC50, IC90). Empty list
            defaults to a single 50% intercept of the curve type.
          </p>
          <InterceptsEditor
            value={drIntercepts}
            onChange={setDrIntercepts}
            curveType={drCurveType}
          />
        </div>
      </details>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ReadoutDefinitionDialog — handles both add and edit modes
// ---------------------------------------------------------------------------

export interface ReadoutDefinitionDialogProps {
  mode: "add" | "edit";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  protocol: Protocol;
  protocolId: string;
  editingReadoutId: string | null;
  isDraft: boolean;
  protocolNames: string[];
  form: ReturnType<typeof useReadoutDefinitionForm>;
  isSaving: boolean;
  onSave: () => void;
  onCancel: () => void;
}

export function ReadoutDefinitionDialog({
  mode,
  open,
  onOpenChange,
  protocol,
  editingReadoutId,
  isDraft,
  protocolNames,
  form,
  isSaving,
  onSave,
  onCancel,
}: ReadoutDefinitionDialogProps) {
  const {
    rdName,
    setRdName,
    rdDescription,
    setRdDescription,
    rdIsCalculated,
    setRdIsCalculated,
    rdCalculationFormula,
    setRdCalculationFormula,
    rdDataType,
    setRdDataType,
    rdUnit,
    setRdUnit,
    rdAggregation,
    setRdAggregation,
    rdNormalizations,
    setRdNormalizations,
    rdPickListValues,
    setRdPickListValues,
    validation,
  } = form;

  const { drFormInvalid } = validation;
  const { drYReadout } = form;

  const isAdd = mode === "add";

  const saveDisabled =
    !rdName.trim() ||
    isReservedReadoutName(rdName) ||
    isSaving ||
    (rdDataType === "dose_response" && !drYReadout) ||
    (rdDataType === "pick_list" && rdPickListValues.filter((v) => v.label.trim()).length === 0) ||
    (rdDataType === "numeric" && rdIsCalculated && !rdCalculationFormula.trim()) ||
    drFormInvalid;

  const doseResponseBlock = (
    <DoseResponseFields
      form={form}
      protocol={protocol}
      excludeId={isAdd ? null : editingReadoutId}
    />
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(95vw,1000px)] max-w-[1000px] sm:max-w-[1000px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isAdd ? "Add Readout Definition" : "Edit Readout Definition"}</DialogTitle>
          <DialogDescription>
            {isAdd
              ? "Define a new measured value for this protocol."
              : isDraft
                ? "Update fields on this readout."
                : "Cosmetic fields (unit) can be edited on a published protocol. Renaming, data-type changes, and other structural edits require a new version — they would invalidate prior runs."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Name</Label>
            <Input
              value={rdName}
              onChange={(e) => setRdName(e.target.value)}
              placeholder={isAdd ? "e.g. % Inhibition" : undefined}
              disabled={!isAdd && !isDraft}
            />
            {isReservedReadoutName(rdName) && (
              <p className="text-xs text-destructive">
                &lsquo;{rdName.trim()}&rsquo; is a reserved well-metadata name and cannot be used as
                a readout. The well&apos;s concentration, batch, and compound are tracked on the
                well itself, not as readouts.
              </p>
            )}
          </div>
          <div className="space-y-1">
            <Label>
              Description <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Textarea
              value={rdDescription}
              onChange={(e) => setRdDescription(e.target.value)}
              placeholder={
                isAdd
                  ? "What this readout captures, e.g. 'Compound activity vs DMSO baseline, normalized per plate.'"
                  : "What this readout captures."
              }
              rows={2}
            />
          </div>
          <div className="space-y-1">
            <Label>Data Type</Label>
            <Select value={rdDataType} onValueChange={setRdDataType} disabled={!isAdd && !isDraft}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VISIBLE_READOUT_DATA_TYPES.map((val) => (
                  <SelectItem key={val} value={val}>
                    {READOUT_DATA_TYPE_LABELS[val as ReadoutDataType] ?? val}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {/* Pick-list specific: Allowed Values directly after Data
              Type. Numeric measurement attributes (Unit, Aggregation,
              Normalization) are hidden — pick lists are categorical
              and these fields don't apply. */}
          {rdDataType === "pick_list" ? (
            <div className="space-y-1">
              <Label>Allowed Values</Label>
              <PickListEditor
                value={rdPickListValues}
                onChange={setRdPickListValues}
                disabled={!isAdd && !isDraft}
              />
            </div>
          ) : (
            <>
              <div className="space-y-1">
                <Label>Unit</Label>
                <Input
                  value={rdUnit}
                  onChange={(e) => setRdUnit(e.target.value)}
                  placeholder={isAdd ? "e.g. nM, %, µM" : undefined}
                />
              </div>
              {/* Calculated toggle — only meaningful for numeric (the
                  formula evaluator returns a float). When on, hide
                  Aggregation + Normalization: the calc engine ignores
                  both for is_calculated readouts. */}
              {rdDataType === "numeric" && (
                <div className="flex items-center gap-3 pt-1">
                  <Switch
                    checked={rdIsCalculated}
                    onCheckedChange={(v) => setRdIsCalculated(v === true)}
                    disabled={!isAdd && !isDraft}
                  />
                  <Label className="text-sm font-normal">
                    Calculated{" "}
                    <span className="text-muted-foreground">
                      — value derived from a formula over other readouts
                    </span>
                  </Label>
                </div>
              )}
              {rdIsCalculated && rdDataType === "numeric" && (
                <div className="space-y-1">
                  <Label>Formula</Label>
                  <FormulaInput
                    value={rdCalculationFormula}
                    onChange={setRdCalculationFormula}
                    availableReadoutNames={
                      isAdd
                        ? protocol.readout_definitions.map((rd) => rd.name)
                        : protocol.readout_definitions
                            .filter((rd) => rd.id !== editingReadoutId)
                            .map((rd) => rd.name)
                    }
                    protocolNames={protocolNames}
                    disabled={!isAdd && !isDraft}
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Use other readout names as variables. Type <code>@</code> for cross-protocol.
                  </p>
                </div>
              )}
              {!rdIsCalculated && (
                <>
                  <div className="space-y-1">
                    <Label>Aggregation</Label>
                    <Select
                      value={rdAggregation}
                      onValueChange={setRdAggregation}
                      disabled={!isAdd && !isDraft}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(READOUT_AGGREGATION_LABELS).map(([val, label]) => (
                          <SelectItem key={val} value={val}>
                            {label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label>Normalization</Label>
                    <NormalizationCheckboxGroup
                      value={rdNormalizations}
                      onChange={setRdNormalizations}
                      disabled={!isAdd && !isDraft}
                    />
                  </div>
                </>
              )}
            </>
          )}
          {/* Dose-response fields are structural (curve type, axes,
              intercepts, ranges) — disabled on non-DRAFT. The fields
              inside DoseResponseFields don't currently take a disabled prop,
              so we wrap in a disabled-pointer-events shim instead. */}
          {!isAdd && !isDraft ? (
            <div className="pointer-events-none opacity-60">{doseResponseBlock}</div>
          ) : (
            doseResponseBlock
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button disabled={saveDisabled} onClick={onSave}>
            {isSaving ? (isAdd ? "Adding..." : "Saving...") : isAdd ? "Add" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
