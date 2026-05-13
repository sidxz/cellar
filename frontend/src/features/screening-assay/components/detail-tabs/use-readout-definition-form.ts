"use client";

import { showInfo } from "@/shared/lib/toast";
import { useState } from "react";
import { PERCENT_FIT_RANGES, WELL_CONC_X } from "../../lib/readout-constants";
import type {
  CurveType,
  HillSlopeConstraint,
  InterceptSpec,
  NormalizationScope,
  PickListValue,
  Protocol,
  ReadoutNormalization,
} from "../../types";

// ---------------------------------------------------------------------------
// Tri-state parameter mode for Top / Bottom curve-fit constraints.
// ---------------------------------------------------------------------------

export type ParamMode = "free" | "range" | "lock";
export const PARAM_MODES: ParamMode[] = ["free", "range", "lock"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function isFiniteValue(s: string): boolean {
  if (s.trim() === "") return false;
  const v = Number.parseFloat(s);
  return Number.isFinite(v);
}

export function isFiniteRange(minS: string, maxS: string): boolean {
  if (!isFiniteValue(minS) || !isFiniteValue(maxS)) return false;
  return Number.parseFloat(minS) < Number.parseFloat(maxS);
}

// ---------------------------------------------------------------------------
// useReadoutDefinitionForm
// ---------------------------------------------------------------------------

export interface ReadoutDefinitionFormReturn {
  // ---- basic readout fields ----
  rdName: string;
  setRdName: (v: string) => void;
  rdDescription: string;
  setRdDescription: (v: string) => void;
  rdIsCalculated: boolean;
  setRdIsCalculated: (v: boolean) => void;
  rdCalculationFormula: string;
  setRdCalculationFormula: (v: string) => void;
  rdDataType: string;
  setRdDataType: (v: string) => void;
  rdUnit: string;
  setRdUnit: (v: string) => void;
  rdAggregation: string;
  setRdAggregation: (v: string) => void;
  rdNormalizations: ReadoutNormalization[];
  setRdNormalizations: (v: ReadoutNormalization[]) => void;
  rdPickListValues: PickListValue[];
  setRdPickListValues: (v: PickListValue[]) => void;

  // ---- dose-response fields ----
  drCurveType: CurveType;
  setDrCurveType: (v: CurveType) => void;
  drXReadout: string;
  setDrXReadout: (v: string) => void;
  drYReadout: string;
  setDrYReadout: (v: string) => void;
  drYNormalization: ReadoutNormalization | null;
  setDrYNormalization: (v: ReadoutNormalization | null) => void;
  drHillConstraint: HillSlopeConstraint;
  setDrHillConstraint: (v: HillSlopeConstraint) => void;
  drNormalizationScope: NormalizationScope;
  setDrNormalizationScope: (v: NormalizationScope) => void;
  drActivityThreshold: string;
  setDrActivityThreshold: (v: string) => void;
  drTopMode: ParamMode;
  setDrTopMode: (v: ParamMode) => void;
  drTopConstraint: string;
  setDrTopConstraint: (v: string) => void;
  drTopMin: string;
  setDrTopMin: (v: string) => void;
  drTopMax: string;
  setDrTopMax: (v: string) => void;
  drBottomMode: ParamMode;
  setDrBottomMode: (v: ParamMode) => void;
  drBottomConstraint: string;
  setDrBottomConstraint: (v: string) => void;
  drBottomMin: string;
  setDrBottomMin: (v: string) => void;
  drBottomMax: string;
  setDrBottomMax: (v: string) => void;
  drHillCustomRange: boolean;
  setDrHillCustomRange: (v: boolean) => void;
  drHillMin: string;
  setDrHillMin: (v: string) => void;
  drHillMax: string;
  setDrHillMax: (v: string) => void;
  drOutlierEnabled: boolean;
  setDrOutlierEnabled: (v: boolean) => void;
  drOutlierSigma: string;
  setDrOutlierSigma: (v: string) => void;
  drInactiveThreshold: string;
  setDrInactiveThreshold: (v: string) => void;
  drFullR2Min: string;
  setDrFullR2Min: (v: string) => void;
  drFullTopMin: string;
  setDrFullTopMin: (v: string) => void;
  drFullBottomMax: string;
  setDrFullBottomMax: (v: string) => void;
  drPartialR2Min: string;
  setDrPartialR2Min: (v: string) => void;
  drIntercepts: InterceptSpec[];
  setDrIntercepts: (v: InterceptSpec[]) => void;

  // ---- actions ----
  openEditReadout: (rdId: string, protocol: Protocol) => void;
  closeEditReadout: () => void;
  resetDoseResponseFields: () => void;
  handleDrYReadoutChange: (newY: string, protocol: Protocol) => void;
  applySuggestedRanges: (protocol: Protocol) => void;

  // ---- derived / validation ----
  validation: {
    drTopRangeError: boolean;
    drBottomRangeError: boolean;
    drTopLockError: boolean;
    drBottomLockError: boolean;
    drHillRangeError: boolean;
    drInactiveThresholdError: boolean;
    drFullR2MinError: boolean;
    drPartialR2MinError: boolean;
    drFullTopMinError: boolean;
    drFullBottomMaxError: boolean;
    drFullPlateauOrderError: boolean;
    drFormInvalid: boolean;
  };

  // ---- form output ----
  buildDoseResponseConfig: () => Record<string, unknown> | null;
}

export function useReadoutDefinitionForm(): ReadoutDefinitionFormReturn {
  // ---- basic readout fields ----
  const [rdName, setRdName] = useState("");
  const [rdDescription, setRdDescription] = useState("");
  const [rdIsCalculated, setRdIsCalculated] = useState(false);
  const [rdCalculationFormula, setRdCalculationFormula] = useState("");
  const [rdDataType, setRdDataType] = useState("numeric");
  const [rdUnit, setRdUnit] = useState("");
  const [rdAggregation, setRdAggregation] = useState("none");
  const [rdNormalizations, setRdNormalizations] = useState<ReadoutNormalization[]>([]);
  const [rdPickListValues, setRdPickListValues] = useState<PickListValue[]>([]);

  // ---- dose-response fields ----
  // X-axis sentinel: when drXReadout === WELL_CONC_X, the curve fits against the
  // well's own concentration (the default and most common case). Mapped to
  // x_readout_name=null in the payload.
  const [drCurveType, setDrCurveType] = useState<CurveType>("ic50");
  const [drXReadout, setDrXReadout] = useState<string>(WELL_CONC_X);
  const [drYReadout, setDrYReadout] = useState("");
  // null = fit the raw layer (rows where is_computed=false). Otherwise the
  // chosen normalization formula must be in the Y readout's normalizations set
  // — the backend cross-validates and silently dropping this on round-trip
  // would degrade CDD-imported DR readouts to fitting the raw signal.
  const [drYNormalization, setDrYNormalization] = useState<ReadoutNormalization | null>(null);
  const [drHillConstraint, setDrHillConstraint] = useState<HillSlopeConstraint>("unconstrained");
  const [drNormalizationScope, setDrNormalizationScope] = useState<NormalizationScope>("per_plate");
  const [drActivityThreshold, setDrActivityThreshold] = useState("");
  // Top/Bottom now have a tri-state mode. Lock and Range are mutually
  // exclusive in the domain; the mode field is the UI's source of truth
  // and decides which of the *Constraint* / *Min* / *Max* fields ship.
  const [drTopMode, setDrTopMode] = useState<ParamMode>("free");
  const [drTopConstraint, setDrTopConstraint] = useState("");
  const [drTopMin, setDrTopMin] = useState("");
  const [drTopMax, setDrTopMax] = useState("");
  const [drBottomMode, setDrBottomMode] = useState<ParamMode>("free");
  const [drBottomConstraint, setDrBottomConstraint] = useState("");
  const [drBottomMin, setDrBottomMin] = useState("");
  const [drBottomMax, setDrBottomMax] = useState("");
  // Hill stays an enum + an optional explicit range that overrides the
  // implicit bounds (POSITIVE_ONLY etc.).
  const [drHillCustomRange, setDrHillCustomRange] = useState(false);
  const [drHillMin, setDrHillMin] = useState("");
  const [drHillMax, setDrHillMax] = useState("");
  // Auto-outlier removal: enabled (true) by default at 3σ. Off (false)
  // disables auto-detection — the fitter still respects manually excluded
  // points. The σ threshold is editable when enabled.
  const [drOutlierEnabled, setDrOutlierEnabled] = useState(true);
  const [drOutlierSigma, setDrOutlierSigma] = useState("3");
  // Classification thresholds (Phase C). Empty string → use backend default.
  // Defaults match the backend: 30 / 0.8 / 80 / 20 / 0.6, calibrated for
  // % readouts. Raw-signal assays must override per-protocol.
  const [drInactiveThreshold, setDrInactiveThreshold] = useState("");
  const [drFullR2Min, setDrFullR2Min] = useState("");
  const [drFullTopMin, setDrFullTopMin] = useState("");
  const [drFullBottomMax, setDrFullBottomMax] = useState("");
  const [drPartialR2Min, setDrPartialR2Min] = useState("");
  // Per-spec intercepts. Empty list = server-default (single 50% intercept
  // derived from curve_type).
  const [drIntercepts, setDrIntercepts] = useState<InterceptSpec[]>([]);

  // ---- helpers ----

  const resetDoseResponseFields = () => {
    setDrCurveType("ic50");
    setDrXReadout(WELL_CONC_X);
    setDrYReadout("");
    setDrYNormalization(null);
    setDrHillConstraint("unconstrained");
    setDrNormalizationScope("per_plate");
    setDrActivityThreshold("");
    setDrTopMode("free");
    setDrTopConstraint("");
    setDrTopMin("");
    setDrTopMax("");
    setDrBottomMode("free");
    setDrBottomConstraint("");
    setDrBottomMin("");
    setDrBottomMax("");
    setDrHillCustomRange(false);
    setDrHillMin("");
    setDrHillMax("");
    setDrOutlierEnabled(true);
    setDrOutlierSigma("3");
    setDrInactiveThreshold("");
    setDrFullR2Min("");
    setDrFullTopMin("");
    setDrFullBottomMax("");
    setDrPartialR2Min("");
    setDrIntercepts([]);
  };

  // Y readouts with bounded normalization (% Inhibition/Activation/Control)
  // get standard sigmoidal default ranges. Ranges (not hard locks) let the
  // optimizer pick a data-consistent plateau when the upper plateau isn't
  // observed in the dose range — the difference between IC50 = 39 µM
  // (lock at 85) and IC50 = 70 µM (range up to 110) on partial curves.
  const suggestedRangesForY = (
    yReadoutName: string,
    protocol: Protocol,
  ): typeof PERCENT_FIT_RANGES | null => {
    const y = protocol.readout_definitions.find((r) => r.name === yReadoutName);
    if (!y) return null;
    const primary = y.normalizations?.find((n) => n !== "none") ?? "none";
    switch (primary) {
      case "percent_inhibition":
      case "percent_activation":
      case "percent_control":
        return PERCENT_FIT_RANGES;
      default:
        return null;
    }
  };

  const openEditReadout = (rdId: string, protocol: Protocol) => {
    const rd = protocol.readout_definitions.find((r) => r.id === rdId);
    if (!rd) return;
    setRdName(rd.name);
    setRdDescription(rd.description ?? "");
    setRdDataType(rd.data_type);
    setRdUnit(rd.unit ?? "");
    setRdAggregation(rd.aggregation);
    setRdNormalizations(rd.normalizations ?? []);
    setRdPickListValues(rd.pick_list_values ?? []);
    setRdIsCalculated(rd.is_calculated);
    setRdCalculationFormula(rd.calculation_formula ?? "");
    if (rd.dose_response_config) {
      const cfg = rd.dose_response_config;
      setDrCurveType(cfg.curve_type);
      setDrXReadout(cfg.x_readout_name ?? WELL_CONC_X);
      setDrYReadout(cfg.y_readout_name);
      setDrYNormalization(cfg.y_normalization ?? null);
      setDrHillConstraint(cfg.hill_slope_constraint);
      setDrNormalizationScope(cfg.normalization_scope);
      setDrActivityThreshold(cfg.activity_threshold != null ? String(cfg.activity_threshold) : "");

      // Top: lock takes precedence; else range; else free.
      if (cfg.top_constraint != null) {
        setDrTopMode("lock");
        setDrTopConstraint(String(cfg.top_constraint));
        setDrTopMin("");
        setDrTopMax("");
      } else if (cfg.top_constraint_min != null || cfg.top_constraint_max != null) {
        setDrTopMode("range");
        setDrTopConstraint("");
        setDrTopMin(cfg.top_constraint_min != null ? String(cfg.top_constraint_min) : "");
        setDrTopMax(cfg.top_constraint_max != null ? String(cfg.top_constraint_max) : "");
      } else {
        setDrTopMode("free");
        setDrTopConstraint("");
        setDrTopMin("");
        setDrTopMax("");
      }

      if (cfg.bottom_constraint != null) {
        setDrBottomMode("lock");
        setDrBottomConstraint(String(cfg.bottom_constraint));
        setDrBottomMin("");
        setDrBottomMax("");
      } else if (cfg.bottom_constraint_min != null || cfg.bottom_constraint_max != null) {
        setDrBottomMode("range");
        setDrBottomConstraint("");
        setDrBottomMin(cfg.bottom_constraint_min != null ? String(cfg.bottom_constraint_min) : "");
        setDrBottomMax(cfg.bottom_constraint_max != null ? String(cfg.bottom_constraint_max) : "");
      } else {
        setDrBottomMode("free");
        setDrBottomConstraint("");
        setDrBottomMin("");
        setDrBottomMax("");
      }

      const hasHillRange = cfg.hill_slope_min != null || cfg.hill_slope_max != null;
      setDrHillCustomRange(hasHillRange);
      setDrHillMin(cfg.hill_slope_min != null ? String(cfg.hill_slope_min) : "");
      setDrHillMax(cfg.hill_slope_max != null ? String(cfg.hill_slope_max) : "");

      const sigma = cfg.outlier_sigma;
      setDrOutlierEnabled(sigma != null);
      setDrOutlierSigma(sigma != null ? String(sigma) : "3");

      // Classification thresholds — empty string = "inherit backend default".
      setDrInactiveThreshold(cfg.inactive_threshold != null ? String(cfg.inactive_threshold) : "");
      setDrFullR2Min(cfg.full_r2_min != null ? String(cfg.full_r2_min) : "");
      setDrFullTopMin(cfg.full_top_min != null ? String(cfg.full_top_min) : "");
      setDrFullBottomMax(cfg.full_bottom_max != null ? String(cfg.full_bottom_max) : "");
      setDrPartialR2Min(cfg.partial_r2_min != null ? String(cfg.partial_r2_min) : "");
      setDrIntercepts(cfg.intercepts ?? []);
    } else {
      resetDoseResponseFields();
    }
  };

  const closeEditReadout = () => {
    setRdName("");
    setRdDescription("");
    setRdDataType("numeric");
    setRdUnit("");
    setRdAggregation("none");
    setRdNormalizations([]);
    setRdPickListValues([]);
    setRdIsCalculated(false);
    setRdCalculationFormula("");
    resetDoseResponseFields();
  };

  /** Build the dose_response_config payload for add/update mutations.
   *  Encodes the tri-state mode for Top/Bottom into the lock vs range fields.
   */
  const buildDoseResponseConfig = (): Record<string, unknown> | null => {
    if (rdDataType !== "dose_response") return null;
    if (!drYReadout) return null;
    const parseOrNull = (s: string) => (s !== "" ? Number.parseFloat(s) : null);
    return {
      curve_type: drCurveType,
      x_readout_name: drXReadout === WELL_CONC_X ? null : drXReadout,
      y_readout_name: drYReadout,
      y_normalization: drYNormalization,
      hill_slope_constraint: drHillConstraint,
      normalization_scope: drNormalizationScope,
      activity_threshold: parseOrNull(drActivityThreshold),
      top_constraint: drTopMode === "lock" ? parseOrNull(drTopConstraint) : null,
      bottom_constraint: drBottomMode === "lock" ? parseOrNull(drBottomConstraint) : null,
      top_constraint_min: drTopMode === "range" ? parseOrNull(drTopMin) : null,
      top_constraint_max: drTopMode === "range" ? parseOrNull(drTopMax) : null,
      bottom_constraint_min: drBottomMode === "range" ? parseOrNull(drBottomMin) : null,
      bottom_constraint_max: drBottomMode === "range" ? parseOrNull(drBottomMax) : null,
      hill_slope_min: drHillCustomRange ? parseOrNull(drHillMin) : null,
      hill_slope_max: drHillCustomRange ? parseOrNull(drHillMax) : null,
      outlier_sigma: drOutlierEnabled ? (parseOrNull(drOutlierSigma) ?? 3.0) : null,
      // Classification thresholds — omit when empty so the backend keeps its
      // default. Otherwise ship the explicit override.
      ...(drInactiveThreshold !== "" && {
        inactive_threshold: parseOrNull(drInactiveThreshold) ?? undefined,
      }),
      ...(drFullR2Min !== "" && {
        full_r2_min: parseOrNull(drFullR2Min) ?? undefined,
      }),
      ...(drFullTopMin !== "" && {
        full_top_min: parseOrNull(drFullTopMin) ?? undefined,
      }),
      ...(drFullBottomMax !== "" && {
        full_bottom_max: parseOrNull(drFullBottomMax) ?? undefined,
      }),
      ...(drPartialR2Min !== "" && {
        partial_r2_min: parseOrNull(drPartialR2Min) ?? undefined,
      }),
      // Intercepts — only emit when the user explicitly configured a list.
      // Empty list lets the backend default to a single 50% intercept.
      ...(drIntercepts.length > 0 && { intercepts: drIntercepts }),
    };
  };

  // When the Y readout changes, prefill Top/Bottom/Hill with the suggested
  // ranges for its normalization — but only if the user hasn't already chosen
  // something. Lets the dialog feel pre-configured without clobbering
  // explicit choices.
  const handleDrYReadoutChange = (newY: string, protocol: Protocol) => {
    setDrYReadout(newY);
    // Different Y readout — its normalizations set may not include the
    // previously-picked layer. Reset to null (raw) so the form stays
    // consistent; the user can re-pick a layer in the picker below.
    setDrYNormalization(null);
    const suggested = suggestedRangesForY(newY, protocol);
    if (!suggested) return;
    let injected = false;
    if (drTopMode === "free") {
      setDrTopMode("range");
      setDrTopMin(String(suggested.topMin));
      setDrTopMax(String(suggested.topMax));
      injected = true;
    }
    if (drBottomMode === "free") {
      setDrBottomMode("range");
      setDrBottomMin(String(suggested.bottomMin));
      setDrBottomMax(String(suggested.bottomMax));
      injected = true;
    }
    if (!drHillCustomRange) {
      setDrHillCustomRange(true);
      setDrHillMin(String(suggested.hillMin));
      setDrHillMax(String(suggested.hillMax));
      injected = true;
    }
    if (injected) {
      showInfo("Applied suggested ranges for % readout");
    }
  };

  /** Apply suggested ranges to Top, Bottom, Hill in one click. */
  const applySuggestedRanges = (protocol: Protocol) => {
    const suggested = suggestedRangesForY(drYReadout, protocol);
    if (!suggested) return;
    setDrTopMode("range");
    setDrTopMin(String(suggested.topMin));
    setDrTopMax(String(suggested.topMax));
    setDrBottomMode("range");
    setDrBottomMin(String(suggested.bottomMin));
    setDrBottomMax(String(suggested.bottomMax));
    setDrHillCustomRange(true);
    setDrHillMin(String(suggested.hillMin));
    setDrHillMax(String(suggested.hillMax));
  };

  // ---- validation ----

  // Range-mode validation. Empty inputs become NaN via parseFloat — we
  // refuse to ship those to the backend. Min<Max required.
  const drTopRangeError =
    rdDataType === "dose_response" && drTopMode === "range" && !isFiniteRange(drTopMin, drTopMax);
  const drBottomRangeError =
    rdDataType === "dose_response" &&
    drBottomMode === "range" &&
    !isFiniteRange(drBottomMin, drBottomMax);
  const drTopLockError =
    rdDataType === "dose_response" && drTopMode === "lock" && !isFiniteValue(drTopConstraint);
  const drBottomLockError =
    rdDataType === "dose_response" && drBottomMode === "lock" && !isFiniteValue(drBottomConstraint);
  const drHillRangeError =
    rdDataType === "dose_response" && drHillCustomRange && !isFiniteRange(drHillMin, drHillMax);

  // Classification threshold validation. Empty = inherit default = OK.
  // When set: numeric required, R² fields ∈ (0, 1], full_top_min must be
  // strictly greater than full_bottom_max so the FULL band is non-empty.
  const isFiniteUnitInterval = (s: string): boolean => {
    if (s.trim() === "") return true; // empty inherits default
    const v = Number.parseFloat(s);
    return Number.isFinite(v) && v > 0 && v <= 1;
  };
  const drInactiveThresholdError =
    rdDataType === "dose_response" &&
    drInactiveThreshold !== "" &&
    !isFiniteValue(drInactiveThreshold);
  const drFullR2MinError = rdDataType === "dose_response" && !isFiniteUnitInterval(drFullR2Min);
  const drPartialR2MinError =
    rdDataType === "dose_response" && !isFiniteUnitInterval(drPartialR2Min);
  const drFullTopMinError =
    rdDataType === "dose_response" && drFullTopMin !== "" && !isFiniteValue(drFullTopMin);
  const drFullBottomMaxError =
    rdDataType === "dose_response" && drFullBottomMax !== "" && !isFiniteValue(drFullBottomMax);
  const drFullPlateauOrderError =
    rdDataType === "dose_response" &&
    drFullTopMin !== "" &&
    drFullBottomMax !== "" &&
    isFiniteValue(drFullTopMin) &&
    isFiniteValue(drFullBottomMax) &&
    Number.parseFloat(drFullTopMin) <= Number.parseFloat(drFullBottomMax);
  const drFormInvalid =
    drTopRangeError ||
    drBottomRangeError ||
    drTopLockError ||
    drBottomLockError ||
    drHillRangeError ||
    drInactiveThresholdError ||
    drFullR2MinError ||
    drPartialR2MinError ||
    drFullTopMinError ||
    drFullBottomMaxError ||
    drFullPlateauOrderError;

  return {
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

    drCurveType,
    setDrCurveType,
    drXReadout,
    setDrXReadout,
    drYReadout,
    setDrYReadout,
    drYNormalization,
    setDrYNormalization,
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

    openEditReadout,
    closeEditReadout,
    resetDoseResponseFields,
    handleDrYReadoutChange,
    applySuggestedRanges,

    validation: {
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
      drFormInvalid,
    },

    buildDoseResponseConfig,
  };
}
