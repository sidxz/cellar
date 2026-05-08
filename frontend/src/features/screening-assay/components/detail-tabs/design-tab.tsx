"use client";

import { useOntologySlots } from "@/features/workspace-config/hooks/use-ontology-slots";
import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Textarea } from "@/shared/components/ui/textarea";
import { showInfo } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import { ExternalLink, Eye, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { usePlateTemplates } from "../../hooks/use-plate-templates";
import {
  useAddConditionDefinition,
  useAddReadoutDefinition,
  useProtocols,
  useRemoveConditionDefinition,
  useRemoveControlLayout,
  useRemoveOntologyAnnotation,
  useRemoveReadoutDefinition,
  useSetControlLayout,
  useSetOntologyAnnotation,
  useUpdateConditionDefinition,
  useUpdateProtocol,
  useUpdateReadoutDefinition,
} from "../../hooks/use-protocols";
import { resolvePickListColor } from "../../lib/pick-list-colors";
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
  type InterceptSpec,
  NORMALIZATION_SCOPE_LABELS,
  type NormalizationScope,
  PLATE_FORMAT_LABELS,
  POS_CONTROL_SIGNAL_LABELS,
  type PickListValue,
  type PlateFormat,
  type PosControlSignal,
  type Protocol,
  type ProtocolStatus,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  READOUT_NORMALIZATION_LABELS,
  type ReadoutAggregation,
  type ReadoutDataType,
  type ReadoutNormalization,
} from "../../types";
import { ConditionGroupTable } from "../condition-group-table";
import { FormulaInput } from "../formula-input";
import { InterceptsEditor } from "../intercepts-editor";
import { PickListEditor } from "../pick-list-editor";
import { PlateMapView } from "../plate-map-view";
import { ReadoutDefinitionViewerDialog } from "../readout-definition-viewer-dialog";
import { NormalizationCheckboxGroup } from "../readout-normalization-checkboxes";

function isFiniteValue(s: string): boolean {
  if (s.trim() === "") return false;
  const v = Number.parseFloat(s);
  return Number.isFinite(v);
}

function isFiniteRange(minS: string, maxS: string): boolean {
  if (!isFiniteValue(minS) || !isFiniteValue(maxS)) return false;
  return Number.parseFloat(minS) < Number.parseFloat(maxS);
}

type ParamMode = "free" | "range" | "lock";
const PARAM_MODES: ParamMode[] = ["free", "range", "lock"];

// Tiny segmented control reused by Top and Bottom param blocks.
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
// DesignTab
// ---------------------------------------------------------------------------

interface DesignTabProps {
  protocol: Protocol;
  protocolId: string;
}

export function DesignTab({ protocol, protocolId }: DesignTabProps) {
  const status = protocol.status as ProtocolStatus;
  const isDraft = status === "draft";
  const isRetired = status === "retired";
  const isLocked = protocol.is_locked;
  // Additive ops (add readout/condition, add NEW control layout, edit
  // cosmetic fields) — DRAFT or unlocked ACTIVE.
  const canAddMetadata = !isLocked && !isRetired;
  // Destructive / structural ops (remove, rename, replace existing
  // layout, ontology edits) — strict DRAFT only. Lock blocks DRAFT too.
  const canStructurallyEdit = isDraft && !isLocked;

  // --- Mutations ---
  const updateProtocol = useUpdateProtocol(protocolId);
  const addReadoutDef = useAddReadoutDefinition(protocolId);
  const removeReadoutDef = useRemoveReadoutDefinition(protocolId);
  const updateReadoutDef = useUpdateReadoutDefinition(protocolId);
  // For @-completion in the formula editor: list of workspace protocols
  // (names only; cross-protocol formulas reference them by name).
  const { data: allProtocols } = useProtocols();
  const protocolNames = useMemo(
    () => (allProtocols ?? []).filter((p) => p.id !== protocolId).map((p) => p.name),
    [allProtocols, protocolId],
  );
  const addConditionDef = useAddConditionDefinition(protocolId);
  const removeConditionDef = useRemoveConditionDefinition(protocolId);
  const updateConditionDef = useUpdateConditionDefinition(protocolId);
  const setControlLayout = useSetControlLayout(protocolId);
  const removeControlLayout = useRemoveControlLayout(protocolId);
  const setOntologyAnnotation = useSetOntologyAnnotation(protocolId);
  const removeOntologyAnnotation = useRemoveOntologyAnnotation(protocolId);

  // --- Queries ---
  const { data: plateTemplates } = usePlateTemplates();
  const { data: ontologySlots } = useOntologySlots();

  // --- Dialog state ---
  const [addReadoutOpen, setAddReadoutOpen] = useState(false);
  const [addConditionOpen, setAddConditionOpen] = useState(false);
  const [editingReadoutId, setEditingReadoutId] = useState<string | null>(null);
  const [viewingReadoutId, setViewingReadoutId] = useState<string | null>(null);

  // --- Readout form fields ---
  const [rdName, setRdName] = useState("");
  const [rdDescription, setRdDescription] = useState("");
  const [rdIsCalculated, setRdIsCalculated] = useState(false);
  const [rdCalculationFormula, setRdCalculationFormula] = useState("");
  const [rdDataType, setRdDataType] = useState("numeric");
  const [rdUnit, setRdUnit] = useState("");
  const [rdAggregation, setRdAggregation] = useState("none");
  const [rdNormalizations, setRdNormalizations] = useState<ReadoutNormalization[]>([]);
  const [rdPickListValues, setRdPickListValues] = useState<PickListValue[]>([]);
  // Dose-response config sub-fields (only used when rdDataType === "dose_response").
  // X-axis sentinel: when drXReadout === WELL_CONC_X, the curve fits against the
  // well's own concentration (the default and most common case). Mapped to
  // x_readout_name=null in the payload.
  const [drCurveType, setDrCurveType] = useState<CurveType>("ic50");
  const [drXReadout, setDrXReadout] = useState<string>(WELL_CONC_X);
  const [drYReadout, setDrYReadout] = useState("");
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

  const resetDoseResponseFields = () => {
    setDrCurveType("ic50");
    setDrXReadout(WELL_CONC_X);
    setDrYReadout("");
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
  const suggestedRangesForY = (yReadoutName: string): typeof PERCENT_FIT_RANGES | null => {
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

  const openEditReadout = (rdId: string) => {
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
    setEditingReadoutId(rdId);
  };

  const closeEditReadout = () => {
    setEditingReadoutId(null);
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
  const handleDrYReadoutChange = (newY: string) => {
    setDrYReadout(newY);
    const suggested = suggestedRangesForY(newY);
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
  const applySuggestedRanges = () => {
    const suggested = suggestedRangesForY(drYReadout);
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

  /** Numeric readouts available as X/Y axis candidates, optionally excluding one. */
  const axisCandidates = (excludeId: string | null) =>
    protocol.readout_definitions
      .filter((rd) => rd.data_type === "numeric" && rd.id !== excludeId)
      .map((rd) => rd.name);

  const renderDoseResponseFields = (excludeId: string | null) => {
    if (rdDataType !== "dose_response") return null;
    const candidates = axisCandidates(excludeId);
    const xIsAdvanced = drXReadout !== WELL_CONC_X;
    const suggested = suggestedRangesForY(drYReadout);
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
            <Select value={drYReadout} onValueChange={handleDrYReadoutChange}>
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
                Pick a different readout only when the X axis is a derivation (e.g.
                log-concentration computed by a calculated readout). 99% of dose-response fits use
                the well's recorded concentration.
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
                <p className="text-xs text-destructive">
                  Enter both min and max with min &lt; max.
                </p>
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
                <p className="text-xs text-destructive">
                  Enter both min and max with min &lt; max.
                </p>
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
                <p className="text-xs text-destructive">
                  Enter both min and max with min &lt; max.
                </p>
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
              onClick={applySuggestedRanges}
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
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  max response
                </span>
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
  };

  // --- Condition form fields ---
  const [cdName, setCdName] = useState("");
  const [cdDataType, setCdDataType] = useState("text");
  const [cdUnit, setCdUnit] = useState("");
  const [editingConditionId, setEditingConditionId] = useState<string | null>(null);

  const openEditCondition = (cdId: string) => {
    const cd = protocol.condition_definitions.find((c) => c.id === cdId);
    if (!cd) return;
    setCdName(cd.name);
    setCdDataType(cd.data_type);
    setCdUnit(cd.unit ?? "");
    setEditingConditionId(cdId);
  };

  const closeEditCondition = () => {
    setEditingConditionId(null);
    setCdName("");
    setCdDataType("text");
    setCdUnit("");
  };

  // --- Control layout form fields ---
  const [clFormat, setClFormat] = useState("96");
  const [clTemplateId, setClTemplateId] = useState("");

  return (
    <div className="space-y-6">
      {/* ── 1. Ontology Annotations ─────────────────────────────────────── */}
      {ontologySlots && ontologySlots.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Ontology Annotations</CardTitle>
            <CardDescription>Controlled vocabulary terms for this protocol.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {ontologySlots.map((slot) => {
              const currentTerms = protocol.ontology_annotations?.[slot.name] ?? [];
              return (
                <div key={slot.id} className="space-y-1">
                  <Label className="text-sm font-medium">
                    {slot.label}
                    {slot.is_required && <span className="ml-1 text-destructive">*</span>}
                  </Label>

                  {canStructurallyEdit ? (
                    <OntologySearchInput
                      ontologySources={slot.ontology_sources}
                      rootConceptId={slot.root_concept_id}
                      allowFreeText={slot.allow_free_text}
                      value={currentTerms.map((t) => ({
                        term_id: t.term_id,
                        label: t.label,
                        ontology_source: t.ontology_source,
                        uri: t.uri,
                      }))}
                      onChange={(terms: OntologyTerm[]) => {
                        if (terms.length === 0) {
                          removeOntologyAnnotation.mutate(slot.name);
                        } else {
                          setOntologyAnnotation.mutate({
                            slot: slot.name,
                            terms: terms.map((t) => ({
                              term_id: t.term_id,
                              label: t.label,
                              ontology_source: t.ontology_source,
                              uri: t.uri,
                            })),
                          });
                        }
                      }}
                    />
                  ) : currentTerms.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {currentTerms.map((t) => (
                        <Badge key={t.term_id} variant="secondary">
                          {t.label}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No terms assigned.</p>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* ── 2. Readout Definitions ──────────────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Readout Definitions</CardTitle>
            <CardDescription>Measured values captured for each compound in a run.</CardDescription>
          </div>
          {canAddMetadata && (
            <Button size="sm" variant="outline" onClick={() => setAddReadoutOpen(true)}>
              <Plus className="mr-1 h-4 w-4" />
              Add
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {protocol.readout_definitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No readout definitions yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">#</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Data Type</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Aggregation</TableHead>
                  <TableHead>Normalization</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {protocol.readout_definitions.map((rd, idx) => (
                  <TableRow key={rd.id}>
                    <TableCell className="text-muted-foreground">{idx + 1}</TableCell>
                    <TableCell>
                      <button
                        type="button"
                        className="font-medium hover:underline underline-offset-2"
                        onClick={() => setViewingReadoutId(rd.id)}
                        title="View readout definition details"
                      >
                        {rd.name}
                      </button>
                      {rd.dose_response_config && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({CURVE_TYPE_LABELS[rd.dose_response_config.curve_type as CurveType]}:{" "}
                          {rd.dose_response_config.x_readout_name ?? "well concentration"} vs{" "}
                          {rd.dose_response_config.y_readout_name})
                        </span>
                      )}
                      {rd.is_calculated && rd.calculation_formula && (
                        <span
                          className="ml-2 inline-flex items-center gap-1 text-xs text-muted-foreground italic"
                          title={`Computed from formula: ${rd.calculation_formula}`}
                        >
                          ƒ{" "}
                          <code className="font-mono not-italic">
                            {rd.calculation_formula.length > 40
                              ? `${rd.calculation_formula.slice(0, 40)}…`
                              : rd.calculation_formula}
                          </code>
                        </span>
                      )}
                      {rd.pick_list_values && rd.pick_list_values.length > 0 && (
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {rd.pick_list_values.map((v) => {
                            const c = resolvePickListColor(v.label, v.color);
                            return (
                              <Badge
                                key={v.label}
                                variant="outline"
                                className={cn("text-[10px]", c.bg, c.text)}
                              >
                                {v.label}
                              </Badge>
                            );
                          })}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      {READOUT_DATA_TYPE_LABELS[rd.data_type as ReadoutDataType] ?? rd.data_type}
                      {rd.dose_response_config && (
                        <span className="ml-1 text-xs text-muted-foreground">
                          ({CURVE_TYPE_LABELS[rd.dose_response_config.curve_type as CurveType]})
                        </span>
                      )}
                    </TableCell>
                    <TableCell>{rd.unit ?? "\u2014"}</TableCell>
                    <TableCell>
                      {READOUT_AGGREGATION_LABELS[rd.aggregation as ReadoutAggregation] ??
                        rd.aggregation}
                    </TableCell>
                    <TableCell>
                      {rd.normalizations && rd.normalizations.length > 0
                        ? rd.normalizations
                            .map(
                              (n) => READOUT_NORMALIZATION_LABELS[n as ReadoutNormalization] ?? n,
                            )
                            .join(", ")
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => setViewingReadoutId(rd.id)}
                          title="View configuration"
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        {canAddMetadata && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => openEditReadout(rd.id)}
                            title={
                              isDraft
                                ? "Edit"
                                : "Edit (cosmetic fields only — rename / structural changes require a new version)"
                            }
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                        )}
                        {canStructurallyEdit && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive hover:text-destructive"
                            disabled={protocol.readout_definitions.length <= 1}
                            onClick={() => removeReadoutDef.mutate(rd.id)}
                            title="Delete"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── 3. Condition Definitions ────────────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Condition Definitions</CardTitle>
            <CardDescription>Experimental conditions that vary between runs.</CardDescription>
          </div>
          {canAddMetadata && (
            <Button size="sm" variant="outline" onClick={() => setAddConditionOpen(true)}>
              <Plus className="mr-1 h-4 w-4" />
              Add
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {protocol.condition_definitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No condition definitions yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Data Type</TableHead>
                  <TableHead>Unit</TableHead>
                  {canStructurallyEdit && <TableHead className="w-10" />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {protocol.condition_definitions.map((cd) => (
                  <TableRow key={cd.id}>
                    <TableCell className="font-medium">{cd.name}</TableCell>
                    <TableCell className="capitalize">{cd.data_type}</TableCell>
                    <TableCell>{cd.unit ?? "\u2014"}</TableCell>
                    {canStructurallyEdit && (
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => openEditCondition(cd.id)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive hover:text-destructive"
                            onClick={() => removeConditionDef.mutate(cd.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── 4. Control Layouts ──────────────────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <div>
            <CardTitle>Control Layouts</CardTitle>
            <CardDescription>
              Plate templates for positive/negative controls per plate format. Required for runs
              that use control-based normalization (e.g., % Inhibition).
            </CardDescription>
          </div>
          <Button asChild size="sm" variant="outline">
            <Link href="/assays/plate-templates" target="_blank">
              <ExternalLink className="mr-1 h-3.5 w-3.5" />
              Manage Templates
            </Link>
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Existing layouts */}
          {protocol.control_layouts && Object.keys(protocol.control_layouts).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(protocol.control_layouts).map(([format, templateId]) => {
                const tmpl = plateTemplates?.find((pt) => pt.id === templateId);
                return (
                  <div key={format} className="rounded-md border px-3 py-2 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm">
                        {PLATE_FORMAT_LABELS[format as PlateFormat] ?? `${format}-well`} &rarr;{" "}
                        <span className="font-medium">{tmpl?.name ?? templateId}</span>
                      </span>
                      {canStructurallyEdit && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() => removeControlLayout.mutate(format)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                    {/* Read-only preview of the template — same color
                          vocabulary as the editor + Plate Templates page,
                          so chemists recognize the layout instantly. */}
                    {tmpl && <PlateMapView format={tmpl.format} templateMap={tmpl.template_map} />}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No control layouts configured.</p>
          )}

          {/* Add form — additive, allowed on unlocked ACTIVE for new
              formats. Replacing an existing format's layout still
              requires DRAFT (would change Z′ interpretation of prior
              runs); we filter the format dropdown to those not yet
              configured so users can't accidentally try. */}
          {canAddMetadata &&
            (plateTemplates && plateTemplates.length === 0 ? (
              <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                No plate templates exist in this workspace yet. Create one first — define which
                wells are positive/negative controls for each plate format.
                <div className="mt-2">
                  <Button asChild size="sm">
                    <Link href="/assays/plate-templates">
                      <Plus className="mr-1 h-3.5 w-3.5" />
                      Create Plate Template
                    </Link>
                  </Button>
                </div>
              </div>
            ) : (
              (() => {
                const configuredFormats = Object.keys(protocol.control_layouts ?? {});
                // On non-DRAFT, filter to formats not already configured —
                // the BE rejects replacing on ACTIVE. On DRAFT, any
                // format is fair game (replace included).
                const availableFormats = isDraft
                  ? Object.keys(PLATE_FORMAT_LABELS)
                  : Object.keys(PLATE_FORMAT_LABELS).filter((f) => !configuredFormats.includes(f));
                if (availableFormats.length === 0) {
                  return (
                    <p className="text-sm text-muted-foreground">
                      All plate formats already have a layout configured. To replace an existing
                      layout, create a new version.
                    </p>
                  );
                }
                return (
                  <div className="flex items-end gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs">Format</Label>
                      <Select
                        value={availableFormats.includes(clFormat) ? clFormat : availableFormats[0]}
                        onValueChange={(v) => {
                          setClFormat(v);
                          setClTemplateId("");
                        }}
                      >
                        <SelectTrigger className="w-[120px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {availableFormats.map((val) => (
                            <SelectItem key={val} value={val}>
                              {PLATE_FORMAT_LABELS[val as keyof typeof PLATE_FORMAT_LABELS]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Template</Label>
                      <Select value={clTemplateId} onValueChange={setClTemplateId}>
                        <SelectTrigger className="w-[200px]">
                          <SelectValue placeholder="Select template..." />
                        </SelectTrigger>
                        <SelectContent>
                          {(plateTemplates ?? [])
                            .filter((pt) => pt.format === clFormat)
                            .map((pt) => (
                              <SelectItem key={pt.id} value={pt.id}>
                                {pt.name}
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button
                      size="sm"
                      disabled={!clTemplateId}
                      onClick={() => {
                        setControlLayout.mutate(
                          {
                            plate_format: clFormat,
                            template_id: clTemplateId,
                          },
                          {
                            onSuccess: () => {
                              setClTemplateId("");
                            },
                          },
                        );
                      }}
                    >
                      Set Layout
                    </Button>
                  </div>
                );
              })()
            ))}
        </CardContent>
      </Card>

      {/* ── 4b. Control Convention ──────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Control Convention</CardTitle>
          <CardDescription>
            Tells the calculation engine which control well produces high raw signal. Drives %
            Inhibition / % Activation / % Control / Z-Score formula dispatch and the heatmap legend.
            Editable after publish — re-run Recompute on each run after changing.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">POS control signal</Label>
              <Select
                value={protocol.pos_control_signal}
                onValueChange={(v) => {
                  if (v === protocol.pos_control_signal) return;
                  updateProtocol.mutate({
                    pos_control_signal: v as PosControlSignal,
                  });
                }}
                disabled={isRetired || updateProtocol.isPending}
              >
                <SelectTrigger className="w-[420px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(["high", "low"] as PosControlSignal[]).map((v) => (
                    <SelectItem key={v} value={v}>
                      {POS_CONTROL_SIGNAL_LABELS[v]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {updateProtocol.isPending && (
              <span className="pb-2 text-xs text-muted-foreground">Saving…</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── 5. Condition Grouping ───────────────────────────────────────── */}
      {protocol.condition_definitions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Condition Grouping</CardTitle>
            <CardDescription>
              Aggregated readout values grouped by experimental condition.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ConditionGroupTable
              protocolId={protocolId}
              conditionDefinitions={protocol.condition_definitions}
            />
          </CardContent>
        </Card>
      )}

      {/* ── Add Readout Definition Dialog ───────────────────────────────── */}
      <Dialog open={addReadoutOpen} onOpenChange={setAddReadoutOpen}>
        <DialogContent className="w-[min(95vw,1000px)] max-w-[1000px] sm:max-w-[1000px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Add Readout Definition</DialogTitle>
            <DialogDescription>Define a new measured value for this protocol.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input
                value={rdName}
                onChange={(e) => setRdName(e.target.value)}
                placeholder="e.g. % Inhibition"
              />
              {isReservedReadoutName(rdName) && (
                <p className="text-xs text-destructive">
                  &lsquo;{rdName.trim()}&rsquo; is a reserved well-metadata name and cannot be used
                  as a readout. The well&apos;s concentration, batch, and compound are tracked on
                  the well itself, not as readouts.
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
                placeholder="What this readout captures, e.g. 'Compound activity vs DMSO baseline, normalized per plate.'"
                rows={2}
              />
            </div>
            <div className="space-y-1">
              <Label>Data Type</Label>
              <Select value={rdDataType} onValueChange={setRdDataType}>
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
                Normalization) are hidden \u2014 pick lists are categorical
                and these fields don't apply. */}
            {rdDataType === "pick_list" ? (
              <div className="space-y-1">
                <Label>Allowed Values</Label>
                <PickListEditor value={rdPickListValues} onChange={setRdPickListValues} />
              </div>
            ) : (
              <>
                <div className="space-y-1">
                  <Label>Unit</Label>
                  <Input
                    value={rdUnit}
                    onChange={(e) => setRdUnit(e.target.value)}
                    placeholder="e.g. nM, %, \u00B5M"
                  />
                </div>
                {/* Calculated toggle \u2014 only meaningful for numeric (the
                    formula evaluator returns a float). When on, hide
                    Aggregation + Normalization: the calc engine ignores
                    both for is_calculated readouts (see
                    readout_calculation_engine.py:172, 282). */}
                {rdDataType === "numeric" && (
                  <div className="flex items-center gap-3 pt-1">
                    <Switch
                      checked={rdIsCalculated}
                      onCheckedChange={(v) => setRdIsCalculated(v === true)}
                    />
                    <Label className="text-sm font-normal">
                      Calculated{" "}
                      <span className="text-muted-foreground">
                        \u2014 value derived from a formula over other readouts
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
                      availableReadoutNames={protocol.readout_definitions.map((rd) => rd.name)}
                      protocolNames={protocolNames}
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
                      <Select value={rdAggregation} onValueChange={setRdAggregation}>
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
                      />
                    </div>
                  </>
                )}
              </>
            )}
            {renderDoseResponseFields(null)}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddReadoutOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={
                !rdName.trim() ||
                isReservedReadoutName(rdName) ||
                addReadoutDef.isPending ||
                (rdDataType === "dose_response" && !drYReadout) ||
                (rdDataType === "pick_list" &&
                  rdPickListValues.filter((v) => v.label.trim()).length === 0) ||
                (rdDataType === "numeric" && rdIsCalculated && !rdCalculationFormula.trim()) ||
                drFormInvalid
              }
              onClick={() => {
                const cleanedPickList = rdPickListValues
                  .filter((v) => v.label.trim())
                  .map((v) => ({
                    label: v.label.trim(),
                    color: v.color || null,
                  }));
                const isCalc = rdDataType === "numeric" && rdIsCalculated;
                addReadoutDef.mutate(
                  {
                    name: rdName.trim(),
                    description: rdDescription.trim() || null,
                    data_type: rdDataType,
                    unit: rdUnit.trim() || undefined,
                    // Calculated readouts: send empty aggregation +
                    // normalizations so the BE doesn't store stale values
                    // alongside the formula (calc engine ignores them).
                    aggregation: isCalc ? "none" : rdAggregation,
                    normalizations: isCalc ? [] : rdNormalizations,
                    is_calculated: isCalc,
                    calculation_formula: isCalc ? rdCalculationFormula.trim() || null : null,
                    pick_list_values: rdDataType === "pick_list" ? cleanedPickList : undefined,
                    dose_response_config: buildDoseResponseConfig(),
                  },
                  {
                    onSuccess: () => {
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
                      setAddReadoutOpen(false);
                    },
                  },
                );
              }}
            >
              {addReadoutDef.isPending ? "Adding..." : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Edit Readout Definition Dialog ──────────────────────────────── */}
      <Dialog
        open={editingReadoutId !== null}
        onOpenChange={(open) => {
          if (!open) closeEditReadout();
        }}
      >
        <DialogContent className="w-[min(95vw,1000px)] max-w-[1000px] sm:max-w-[1000px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Readout Definition</DialogTitle>
            <DialogDescription>
              {isDraft
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
                disabled={!isDraft}
              />
              {isReservedReadoutName(rdName) && (
                <p className="text-xs text-destructive">
                  &lsquo;{rdName.trim()}&rsquo; is a reserved well-metadata name and cannot be used
                  as a readout.
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
                placeholder="What this readout captures."
                rows={2}
              />
            </div>
            <div className="space-y-1">
              <Label>Data Type</Label>
              <Select value={rdDataType} onValueChange={setRdDataType} disabled={!isDraft}>
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
                  disabled={!isDraft}
                />
              </div>
            ) : (
              <>
                <div className="space-y-1">
                  <Label>Unit</Label>
                  <Input value={rdUnit} onChange={(e) => setRdUnit(e.target.value)} />
                </div>
                {/* Calculated toggle — structural (changing the formula
                    on ACTIVE would silently shift computed values across
                    every prior run). Disabled on non-DRAFT. */}
                {rdDataType === "numeric" && (
                  <div className="flex items-center gap-3 pt-1">
                    <Switch
                      checked={rdIsCalculated}
                      onCheckedChange={(v) => setRdIsCalculated(v === true)}
                      disabled={!isDraft}
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
                      availableReadoutNames={protocol.readout_definitions
                        .filter((rd) => rd.id !== editingReadoutId)
                        .map((rd) => rd.name)}
                      protocolNames={protocolNames}
                      disabled={!isDraft}
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
                        disabled={!isDraft}
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
                        disabled={!isDraft}
                      />
                    </div>
                  </>
                )}
              </>
            )}
            {/* Dose-response fields are structural (curve type, axes,
                intercepts, ranges) — disabled on non-DRAFT. The fields
                inside renderDoseResponseFields don't currently take a
                disabled prop, so we wrap in a disabled-pointer-events
                shim instead. Cleaner long-term: thread `disabled`. */}
            {!isDraft ? (
              <div className="pointer-events-none opacity-60">
                {renderDoseResponseFields(editingReadoutId)}
              </div>
            ) : (
              renderDoseResponseFields(editingReadoutId)
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeEditReadout}>
              Cancel
            </Button>
            <Button
              disabled={
                !rdName.trim() ||
                isReservedReadoutName(rdName) ||
                updateReadoutDef.isPending ||
                (rdDataType === "dose_response" && !drYReadout) ||
                (rdDataType === "pick_list" &&
                  rdPickListValues.filter((v) => v.label.trim()).length === 0) ||
                (rdDataType === "numeric" && rdIsCalculated && !rdCalculationFormula.trim()) ||
                drFormInvalid
              }
              onClick={() => {
                if (!editingReadoutId) return;
                const cleanedPickList = rdPickListValues
                  .filter((v) => v.label.trim())
                  .map((v) => ({
                    label: v.label.trim(),
                    color: v.color || null,
                  }));
                const isCalc = rdDataType === "numeric" && rdIsCalculated;
                updateReadoutDef.mutate(
                  {
                    definitionId: editingReadoutId,
                    data: {
                      name: rdName.trim(),
                      description: rdDescription.trim() || null,
                      data_type: rdDataType,
                      unit: rdUnit.trim() || null,
                      aggregation: isCalc ? "none" : rdAggregation,
                      normalizations: isCalc ? [] : rdNormalizations,
                      is_calculated: isCalc,
                      calculation_formula: isCalc ? rdCalculationFormula.trim() || null : null,
                      pick_list_values: rdDataType === "pick_list" ? cleanedPickList : null,
                      dose_response_config: buildDoseResponseConfig(),
                    },
                  },
                  { onSuccess: closeEditReadout },
                );
              }}
            >
              {updateReadoutDef.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Condition Definition Dialog ─────────────────────────────── */}
      <Dialog open={addConditionOpen} onOpenChange={setAddConditionOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Condition Definition</DialogTitle>
            <DialogDescription>
              Define an experimental condition that varies between runs.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input
                value={cdName}
                onChange={(e) => setCdName(e.target.value)}
                placeholder="e.g. Cell Passage, Temperature"
              />
            </div>
            <div className="space-y-1">
              <Label>Data Type</Label>
              <Select value={cdDataType} onValueChange={setCdDataType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="text">Text</SelectItem>
                  <SelectItem value="numeric">Numeric</SelectItem>
                  <SelectItem value="pick_list">Pick List</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={cdUnit}
                onChange={(e) => setCdUnit(e.target.value)}
                placeholder="e.g. \u00B0C, hrs"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddConditionOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!cdName.trim() || addConditionDef.isPending}
              onClick={() => {
                addConditionDef.mutate(
                  {
                    name: cdName.trim(),
                    data_type: cdDataType,
                    unit: cdUnit.trim() || undefined,
                  },
                  {
                    onSuccess: () => {
                      setCdName("");
                      setCdDataType("text");
                      setCdUnit("");
                      setAddConditionOpen(false);
                    },
                  },
                );
              }}
            >
              {addConditionDef.isPending ? "Adding..." : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Edit Condition Definition Dialog ────────────────────────────── */}
      <Dialog
        open={editingConditionId !== null}
        onOpenChange={(open) => {
          if (!open) closeEditCondition();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Condition Definition</DialogTitle>
            <DialogDescription>
              Update fields on this condition. Only available while the protocol is in draft.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input value={cdName} onChange={(e) => setCdName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Data Type</Label>
              <Select value={cdDataType} onValueChange={setCdDataType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="text">Text</SelectItem>
                  <SelectItem value="numeric">Numeric</SelectItem>
                  <SelectItem value="pick_list">Pick List</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input value={cdUnit} onChange={(e) => setCdUnit(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeEditCondition}>
              Cancel
            </Button>
            <Button
              disabled={!cdName.trim() || updateConditionDef.isPending}
              onClick={() => {
                if (!editingConditionId) return;
                updateConditionDef.mutate(
                  {
                    definitionId: editingConditionId,
                    data: {
                      name: cdName.trim(),
                      data_type: cdDataType,
                      unit: cdUnit.trim() || null,
                    },
                  },
                  { onSuccess: closeEditCondition },
                );
              }}
            >
              {updateConditionDef.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ReadoutDefinitionViewerDialog
        readoutDef={
          viewingReadoutId
            ? (protocol.readout_definitions.find((rd) => rd.id === viewingReadoutId) ?? null)
            : null
        }
        open={viewingReadoutId !== null}
        onOpenChange={(open) => {
          if (!open) setViewingReadoutId(null);
        }}
      />
    </div>
  );
}
