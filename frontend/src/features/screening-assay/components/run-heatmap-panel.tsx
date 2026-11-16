"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { fullEffectControl, isActivation, wellTypeColors } from "@/shared/lib/chart-colors";
import { showError, showSuccess, showWarning } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import { useMemo, useState } from "react";
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { useFlagOutliers } from "../hooks/use-flag-outliers";
import { apiReason } from "../hooks/use-instrument-import-wizard";
import { usePlateMap } from "../hooks/use-plate-setup";
import { useProtocol } from "../hooks/use-protocols";
import { useReadoutDataByRun } from "../hooks/use-readout-data";
import { classifyZPrime, readPerPlateQc } from "../lib/qc-metrics";
import { hasComputedLayer } from "../lib/readout-data-pivot";
import {
  type PlateData,
  type PlateMapWell,
  READOUT_NORMALIZATION_LABELS,
  type ReadoutDefinition,
  type ReadoutNormalization,
  type Run,
} from "../types";
import {
  ColorScaleLegend,
  type Palette,
  PlateValueHeatmap,
  type ScaleKind,
  type ValueScale,
} from "./plate-value-heatmap";
import { RunPlateLink } from "./run-plate-link";
import { Z_PRIME_BADGE } from "./z-prime-badge";

type ValueLayer = "raw" | "normalized";

/** Sentinel id for the synthetic "well concentration" option. Lives on
 *  `well.dose`, not in `readout_data` — branched everywhere the panel
 *  reads a value. */
const DOSE_OPTION_ID = "__well_dose__";

function computedUnitLabel(normalization: ReadoutNormalization): string {
  if (normalization === "none") return "Computed";
  return READOUT_NORMALIZATION_LABELS[normalization];
}

/** A % layer's fixed anchors: [no effect (white), full effect (red)]. */
const FIXED_PERCENT: Partial<Record<ReadoutNormalization, [number, number]>> = {
  percent_inhibition: [0, 100],
  percent_activation: [0, 100],
  percent_control: [100, 0],
};

const mean = (vs: number[]) =>
  vs.length > 0 ? vs.reduce((a, b) => a + b, 0) / vs.length : undefined;

const fmt = (v: number) => String(Number(v.toPrecision(3)));

/** ``none`` at white and ``full`` red: the diverging palette puts ``low`` at t=0.25
 *  and ``high`` at 0.75, so ``low`` mirrors ``full`` around ``none``. Beyond full
 *  darkens toward black, below none toward blue. */
function anchored(
  none: number,
  full: number,
  noneText: string,
  fullText: string,
  negMean: number | undefined,
  posMean: number | undefined,
): ValueScale {
  return {
    low: 2 * none - full,
    high: full,
    kind: "linear",
    negMean,
    posMean,
    marks: [
      { value: none, text: noneText },
      { value: full, text: fullText },
    ],
  };
}

interface RunHeatmapPanelProps {
  run: Run;
}

export function RunHeatmapPanel({ run }: RunHeatmapPanelProps) {
  const { data: plateMap, isLoading: plateMapLoading } = usePlateMap(run.id);
  const { data: readoutData, isLoading: readoutLoading } = useReadoutDataByRun(run.id);
  const { data: protocol } = useProtocol(run.protocol_id);
  const { data: curves } = useDoseResponseByRun(run.id);
  const canEdit = useCanEdit();
  const flag = useFlagOutliers();
  // Outlier flags change only on a run neither locked nor approved (the API refuses too).
  const canFlag = canEdit && !run.is_locked && run.status !== "approved";

  const numericReadouts = useMemo<ReadoutDefinition[]>(() => {
    if (!protocol) return [];
    return [...protocol.readout_definitions]
      .filter((d) => d.data_type === "numeric")
      .sort((a, b) => a.display_order - b.display_order);
  }, [protocol]);

  const [readoutId, setReadoutId] = useState<string | null>(null);
  const [layer, setLayer] = useState<ValueLayer>("normalized");
  const [scaleKind, setScaleKind] = useState<ScaleKind>("linear");

  const plates = plateMap?.plates ?? [];
  const doseUnit = plateMap?.dose_unit ?? "uM";
  const perPlateQc = readPerPlateQc(run.qc_metrics);

  // Pick a sane default once readouts load. Falls back to the dose option
  // when the protocol declares no numeric readouts so the dropdown is
  // never empty for a freshly-imported run.
  const effectiveReadoutId = readoutId ?? numericReadouts[0]?.id ?? DOSE_OPTION_ID;
  const isDose = effectiveReadoutId === DOSE_OPTION_ID;
  const selectedDef = isDose ? undefined : numericReadouts.find((d) => d.id === effectiveReadoutId);
  const layerAvailable = !isDose && selectedDef ? hasComputedLayer(selectedDef) : false;
  const effectiveLayer: ValueLayer = layerAvailable ? layer : "raw";

  const wantsComputed = effectiveLayer === "normalized" && layerAvailable;
  const normalization = selectedDef?.normalizations?.find((n) => n !== "none");
  const rawUnit = isDose ? doseUnit : (selectedDef?.unit ?? null);
  // Controls by effect under the protocol's convention: the full-effect one red.
  const activation = isActivation(selectedDef?.normalizations ?? []);
  const fullIsPositive =
    fullEffectControl(protocol?.pos_control_signal, activation) === "positive_control";
  const colors = wellTypeColors(protocol?.pos_control_signal, activation);

  // Per-well value lookups. For the readout case we split by is_computed so
  // the tooltip can show both layers. For the dose case the dose value
  // already shows in the tooltip's existing "Dose" line, so the secondary
  // raw/computed lines stay empty.
  const { activeByWellId, rawByWellId, computedByWellId } = useMemo(() => {
    const active = new Map<string, number>();
    const raw = new Map<string, number>();
    const computed = new Map<string, number>();

    if (isDose) {
      for (const plate of plates) {
        for (const w of plate.wells) {
          if (w.dose != null) active.set(w.well_id, w.dose);
        }
      }
      return { activeByWellId: active, rawByWellId: raw, computedByWellId: computed };
    }

    if (!readoutData || !effectiveReadoutId) {
      return { activeByWellId: active, rawByWellId: raw, computedByWellId: computed };
    }
    for (const r of readoutData) {
      if (r.readout_definition_id !== effectiveReadoutId) continue;
      if (r.well_id == null || r.value_numeric == null) continue;
      if (r.is_computed) computed.set(r.well_id, r.value_numeric);
      else raw.set(r.well_id, r.value_numeric);
    }
    const source = wantsComputed ? computed : raw;
    for (const [wellId, v] of source) active.set(wellId, v);
    return { activeByWellId: active, rawByWellId: raw, computedByWellId: computed };
  }, [readoutData, effectiveReadoutId, wantsComputed, isDose, plates]);

  // A well is an outlier when its raw readouts are flagged (they are flagged together).
  const outlierWellIds = useMemo(() => {
    const ids = new Set<string>();
    for (const r of readoutData ?? []) {
      if (r.is_outlier && !r.is_computed && r.well_id != null) ids.add(r.well_id);
    }
    return ids;
  }, [readoutData]);

  function onFlag(well: PlateMapWell, outlier: boolean, reason: string | null) {
    flag.mutate(
      { runId: run.id, well_ids: [well.well_id], outlier, reason },
      {
        onSuccess: (out) => {
          showSuccess(
            outlier
              ? `${well.position_label} flagged as an outlier`
              : `${well.position_label} is no longer an outlier`,
          );
          if (out.compute_warning) showWarning(out.compute_warning);
        },
        onError: (e) => showError(apiReason(e)),
      },
    );
  }

  /** Per-plate scale.
   *
   *  Z-score: μ ± 2σ across every well with a value on this plate. σ
   *  computed from samples *and* controls combined; otherwise the
   *  high-leverage control wells dominate the gradient and crush the
   *  sample variance.
   *
   *  Linear (readouts), the platform's scale: a % layer on its fixed
   *  scale (0 % white, 100 % red); raw and z-score anchored on the plate's
   *  control means; otherwise min/max of samples.
   *
   *  Linear (dose): no control anchoring (NEG/POS doses aren't meaningful
   *  reference points). min/max across every well with a dose. */
  function buildScale(plate: PlateData): ValueScale {
    const allValues: number[] = [];
    for (const w of plate.wells) {
      const v = activeByWellId.get(w.well_id);
      if (v != null) allValues.push(v);
    }

    if (scaleKind === "zscore") {
      if (allValues.length < 2) {
        return {
          low: 0,
          high: 1,
          kind: "zscore",
          zMean: 0,
          zStd: 0,
        };
      }
      const mu = mean(allValues) as number;
      const variance = allValues.reduce((a, b) => a + (b - mu) ** 2, 0) / (allValues.length - 1);
      const std = Math.sqrt(variance);
      // Symmetric ±2σ window. Outliers fall into the dark tails.
      // If σ collapses to 0 (all values identical) widen to ±1 so the
      // legend still renders without divide-by-zero downstream.
      const halfSpan = std > 0 ? 2 * std : 1;
      return {
        low: mu - halfSpan,
        high: mu + halfSpan,
        kind: "zscore",
        zMean: mu,
        zStd: std,
      };
    }

    if (isDose) {
      if (allValues.length === 0) {
        return { low: 0, high: 1, kind: "linear" };
      }
      const lo = Math.min(...allValues);
      const hi = Math.max(...allValues);
      return {
        low: lo,
        high: hi === lo ? lo + 1 : hi,
        kind: "linear",
      };
    }

    const negValues: number[] = [];
    const posValues: number[] = [];
    const sampleValues: number[] = [];
    for (const w of plate.wells) {
      const v = activeByWellId.get(w.well_id);
      // An outlier is no anchor, as in the run's plate QC.
      if (v == null || outlierWellIds.has(w.well_id)) continue;
      if (w.well_type === "negative_control") negValues.push(v);
      else if (w.well_type === "positive_control") posValues.push(v);
      else if (w.well_type === "sample") sampleValues.push(v);
    }
    const negMean = mean(negValues);
    const posMean = mean(posValues);

    // The platform's scale: a % layer on its fixed scale (no effect at white, full
    // effect red); raw and z-score anchored on this plate's control means — the
    // no-effect control at white, the full-effect one red.
    const fixed = wantsComputed && normalization ? FIXED_PERCENT[normalization] : undefined;
    if (fixed) {
      const [none, full] = fixed;
      return anchored(none, full, `${none} %`, `${full} %`, negMean, posMean);
    }
    const [none, full] = fullIsPositive ? [negMean, posMean] : [posMean, negMean];
    const [noneName, fullName] = fullIsPositive ? ["NEG", "POS"] : ["POS", "NEG"];
    if (none != null && full != null && none !== full) {
      const u = wantsComputed ? "" : rawUnit ? ` ${rawUnit}` : "";
      return anchored(
        none,
        full,
        `${noneName} ${fmt(none)}${u}`,
        `${fullName} ${fmt(full)}${u}`,
        negMean,
        posMean,
      );
    }
    if (sampleValues.length === 0) {
      return {
        low: 0,
        high: 1,
        kind: "linear",
        negMean,
        posMean,
      };
    }
    const lo = Math.min(...sampleValues);
    const hi = Math.max(...sampleValues);
    return {
      low: lo,
      high: hi === lo ? lo + 1 : hi,
      kind: "linear",
      negMean,
      posMean,
    };
  }

  /** Sequential palette only when the metric is unsigned magnitude AND we
   *  aren't z-scoring it — otherwise the diverging palette carries the
   *  signed semantics correctly. */
  const palette: Palette = isDose && scaleKind === "linear" ? "sequential" : "diverging";

  if (!protocol || plateMapLoading || readoutLoading) {
    return <p className="py-12 text-center text-sm text-muted-foreground">Loading…</p>;
  }

  if (plates.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        No plate map. Import a run file or set up a plate.
      </p>
    );
  }

  // For the dose option there's no readout def — synthesize labels from
  // the protocol's canonical dose unit.
  const computedUnit = isDose
    ? "Concentration"
    : selectedDef
      ? computedUnitLabel(normalization ?? "none")
      : "Computed";

  return (
    <div className="mt-4 space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Readout</label>
          <Select value={effectiveReadoutId ?? undefined} onValueChange={(v) => setReadoutId(v)}>
            <SelectTrigger className="h-9 w-[260px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {numericReadouts.map((d) => (
                <SelectItem key={d.id} value={d.id} className="text-sm">
                  {d.name}
                  {d.unit ? ` (${d.unit})` : ""}
                </SelectItem>
              ))}
              <SelectItem value={DOSE_OPTION_ID} className="text-sm">
                Concentration ({doseUnit})
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {layerAvailable && (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Value</label>
            <div className="inline-flex h-9 items-center gap-0.5 rounded-md border bg-muted/40 p-1">
              <Button
                type="button"
                size="sm"
                variant={effectiveLayer === "raw" ? "secondary" : "ghost"}
                className="h-7 rounded-sm px-2.5 text-xs"
                onClick={() => setLayer("raw")}
              >
                Raw
              </Button>
              <Button
                type="button"
                size="sm"
                variant={effectiveLayer === "normalized" ? "secondary" : "ghost"}
                className="h-7 rounded-sm px-2.5 text-xs"
                onClick={() => setLayer("normalized")}
              >
                {computedUnit}
              </Button>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Scale</label>
          <div className="inline-flex h-9 items-center gap-0.5 rounded-md border bg-muted/40 p-1">
            <Button
              type="button"
              size="sm"
              variant={scaleKind === "linear" ? "secondary" : "ghost"}
              className="h-7 rounded-sm px-2.5 text-xs"
              onClick={() => setScaleKind("linear")}
            >
              Linear
            </Button>
            <Button
              type="button"
              size="sm"
              variant={scaleKind === "zscore" ? "secondary" : "ghost"}
              className="h-7 rounded-sm px-2.5 text-xs"
              onClick={() => setScaleKind("zscore")}
            >
              Z-Score
            </Button>
          </div>
        </div>
      </div>

      {/* Per-plate heatmaps */}
      <div className="space-y-8">
        {plates.map((plate) => {
          const scale = buildScale(plate);
          const qc = perPlateQc[plate.plate_id];
          const zp = typeof qc?.z_prime === "number" ? qc.z_prime : null;
          const zpQuality = zp != null ? classifyZPrime(zp) : null;

          // Every well with a value is filled, controls too (as on the platform:
          // the positive-control column reads solid red); a control keeps its
          // type-color outline as identity.
          const valuesForGradient = new Map<string, number>();
          const controlTypesSeen = new Set<string>();
          for (const w of plate.wells) {
            const v = activeByWellId.get(w.well_id);
            if (v != null) valuesForGradient.set(w.well_id, v);
            if (
              w.well_type === "negative_control" ||
              w.well_type === "positive_control" ||
              w.well_type === "blank" ||
              w.well_type === "reference"
            ) {
              controlTypesSeen.add(w.well_type);
            }
          }
          const controlTypesPresent = (
            ["negative_control", "positive_control", "blank", "reference"] as const
          ).filter((t) => controlTypesSeen.has(t));

          return (
            <div key={plate.plate_id} className="space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <div className="flex items-baseline gap-3">
                  <h3 className="text-sm font-medium">Plate {plate.plate_number}</h3>
                  <span className="text-xs text-muted-foreground">
                    {plate.summary.total_wells} wells · {plate.summary.sample_wells} samples ·{" "}
                    {plate.summary.control_wells} controls
                  </span>
                  <RunPlateLink runId={run.id} plate={plate} readOnly />
                </div>
                {zp != null && zpQuality && (
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                      Z&apos;
                    </span>
                    <span className="font-mono text-sm tabular-nums">{zp.toFixed(3)}</span>
                    <Badge
                      variant="outline"
                      className={cn("text-[10px] font-medium", Z_PRIME_BADGE[zpQuality].className)}
                    >
                      {Z_PRIME_BADGE[zpQuality].label}
                    </Badge>
                    {typeof qc?.s2b === "number" && (
                      <span className="ml-2 text-[11px] text-muted-foreground">
                        S/B <span className="font-mono tabular-nums">{qc.s2b.toFixed(2)}</span>
                      </span>
                    )}
                  </div>
                )}
              </div>

              <ColorScaleLegend
                scale={scale}
                palette={palette}
                unit={wantsComputed ? null : rawUnit}
                controlTypesPresent={controlTypesPresent}
                colors={colors}
                hasOutliers={plate.wells.some((w) => outlierWellIds.has(w.well_id))}
              />

              <PlateValueHeatmap
                plate={plate}
                valueByWellId={valuesForGradient}
                rawByWellId={rawByWellId}
                computedByWellId={computedByWellId}
                scale={scale}
                palette={palette}
                rawUnit={rawUnit}
                computedUnit={computedUnit}
                doseUnit={doseUnit}
                outlierWellIds={outlierWellIds}
                colors={colors}
                onFlag={canFlag ? onFlag : undefined}
                flagPending={flag.isPending}
              />
            </div>
          );
        })}
      </div>

      {curves && curves.length > 0 && (
        <p className="pt-2 text-[11px] text-muted-foreground">
          {curves.length} fitted curve{curves.length === 1 ? "" : "s"} · see Dose-Response tab.
        </p>
      )}
    </div>
  );
}
