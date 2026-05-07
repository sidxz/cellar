"use client";

import { useState } from "react";
import { ExternalLink, Eye, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import {
  useAddReadoutDefinition,
  useRemoveReadoutDefinition,
  useUpdateReadoutDefinition,
  useAddConditionDefinition,
  useRemoveConditionDefinition,
  useUpdateConditionDefinition,
  useSetControlLayout,
  useRemoveControlLayout,
  useSetOntologyAnnotation,
  useRemoveOntologyAnnotation,
  useUpdateProtocol,
} from "../../hooks/use-protocols";
import { useOntologySlots } from "@/features/workspace-config/hooks/use-ontology-slots";
import {
  OntologySearchInput,
  type OntologyTerm,
} from "@/shared/components/ontology-search-input";
import { usePlateTemplates } from "../../hooks/use-plate-templates";
import { ConditionGroupTable } from "../condition-group-table";
import { ReadoutDefinitionViewerDialog } from "../readout-definition-viewer-dialog";
import {
  CURVE_TYPE_LABELS,
  HILL_SLOPE_CONSTRAINT_LABELS,
  NORMALIZATION_SCOPE_LABELS,
  PLATE_FORMAT_LABELS,
  POS_CONTROL_SIGNAL_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  READOUT_NORMALIZATION_LABELS,
  type CurveType,
  type HillSlopeConstraint,
  type NormalizationScope,
  type PlateFormat,
  type PosControlSignal,
  type Protocol,
  type ProtocolStatus,
  type ReadoutAggregation,
  type ReadoutDataType,
  type ReadoutNormalization,
} from "../../types";

// Reserved readout-definition names that collide with built-in well metadata.
// Kept in sync with backend domain.screening_assay.protocol._RESERVED_READOUT_NAMES.
const RESERVED_READOUT_NAMES: ReadonlySet<string> = new Set([
  "concentration",
  "dose",
  "well",
  "plate",
  "batch",
  "compound",
]);

function isReservedReadoutName(name: string): boolean {
  return RESERVED_READOUT_NAMES.has(name.trim().toLowerCase());
}

// Sentinel for the X-axis dropdown that means "use the well's concentration"
// (mapped to x_readout_name=null in the payload).
const WELL_CONC_X = "__well_concentration__";

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

  // --- Mutations ---
  const updateProtocol = useUpdateProtocol(protocolId);
  const addReadoutDef = useAddReadoutDefinition(protocolId);
  const removeReadoutDef = useRemoveReadoutDefinition(protocolId);
  const updateReadoutDef = useUpdateReadoutDefinition(protocolId);
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
  const [rdDataType, setRdDataType] = useState("numeric");
  const [rdUnit, setRdUnit] = useState("");
  const [rdAggregation, setRdAggregation] = useState("none");
  const [rdNormalization, setRdNormalization] = useState("none");
  // Dose-response config sub-fields (only used when rdDataType === "dose_response").
  // X-axis sentinel: when drXReadout === WELL_CONC_X, the curve fits against the
  // well's own concentration (the default and most common case). Mapped to
  // x_readout_name=null in the payload.
  const [drCurveType, setDrCurveType] = useState<CurveType>("ic50");
  const [drXReadout, setDrXReadout] = useState<string>(WELL_CONC_X);
  const [drYReadout, setDrYReadout] = useState("");
  const [drHillConstraint, setDrHillConstraint] =
    useState<HillSlopeConstraint>("unconstrained");
  const [drNormalizationScope, setDrNormalizationScope] =
    useState<NormalizationScope>("per_plate");
  const [drActivityThreshold, setDrActivityThreshold] = useState("");
  // Top/Bottom now have a tri-state mode (Phase B). Lock and Range are
  // mutually exclusive in the domain; the mode field is the UI's source of
  // truth and decides which of the *Constraint* / *Min* / *Max* fields ship.
  type ParamMode = "free" | "range" | "lock";
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
  };

  // Y readouts with bounded normalization (% Inhibition/Activation/Control)
  // get CDD's IC50calc default ranges: Top ∈ [85, 110], Bottom ∈ [-10, 10],
  // Hill ∈ [0.9, 1.1]. Ranges (not hard locks) let the optimizer pick a
  // data-consistent plateau when the upper plateau isn't observed in the
  // dose range — the difference between IC50 = 39 µM (lock at 85) and
  // IC50 = 70 µM (range up to 110) on partial curves.
  const suggestedRangesForY = (
    yReadoutName: string,
  ): {
    topMin: number;
    topMax: number;
    bottomMin: number;
    bottomMax: number;
    hillMin: number;
    hillMax: number;
  } | null => {
    const y = protocol.readout_definitions.find((r) => r.name === yReadoutName);
    if (!y) return null;
    switch (y.normalization) {
      case "percent_inhibition":
      case "percent_activation":
      case "percent_control":
        return {
          topMin: 85,
          topMax: 110,
          bottomMin: -10,
          bottomMax: 10,
          hillMin: 0.9,
          hillMax: 1.1,
        };
      default:
        return null;
    }
  };

  const openEditReadout = (rdId: string) => {
    const rd = protocol.readout_definitions.find((r) => r.id === rdId);
    if (!rd) return;
    setRdName(rd.name);
    setRdDataType(rd.data_type);
    setRdUnit(rd.unit ?? "");
    setRdAggregation(rd.aggregation);
    setRdNormalization(rd.normalization);
    if (rd.dose_response_config) {
      const cfg = rd.dose_response_config;
      setDrCurveType(cfg.curve_type);
      setDrXReadout(cfg.x_readout_name ?? WELL_CONC_X);
      setDrYReadout(cfg.y_readout_name);
      setDrHillConstraint(cfg.hill_slope_constraint);
      setDrNormalizationScope(cfg.normalization_scope);
      setDrActivityThreshold(
        cfg.activity_threshold != null ? String(cfg.activity_threshold) : "",
      );

      // Top: lock takes precedence; else range; else free.
      if (cfg.top_constraint != null) {
        setDrTopMode("lock");
        setDrTopConstraint(String(cfg.top_constraint));
        setDrTopMin("");
        setDrTopMax("");
      } else if (
        cfg.top_constraint_min != null ||
        cfg.top_constraint_max != null
      ) {
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
      } else if (
        cfg.bottom_constraint_min != null ||
        cfg.bottom_constraint_max != null
      ) {
        setDrBottomMode("range");
        setDrBottomConstraint("");
        setDrBottomMin(
          cfg.bottom_constraint_min != null ? String(cfg.bottom_constraint_min) : "",
        );
        setDrBottomMax(
          cfg.bottom_constraint_max != null ? String(cfg.bottom_constraint_max) : "",
        );
      } else {
        setDrBottomMode("free");
        setDrBottomConstraint("");
        setDrBottomMin("");
        setDrBottomMax("");
      }

      const hasHillRange =
        cfg.hill_slope_min != null || cfg.hill_slope_max != null;
      setDrHillCustomRange(hasHillRange);
      setDrHillMin(cfg.hill_slope_min != null ? String(cfg.hill_slope_min) : "");
      setDrHillMax(cfg.hill_slope_max != null ? String(cfg.hill_slope_max) : "");

      const sigma = cfg.outlier_sigma;
      setDrOutlierEnabled(sigma != null);
      setDrOutlierSigma(sigma != null ? String(sigma) : "3");
    } else {
      resetDoseResponseFields();
    }
    setEditingReadoutId(rdId);
  };

  const closeEditReadout = () => {
    setEditingReadoutId(null);
    setRdName("");
    setRdDataType("numeric");
    setRdUnit("");
    setRdAggregation("none");
    setRdNormalization("none");
    resetDoseResponseFields();
  };

  /** Build the dose_response_config payload for add/update mutations.
   *  Encodes the tri-state mode for Top/Bottom into the lock vs range fields.
   */
  const buildDoseResponseConfig = (): Record<string, unknown> | null => {
    if (rdDataType !== "dose_response") return null;
    if (!drYReadout) return null;
    const parseOrNull = (s: string) => (s !== "" ? parseFloat(s) : null);
    return {
      curve_type: drCurveType,
      x_readout_name: drXReadout === WELL_CONC_X ? null : drXReadout,
      y_readout_name: drYReadout,
      hill_slope_constraint: drHillConstraint,
      normalization_scope: drNormalizationScope,
      activity_threshold: parseOrNull(drActivityThreshold),
      top_constraint: drTopMode === "lock" ? parseOrNull(drTopConstraint) : null,
      bottom_constraint:
        drBottomMode === "lock" ? parseOrNull(drBottomConstraint) : null,
      top_constraint_min: drTopMode === "range" ? parseOrNull(drTopMin) : null,
      top_constraint_max: drTopMode === "range" ? parseOrNull(drTopMax) : null,
      bottom_constraint_min:
        drBottomMode === "range" ? parseOrNull(drBottomMin) : null,
      bottom_constraint_max:
        drBottomMode === "range" ? parseOrNull(drBottomMax) : null,
      hill_slope_min: drHillCustomRange ? parseOrNull(drHillMin) : null,
      hill_slope_max: drHillCustomRange ? parseOrNull(drHillMax) : null,
      outlier_sigma: drOutlierEnabled
        ? parseOrNull(drOutlierSigma) ?? 3.0
        : null,
    };
  };

  // When the Y readout changes, prefill Top/Bottom/Hill with CDD-style ranges
  // for its normalization — but only if the user hasn't already chosen
  // something. Lets the dialog feel pre-configured without clobbering
  // explicit choices.
  const handleDrYReadoutChange = (newY: string) => {
    setDrYReadout(newY);
    const suggested = suggestedRangesForY(newY);
    if (!suggested) return;
    if (drTopMode === "free") {
      setDrTopMode("range");
      setDrTopMin(String(suggested.topMin));
      setDrTopMax(String(suggested.topMax));
    }
    if (drBottomMode === "free") {
      setDrBottomMode("range");
      setDrBottomMin(String(suggested.bottomMin));
      setDrBottomMax(String(suggested.bottomMax));
    }
    if (!drHillCustomRange) {
      setDrHillCustomRange(true);
      setDrHillMin(String(suggested.hillMin));
      setDrHillMax(String(suggested.hillMax));
    }
  };

  /** Apply CDD-style ranges to Top, Bottom, Hill in one click. */
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

  /** Numeric readouts available as X/Y axis candidates, optionally excluding one. */
  const axisCandidates = (excludeId: string | null) =>
    protocol.readout_definitions
      .filter((rd) => rd.data_type === "numeric" && rd.id !== excludeId)
      .map((rd) => rd.name);

  const renderDoseResponseFields = (excludeId: string | null) => {
    if (rdDataType !== "dose_response") return null;
    const candidates = axisCandidates(excludeId);
    return (
      <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
        <p className="text-xs font-medium">Dose-Response Configuration</p>
        <div className="grid grid-cols-3 gap-3">
          <div className="grid gap-1">
            <Label className="text-xs">Curve Type</Label>
            <Select
              value={drCurveType}
              onValueChange={(v) => setDrCurveType(v as CurveType)}
            >
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
            <Label className="text-xs">X-Axis Readout</Label>
            <Select value={drXReadout} onValueChange={setDrXReadout}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={WELL_CONC_X}>
                  (use well concentration)
                </SelectItem>
                {candidates.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
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
        <div className="grid grid-cols-3 gap-3">
          <div className="grid gap-1">
            <Label className="text-xs">Hill Slope</Label>
            <Select
              value={drHillConstraint}
              onValueChange={(v) =>
                setDrHillConstraint(v as HillSlopeConstraint)
              }
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
              onValueChange={(v) =>
                setDrNormalizationScope(v as NormalizationScope)
              }
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
            <ParamModeToggle
              mode={drTopMode}
              onChange={setDrTopMode}
              idPrefix="top"
            />
          </div>
          {drTopMode === "lock" && (
            <Input
              type="number"
              placeholder="exact value, e.g. 100"
              value={drTopConstraint}
              onChange={(e) => setDrTopConstraint(e.target.value)}
              className="max-w-xs"
            />
          )}
          {drTopMode === "range" && (
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
            <ParamModeToggle
              mode={drBottomMode}
              onChange={setDrBottomMode}
              idPrefix="bottom"
            />
          </div>
          {drBottomMode === "lock" && (
            <Input
              type="number"
              placeholder="exact value, e.g. 0"
              value={drBottomConstraint}
              onChange={(e) => setDrBottomConstraint(e.target.value)}
              className="max-w-xs"
            />
          )}
          {drBottomMode === "range" && (
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
              <span className="text-xs text-muted-foreground">
                × SD of residuals (CDD default: 3)
              </span>
            </div>
          )}
          {!drOutlierEnabled && (
            <p className="text-xs text-muted-foreground">
              Disabled — fitter will not auto-flag points; manual exclusion
              still works.
            </p>
          )}
        </div>

        {/* CDD-style suggestion banner. */}
        {(() => {
          const suggested = suggestedRangesForY(drYReadout);
          if (!suggested) {
            return (
              <p className="text-xs text-muted-foreground leading-tight">
                Lock and Range are mutually exclusive. Leave both at Free for
                raw-signal readouts; use Range for percent-normalized
                readouts.
              </p>
            );
          }
          return (
            <div className="flex items-start justify-between gap-3 rounded-md border border-dashed bg-muted/40 p-2">
              <p className="text-xs text-muted-foreground leading-tight">
                Suggested for this readout: Top ∈ [{suggested.topMin},{" "}
                {suggested.topMax}], Bottom ∈ [{suggested.bottomMin},{" "}
                {suggested.bottomMax}], Hill ∈ [{suggested.hillMin},{" "}
                {suggested.hillMax}].
              </p>
              <button
                type="button"
                className="shrink-0 text-xs text-primary underline-offset-2 hover:underline"
                onClick={applySuggestedRanges}
              >
                Use suggested
              </button>
            </div>
          );
        })()}
      </div>
    );
  };

  // Tiny segmented control reused by Top and Bottom param blocks.
  function ParamModeToggle({
    mode,
    onChange,
    idPrefix,
  }: {
    mode: "free" | "range" | "lock";
    onChange: (m: "free" | "range" | "lock") => void;
    idPrefix: string;
  }) {
    const options: ("free" | "range" | "lock")[] = ["free", "range", "lock"];
    return (
      <div className="inline-flex rounded-md border" role="radiogroup">
        {options.map((opt) => (
          <button
            key={`${idPrefix}-${opt}`}
            type="button"
            role="radio"
            aria-checked={mode === opt}
            onClick={() => onChange(opt)}
            className={
              "px-2.5 py-1 text-xs capitalize first:rounded-l-md last:rounded-r-md " +
              (mode === opt
                ? "bg-primary text-primary-foreground"
                : "bg-background hover:bg-muted")
            }
          >
            {opt}
          </button>
        ))}
      </div>
    );
  }

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
            <CardDescription>
              Controlled vocabulary terms for this protocol.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {ontologySlots.map((slot) => {
              const currentTerms =
                protocol.ontology_annotations?.[slot.name] ?? [];
              return (
                <div key={slot.id} className="space-y-1">
                  <Label className="text-sm font-medium">
                    {slot.label}
                    {slot.is_required && (
                      <span className="ml-1 text-destructive">*</span>
                    )}
                  </Label>

                  {isDraft ? (
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
                    <p className="text-sm text-muted-foreground">
                      No terms assigned.
                    </p>
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
            <CardDescription>
              Measured values captured for each compound in a run.
            </CardDescription>
          </div>
          {isDraft && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setAddReadoutOpen(true)}
            >
              <Plus className="mr-1 h-4 w-4" />
              Add
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {protocol.readout_definitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No readout definitions yet.
            </p>
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
                    <TableCell className="text-muted-foreground">
                      {idx + 1}
                    </TableCell>
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
                          (
                          {
                            CURVE_TYPE_LABELS[
                              rd.dose_response_config
                                .curve_type as CurveType
                            ]
                          }
                          :{" "}
                          {rd.dose_response_config.x_readout_name ??
                            "well concentration"}{" "}
                          vs {rd.dose_response_config.y_readout_name})
                        </span>
                      )}
                      {rd.pick_list_values &&
                        rd.pick_list_values.length > 0 && (
                          <div className="mt-0.5 flex flex-wrap gap-1">
                            {rd.pick_list_values.map((v) => (
                              <Badge
                                key={v}
                                variant="outline"
                                className="text-[10px]"
                              >
                                {v}
                              </Badge>
                            ))}
                          </div>
                        )}
                    </TableCell>
                    <TableCell>
                      {READOUT_DATA_TYPE_LABELS[
                        rd.data_type as ReadoutDataType
                      ] ?? rd.data_type}
                      {rd.dose_response_config && (
                        <span className="ml-1 text-xs text-muted-foreground">
                          (
                          {
                            CURVE_TYPE_LABELS[
                              rd.dose_response_config
                                .curve_type as CurveType
                            ]
                          }
                          )
                        </span>
                      )}
                    </TableCell>
                    <TableCell>{rd.unit ?? "\u2014"}</TableCell>
                    <TableCell>
                      {READOUT_AGGREGATION_LABELS[
                        rd.aggregation as ReadoutAggregation
                      ] ?? rd.aggregation}
                    </TableCell>
                    <TableCell>
                      {READOUT_NORMALIZATION_LABELS[
                        rd.normalization as ReadoutNormalization
                      ] ?? rd.normalization}
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
                        {isDraft && (
                          <>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => openEditReadout(rd.id)}
                              title="Edit"
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-destructive hover:text-destructive"
                              disabled={
                                protocol.readout_definitions.length <= 1
                              }
                              onClick={() => removeReadoutDef.mutate(rd.id)}
                              title="Delete"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </>
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
            <CardDescription>
              Experimental conditions that vary between runs.
            </CardDescription>
          </div>
          {isDraft && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setAddConditionOpen(true)}
            >
              <Plus className="mr-1 h-4 w-4" />
              Add
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {protocol.condition_definitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No condition definitions yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Data Type</TableHead>
                  <TableHead>Unit</TableHead>
                  {isDraft && <TableHead className="w-10" />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {protocol.condition_definitions.map((cd) => (
                  <TableRow key={cd.id}>
                    <TableCell className="font-medium">{cd.name}</TableCell>
                    <TableCell className="capitalize">
                      {cd.data_type}
                    </TableCell>
                    <TableCell>{cd.unit ?? "\u2014"}</TableCell>
                    {isDraft && (
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
                            onClick={() =>
                              removeConditionDef.mutate(cd.id)
                            }
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
              Plate templates for positive/negative controls per plate format.
              Required for runs that use control-based normalization (e.g.,
              % Inhibition).
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
          {protocol.control_layouts &&
          Object.keys(protocol.control_layouts).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(protocol.control_layouts).map(
                ([format, templateId]) => {
                  const tmpl = plateTemplates?.find(
                    (pt) => pt.id === templateId,
                  );
                  return (
                    <div
                      key={format}
                      className="flex items-center justify-between rounded-md border px-3 py-2"
                    >
                      <span className="text-sm">
                        {PLATE_FORMAT_LABELS[format as PlateFormat] ??
                          `${format}-well`}{" "}
                        &rarr;{" "}
                        <span className="font-medium">
                          {tmpl?.name ?? templateId}
                        </span>
                      </span>
                      {isDraft && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() =>
                            removeControlLayout.mutate(format)
                          }
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  );
                },
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No control layouts configured.
            </p>
          )}

          {/* Add form (draft only) */}
          {isDraft && (
            <>
              {plateTemplates && plateTemplates.length === 0 ? (
                <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                  No plate templates exist in this workspace yet. Create one
                  first — define which wells are positive/negative controls
                  for each plate format.
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
                <div className="flex items-end gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Format</Label>
                    <Select
                      value={clFormat}
                      onValueChange={(v) => {
                        setClFormat(v);
                        setClTemplateId("");
                      }}
                    >
                      <SelectTrigger className="w-[120px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(PLATE_FORMAT_LABELS).map(
                          ([val, label]) => (
                            <SelectItem key={val} value={val}>
                              {label}
                            </SelectItem>
                          ),
                        )}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Template</Label>
                    <Select
                      value={clTemplateId}
                      onValueChange={setClTemplateId}
                    >
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
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* ── 4b. Control Convention ──────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Control Convention</CardTitle>
          <CardDescription>
            Tells the calculation engine which control well produces high raw
            signal. Drives % Inhibition / % Activation / % Control / Z-Score
            formula dispatch and the heatmap legend. Editable after publish —
            re-run Recompute on each run after changing.
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
              <span className="pb-2 text-xs text-muted-foreground">
                Saving…
              </span>
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
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Readout Definition</DialogTitle>
            <DialogDescription>
              Define a new measured value for this protocol.
            </DialogDescription>
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
                  &lsquo;{rdName.trim()}&rsquo; is a reserved well-metadata name
                  and cannot be used as a readout. The well&apos;s concentration,
                  batch, and compound are tracked on the well itself, not as
                  readouts.
                </p>
              )}
            </div>
            <div className="space-y-1">
              <Label>Data Type</Label>
              <Select value={rdDataType} onValueChange={setRdDataType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_DATA_TYPE_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={rdUnit}
                onChange={(e) => setRdUnit(e.target.value)}
                placeholder="e.g. nM, %, \u00B5M"
              />
            </div>
            <div className="space-y-1">
              <Label>Aggregation</Label>
              <Select
                value={rdAggregation}
                onValueChange={setRdAggregation}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_AGGREGATION_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Normalization</Label>
              <Select
                value={rdNormalization}
                onValueChange={setRdNormalization}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_NORMALIZATION_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            {renderDoseResponseFields(null)}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setAddReadoutOpen(false)}
            >
              Cancel
            </Button>
            <Button
              disabled={
                !rdName.trim() ||
                isReservedReadoutName(rdName) ||
                addReadoutDef.isPending ||
                (rdDataType === "dose_response" && !drYReadout)
              }
              onClick={() => {
                addReadoutDef.mutate(
                  {
                    name: rdName.trim(),
                    data_type: rdDataType,
                    unit: rdUnit.trim() || undefined,
                    aggregation: rdAggregation,
                    normalization: rdNormalization,
                    dose_response_config: buildDoseResponseConfig(),
                  },
                  {
                    onSuccess: () => {
                      setRdName("");
                      setRdDataType("numeric");
                      setRdUnit("");
                      setRdAggregation("none");
                      setRdNormalization("none");
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
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Readout Definition</DialogTitle>
            <DialogDescription>
              Update fields on this readout. Only available while the protocol
              is in draft.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input
                value={rdName}
                onChange={(e) => setRdName(e.target.value)}
              />
              {isReservedReadoutName(rdName) && (
                <p className="text-xs text-destructive">
                  &lsquo;{rdName.trim()}&rsquo; is a reserved well-metadata name
                  and cannot be used as a readout.
                </p>
              )}
            </div>
            <div className="space-y-1">
              <Label>Data Type</Label>
              <Select value={rdDataType} onValueChange={setRdDataType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_DATA_TYPE_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={rdUnit}
                onChange={(e) => setRdUnit(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label>Aggregation</Label>
              <Select value={rdAggregation} onValueChange={setRdAggregation}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_AGGREGATION_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Normalization</Label>
              <Select
                value={rdNormalization}
                onValueChange={setRdNormalization}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_NORMALIZATION_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            {renderDoseResponseFields(editingReadoutId)}
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
                (rdDataType === "dose_response" && !drYReadout)
              }
              onClick={() => {
                if (!editingReadoutId) return;
                updateReadoutDef.mutate(
                  {
                    definitionId: editingReadoutId,
                    data: {
                      name: rdName.trim(),
                      data_type: rdDataType,
                      unit: rdUnit.trim() || null,
                      aggregation: rdAggregation,
                      normalization: rdNormalization,
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
            <Button
              variant="outline"
              onClick={() => setAddConditionOpen(false)}
            >
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
              Update fields on this condition. Only available while the
              protocol is in draft.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input
                value={cdName}
                onChange={(e) => setCdName(e.target.value)}
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
              />
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
            ? protocol.readout_definitions.find(
                (rd) => rd.id === viewingReadoutId,
              ) ?? null
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
