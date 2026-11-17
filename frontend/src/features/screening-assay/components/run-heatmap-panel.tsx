"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import {
  CHART_COLORS,
  fullEffectControl,
  isActivation,
  wellTypeColors,
} from "@/shared/lib/chart-colors";
import { showError, showSuccess, showWarning } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import { Maximize2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { useFlagOutliers } from "../hooks/use-flag-outliers";
import { apiReason } from "../hooks/use-instrument-import-wizard";
import { usePlateMap } from "../hooks/use-plate-setup";
import { useProtocol } from "../hooks/use-protocols";
import { useReadoutDataByRun } from "../hooks/use-readout-data";
import {
  type Palette,
  type PlateColorBy,
  type ScaleKind,
  buildPlateScale,
  compoundColorsForPlates,
  formatPlateValue,
} from "../lib/plate-map-values";
import { hasComputedLayer } from "../lib/readout-data-pivot";
import { replicateWells } from "../lib/replicate-wells";
import {
  type PlateData,
  type PlateMapWell,
  READOUT_NORMALIZATION_LABELS,
  type ReadoutNormalization,
  type Run,
} from "../types";
import { PlateCompoundsList } from "./plate-compounds-list";
import { PlateQualitySummary } from "./plate-quality-summary";
import { ColorScaleLegend, PlateValueHeatmap } from "./plate-value-heatmap";
import { PlateWellDetails } from "./plate-well-details";
import { PlateWellMenu } from "./plate-well-menu";
import { RunPlateLink } from "./run-plate-link";

const EMPTY_VALUES = new Map<string, number>();
const COLOR_BY_OPTIONS: { value: PlateColorBy; label: string }[] = [
  { value: "response", label: "Response" },
  { value: "compound", label: "Compound" },
  { value: "concentration", label: "Concentration" },
  { value: "well-type", label: "Well type" },
];
const CONTROL_TYPES = ["negative_control", "positive_control", "blank", "reference"] as const;

interface RunHeatmapPanelProps {
  run: Run;
  colorBy?: PlateColorBy;
  onColorByChange?: (colorBy: PlateColorBy) => void;
  onOpenResults?: () => void;
}

/** All plates share a readout, colour encoding, and (by default) numeric scale. */
export function RunHeatmapPanel({
  run,
  colorBy,
  onColorByChange,
  onOpenResults,
}: RunHeatmapPanelProps) {
  const { data: plateMap, isLoading: plateMapLoading } = usePlateMap(run.id);
  const {
    data: readoutData,
    isLoading: readoutLoading,
    error: readoutError,
  } = useReadoutDataByRun(run.id);
  const { data: protocol, isLoading: protocolLoading } = useProtocol(run.protocol_id);
  const { data: curves } = useDoseResponseByRun(run.id);
  const canEdit = useCanEdit();
  const flag = useFlagOutliers();
  const canFlag =
    canEdit && !run.is_locked && ["draft", "in_progress", "completed"].includes(run.status);

  const [localColorBy, setLocalColorBy] = useState<PlateColorBy>("response");
  const [readoutId, setReadoutId] = useState<string | null>(null);
  const [layer, setLayer] = useState<"raw" | "normalized">("normalized");
  const [scaleKind, setScaleKind] = useState<ScaleKind>("linear");
  const [scaleScope, setScaleScope] = useState<"run" | "plate">("run");
  const [compactChoice, setCompactChoice] = useState<boolean | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selection, setSelection] = useState<{ plateId: string; wellId: string } | null>(null);
  const [highlight, setHighlight] = useState<{
    wellId: string;
    kind: "compound" | "replicates";
  } | null>(null);
  const [customFlag, setCustomFlag] = useState<{
    plate: PlateData;
    well: PlateMapWell;
    outlier: boolean;
  } | null>(null);
  const [customReason, setCustomReason] = useState("");

  const plates = plateMap?.plates ?? [];
  const compact = compactChoice ?? plates.length > 6;
  const doseUnit = plateMap?.dose_unit ?? "uM";
  const highlightSource = plates
    .flatMap((plate) => plate.wells)
    .find((well) => well.well_id === highlight?.wellId);
  const highlightedWells = highlightSource
    ? highlight?.kind === "replicates"
      ? replicateWells(plates, highlightSource).map((item) => item.well)
      : plates
          .flatMap((plate) => plate.wells)
          .filter(
            (well) =>
              !!highlightSource.molecule_id && well.molecule_id === highlightSource.molecule_id,
          )
    : [];
  const highlightedIds = new Set(highlightedWells.map((well) => well.well_id));
  const flagUnavailableReason = canFlag
    ? null
    : !canEdit
      ? "Read-only access — outlier flags cannot be changed."
      : run.is_locked
        ? "This run is locked — outlier flags cannot be changed."
        : `Outlier changes are unavailable for ${run.status.replace(/_/g, " ")} runs.`;
  const numericReadouts = useMemo(
    () =>
      [...(protocol?.readout_definitions ?? [])]
        .filter((definition) => definition.data_type === "numeric")
        .sort((a, b) => a.display_order - b.display_order),
    [protocol],
  );
  const selectedDef =
    numericReadouts.find((definition) => definition.id === readoutId) ?? numericReadouts[0];
  const requestedColorBy = colorBy ?? localColorBy;
  const activeColorBy =
    requestedColorBy === "response" && !selectedDef ? "well-type" : requestedColorBy;
  const isDose = activeColorBy === "concentration";
  const isNumeric = activeColorBy === "response" || isDose;
  const layerAvailable = !!selectedDef && hasComputedLayer(selectedDef);
  const wantsComputed = layerAvailable && layer === "normalized";
  const normalization = selectedDef?.normalizations?.find((value) => value !== "none");
  const computedUnit = normalization
    ? (READOUT_NORMALIZATION_LABELS[normalization as ReadoutNormalization] ?? normalization)
    : "Computed response";
  const rawUnit = selectedDef?.unit ?? null;
  const responseLabel = wantsComputed ? computedUnit : `Raw${rawUnit ? ` (${rawUnit})` : ""}`;
  const valueUnit = isDose
    ? doseUnit
    : wantsComputed && normalization?.startsWith("percent_")
      ? "%"
      : rawUnit;
  const activation = isActivation(selectedDef?.normalizations ?? []);
  const fullIsPositive =
    fullEffectControl(protocol?.pos_control_signal, activation) === "positive_control";
  const colors = wellTypeColors(protocol?.pos_control_signal, activation);

  const { rawValues, computedValues, outliers } = useMemo(() => {
    const rawValues = new Map<string, number>();
    const computedValues = new Map<string, number>();
    const outliers = new Set<string>();
    for (const row of readoutData ?? []) {
      if (!row.well_id) continue;
      if (row.is_outlier && !row.is_computed) outliers.add(row.well_id);
      if (
        row.readout_definition_id !== selectedDef?.id ||
        row.value_numeric == null ||
        !Number.isFinite(row.value_numeric)
      )
        continue;
      (row.is_computed ? computedValues : rawValues).set(row.well_id, row.value_numeric);
    }
    return { rawValues, computedValues, outliers };
  }, [readoutData, selectedDef?.id]);
  const responseValues = wantsComputed ? computedValues : rawValues;
  const concentrations = useMemo(
    () =>
      new Map(
        plates.flatMap((plate) =>
          plate.wells
            .filter((well) => well.dose != null && Number.isFinite(well.dose))
            .map((well) => [well.well_id, well.dose as number] as const),
        ),
      ),
    [plates],
  );
  const numericValues = isDose ? concentrations : responseValues;
  const compoundColors = useMemo(() => compoundColorsForPlates(plates), [plates]);
  const categoricalColors = useMemo(() => {
    const result = new Map<string, string>();
    if (activeColorBy !== "compound" && activeColorBy !== "well-type") return result;
    for (const plate of plates) {
      for (const well of plate.wells) {
        if (activeColorBy === "well-type")
          result.set(well.well_id, colors[well.well_type] ?? CHART_COLORS.neutral);
        else if (well.well_type === "sample")
          result.set(
            well.well_id,
            (well.molecule_id && compoundColors.get(well.molecule_id)) || CHART_COLORS.primary,
          );
      }
    }
    return result;
  }, [plates, activeColorBy, compoundColors, colors]);
  const palette: Palette = isDose && scaleKind === "linear" ? "sequential" : "diverging";
  const scaleOptions = {
    values: numericValues,
    outliers,
    kind: scaleKind,
    concentration: isDose,
    normalization:
      wantsComputed && !isDose ? (normalization as ReadoutNormalization | undefined) : undefined,
    fullIsPositive,
    unit: valueUnit,
  };
  const sharedScale = buildPlateScale({ ...scaleOptions, plates });
  const scaleFor = (plate: PlateData) =>
    scaleScope === "run" ? sharedScale : buildPlateScale({ ...scaleOptions, plates: [plate] });
  const controlTypes = CONTROL_TYPES.filter((type) =>
    plates.some((plate) => plate.wells.some((well) => well.well_type === type)),
  );

  function changeColorBy(value: string) {
    const next = value as PlateColorBy;
    setLocalColorBy(next);
    onColorByChange?.(next);
  }
  function onFlag(well: PlateMapWell, outlier: boolean, reason: string | null) {
    if (!canFlag || flag.isPending || (run.status === "completed" && !reason?.trim())) return;
    flag.mutate(
      { runId: run.id, well_ids: [well.well_id], outlier, reason },
      {
        onSuccess: (result) => {
          setCustomFlag(null);
          setCustomReason("");
          showSuccess(
            outlier
              ? `${well.position_label} flagged as an outlier`
              : `${well.position_label} is no longer an outlier`,
          );
          if (result.compute_warning) showWarning(result.compute_warning);
        },
        onError: (error) => showError(apiReason(error)),
      },
    );
  }
  const renderMap = (plate: PlateData, preview = false) => (
    <PlateValueHeatmap
      plate={plate}
      valueByWellId={isNumeric ? numericValues : EMPTY_VALUES}
      colorByWellId={isNumeric ? undefined : categoricalColors}
      rawByWellId={rawValues}
      computedByWellId={computedValues}
      scale={scaleFor(plate)}
      palette={palette}
      rawUnit={rawUnit}
      computedUnit={computedUnit}
      doseUnit={doseUnit}
      outlierWellIds={outliers}
      colors={colors}
      preview={preview}
      onSelectWell={(well) => setSelection({ plateId: plate.plate_id, wellId: well.well_id })}
      selectedWellId={selection?.plateId === plate.plate_id ? selection.wellId : undefined}
      highlightedWellIds={highlightedIds}
      renderWellMenu={(well) => (
        <PlateWellMenu
          plate={plate}
          well={well}
          plates={plates}
          excluded={outliers.has(well.well_id)}
          rawValue={rawValues.get(well.well_id)}
          computedValue={computedValues.get(well.well_id)}
          rawLabel={`${selectedDef?.name ?? "Response"} · Raw${rawUnit ? ` (${rawUnit})` : ""}`}
          computedLabel={computedUnit}
          doseUnit={doseUnit}
          canFlag={canFlag}
          flagPending={flag.isPending}
          flagUnavailableReason={flagUnavailableReason}
          onInspect={() => setSelection({ plateId: plate.plate_id, wellId: well.well_id })}
          onFlag={(outlier, reason) => onFlag(well, outlier, reason)}
          onCustomReason={(outlier) => {
            setCustomReason("");
            setCustomFlag({ plate, well, outlier });
          }}
          onHighlight={(kind) => setHighlight({ wellId: well.well_id, kind })}
        />
      )}
    />
  );
  const legend = (plate?: PlateData) => (
    <ColorScaleLegend
      scale={plate ? scaleFor(plate) : sharedScale}
      palette={palette}
      unit={valueUnit}
      controlTypesPresent={controlTypes}
      colors={colors}
      hasOutliers={outliers.size > 0}
    />
  );
  const quality = (plate: PlateData) => (
    <PlateQualitySummary
      run={run}
      plate={plate}
      readoutId={selectedDef?.id}
      layer={wantsComputed && normalization ? normalization : "raw"}
      values={responseValues}
      outliers={outliers}
      showCoverage={activeColorBy === "response"}
      valueLabel={responseLabel}
    />
  );
  const expanded = plates.find((plate) => plate.plate_id === expandedId);
  const selectedPlate = plates.find((plate) => plate.plate_id === selection?.plateId);
  const selectedWell = selectedPlate?.wells.find((well) => well.well_id === selection?.wellId);

  if (plateMapLoading || readoutLoading || protocolLoading)
    return <p className="py-12 text-center text-sm text-muted-foreground">Loading plates…</p>;
  if (!plates.length)
    return (
      <div className="space-y-3 rounded-lg border border-dashed py-12 text-center text-sm text-muted-foreground">
        <p>No plates have been populated for this run.</p>
        {canEdit && !run.is_locked && onOpenResults && (
          <Button size="sm" variant="outline" onClick={onOpenResults}>
            Import data in Results
          </Button>
        )}
      </div>
    );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3 rounded-lg border bg-muted/15 p-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Colour by</span>
          <Select value={activeColorBy} onValueChange={changeColorBy}>
            <SelectTrigger aria-label="Colour by" className="h-9 w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {COLOR_BY_OPTIONS.map((option) => (
                <SelectItem
                  key={option.value}
                  value={option.value}
                  disabled={option.value === "response" && !selectedDef}
                >
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {numericReadouts.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">Readout</span>
            <Select value={selectedDef?.id} onValueChange={setReadoutId}>
              <SelectTrigger aria-label="Readout" className="h-9 w-56 max-w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {numericReadouts.map((definition) => (
                  <SelectItem key={definition.id} value={definition.id}>
                    {definition.name}
                    {definition.unit ? ` (${definition.unit})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {activeColorBy === "response" && layerAvailable && (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">Value</span>
            <div className="inline-flex h-9 items-center gap-0.5 rounded-md border bg-background p-1">
              <Button
                type="button"
                size="sm"
                variant={!wantsComputed ? "secondary" : "ghost"}
                aria-pressed={!wantsComputed}
                className="h-7 px-2.5"
                onClick={() => setLayer("raw")}
              >
                Raw
              </Button>
              <Button
                type="button"
                size="sm"
                variant={wantsComputed ? "secondary" : "ghost"}
                aria-pressed={wantsComputed}
                className="h-7 px-2.5"
                onClick={() => setLayer("normalized")}
              >
                {computedUnit}
              </Button>
            </div>
          </div>
        )}
        {isNumeric && (
          <>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">Scale</span>
              <div className="inline-flex h-9 items-center gap-0.5 rounded-md border bg-background p-1">
                <Button
                  type="button"
                  size="sm"
                  variant={scaleKind === "linear" ? "secondary" : "ghost"}
                  aria-pressed={scaleKind === "linear"}
                  className="h-7 px-2.5"
                  onClick={() => setScaleKind("linear")}
                >
                  Linear
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={scaleKind === "zscore" ? "secondary" : "ghost"}
                  aria-pressed={scaleKind === "zscore"}
                  className="h-7 px-2.5"
                  onClick={() => setScaleKind("zscore")}
                >
                  Z-Score
                </Button>
              </div>
            </div>
            {plates.length > 1 && (
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-muted-foreground">Range</span>
                <Select
                  value={scaleScope}
                  onValueChange={(value) => setScaleScope(value as "run" | "plate")}
                >
                  <SelectTrigger aria-label="Scale range" className="h-9 w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="run">Shared across plates</SelectItem>
                    <SelectItem value="plate">Per plate</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </>
        )}
        <div className="ml-auto flex h-9 items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {plates.length} {plates.length === 1 ? "plate" : "plates"}
          </span>
          {plates.length > 1 && (
            <Button
              size="sm"
              variant="outline"
              aria-pressed={compact}
              onClick={() => setCompactChoice(!compact)}
            >
              {compact ? "Detailed maps" : "Compact maps"}
            </Button>
          )}
        </div>
      </div>

      {readoutError && (
        <p
          role="alert"
          className="rounded-md border border-destructive/30 p-3 text-sm text-destructive"
        >
          Response values could not be loaded. Reload to try again; compound and well-type views
          remain available.
        </p>
      )}
      {isNumeric ? (
        scaleScope === "run" ? (
          <section aria-label="Shared colour scale" className="space-y-2 rounded-lg border p-3">
            <p className="text-xs font-medium">
              {isDose
                ? `Concentration (${doseUnit})`
                : `${selectedDef?.name ?? "Response"} · ${responseLabel}`}
              <span className="ml-2 font-normal text-muted-foreground">
                {plates.length > 1
                  ? "Same colours mean the same values across plates"
                  : "Click a well to inspect; right-click for actions"}
              </span>
            </p>
            {legend()}
          </section>
        ) : (
          <p className="rounded-md border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
            Per-plate scaling is on. Each map has its own scale; colours are not directly comparable
            between plates.
          </p>
        )
      ) : (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          <span>
            {activeColorBy === "compound"
              ? "The same compound has the same colour across every plate"
              : "Wells are coloured by their role"}
          </span>
          {activeColorBy === "well-type" && (
            <span className="flex items-center gap-1.5">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{ background: colors.sample ?? CHART_COLORS.primary }}
              />
              Sample
            </span>
          )}
          {controlTypes.map((type) => (
            <span key={type} className="flex items-center gap-1.5">
              <span
                className="h-2.5 w-2.5 rounded-sm border-2"
                style={{
                  borderColor: colors[type],
                  background: activeColorBy === "well-type" ? colors[type] : "transparent",
                }}
              />
              {type.replace(/_/g, " ")}
            </span>
          ))}
          {outliers.size > 0 && <span>✕ Excluded from QC</span>}
        </div>
      )}

      {highlightSource && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-sm">
          <span>
            {highlight?.kind === "replicates" ? "Replicates" : "Same compound"} ·{" "}
            {highlightSource.registration_number ??
              highlightSource.batch_number ??
              highlightSource.position_label}
            {highlight?.kind === "replicates" && highlightSource.dose != null
              ? ` · ${formatPlateValue(highlightSource.dose)} ${doseUnit}`
              : ""}{" "}
            · {highlightedIds.size} wells
          </span>
          <Button className="ml-auto" variant="ghost" size="sm" onClick={() => setHighlight(null)}>
            Clear highlights
          </Button>
        </div>
      )}
      <div
        className={cn(
          "grid items-start gap-4",
          compact
            ? "[grid-template-columns:repeat(auto-fit,minmax(min(100%,20rem),1fr))]"
            : "[grid-template-columns:repeat(auto-fit,minmax(min(100%,32rem),1fr))]",
        )}
      >
        {plates.map((plate) => (
          <article
            key={plate.plate_id}
            aria-label={`Plate ${plate.plate_number}`}
            className="min-w-0 space-y-3 rounded-lg border bg-card p-4"
          >
            <header className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold">Plate {plate.plate_number}</h3>
                <RunPlateLink runId={run.id} plate={plate} readOnly={run.is_locked || !canEdit} />
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 gap-1.5 px-2"
                aria-label={`Expand Plate ${plate.plate_number}`}
                onClick={() => setExpandedId(plate.plate_id)}
              >
                <Maximize2 className="h-3.5 w-3.5" />
                Expand
              </Button>
            </header>
            {quality(plate)}
            {isNumeric && scaleScope === "plate" && legend(plate)}
            {compact ? (
              <button
                type="button"
                className="block w-full rounded-md text-left focus-visible:outline-2 focus-visible:outline-primary"
                aria-label={`Inspect Plate ${plate.plate_number}`}
                onClick={() => setExpandedId(plate.plate_id)}
              >
                {renderMap(plate, true)}
              </button>
            ) : (
              <div className="flex justify-center [&>div]:min-w-0">{renderMap(plate)}</div>
            )}
            {!plate.wells.length && canEdit && !run.is_locked && onOpenResults && (
              <Button size="sm" variant="outline" onClick={onOpenResults}>
                Import data in Results
              </Button>
            )}
            <PlateCompoundsList plate={plate} colors={compoundColors} doseUnit={doseUnit} />
          </article>
        ))}
      </div>
      {curves && curves.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {curves.length} fitted {curves.length === 1 ? "curve" : "curves"} · available in Results →
          Dose-response and when selecting a sample well.
        </p>
      )}

      <Dialog
        open={!!expanded}
        onOpenChange={(open) => {
          if (!open) setExpandedId(null);
        }}
      >
        {expanded && (
          <DialogContent className="max-h-[90dvh] w-[calc(100vw-2rem)] overflow-y-auto sm:max-w-4xl">
            <DialogHeader>
              <DialogTitle>Plate {expanded.plate_number}</DialogTitle>
              <DialogDescription>
                {COLOR_BY_OPTIONS.find((option) => option.value === activeColorBy)?.label} view ·
                using the overview’s readout and scale
              </DialogDescription>
            </DialogHeader>
            {quality(expanded)}
            {isNumeric && legend(expanded)}
            <div className="flex justify-center [&>div]:min-w-0">{renderMap(expanded)}</div>
            <PlateCompoundsList plate={expanded} colors={compoundColors} doseUnit={doseUnit} />
          </DialogContent>
        )}
      </Dialog>
      {selectedPlate && selectedWell && (
        <PlateWellDetails
          key={selectedWell.well_id}
          plate={selectedPlate}
          well={selectedWell}
          plates={plates}
          rawValues={rawValues}
          computedValues={computedValues}
          responseValues={responseValues}
          responseLabel={responseLabel}
          rawUnit={rawUnit}
          computedUnit={computedUnit}
          doseUnit={doseUnit}
          outliers={outliers}
          curves={curves ?? []}
          canFlag={canFlag}
          flagPending={flag.isPending}
          reasonRequired={run.status === "completed"}
          onFlag={onFlag}
          onClose={() => setSelection(null)}
        />
      )}
      <Dialog
        open={!!customFlag}
        onOpenChange={(open) => {
          if (!open) {
            setCustomFlag(null);
            setCustomReason("");
          }
        }}
      >
        {customFlag && (
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>
                {customFlag.outlier ? "Exclude from QC" : "Restore to QC"} · Plate{" "}
                {customFlag.plate.plate_number} · {customFlag.well.position_label}
              </DialogTitle>
              <DialogDescription>
                {customFlag.outlier
                  ? "Leaves plate QC and normalization anchors; the measurement is retained. The run is recalculated."
                  : "Returns the well to plate QC and normalization anchors. The run is recalculated."}
              </DialogDescription>
            </DialogHeader>
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                if (customReason.trim())
                  onFlag(customFlag.well, customFlag.outlier, customReason.trim());
              }}
            >
              <Input
                aria-label="Reason"
                placeholder="Reason for this QC decision"
                required
                maxLength={500}
                value={customReason}
                onChange={(event) => setCustomReason(event.target.value)}
              />
              <DialogFooter>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setCustomFlag(null)}
                  disabled={flag.isPending}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="outline"
                  disabled={!canFlag || flag.isPending || !customReason.trim()}
                >
                  {flag.isPending
                    ? "Updating…"
                    : customFlag.outlier
                      ? "Exclude well"
                      : "Restore well"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}
