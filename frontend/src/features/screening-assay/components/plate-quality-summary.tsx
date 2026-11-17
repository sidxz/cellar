"use client";

import { Badge } from "@/shared/components/ui/badge";
import { formatPlateValue } from "../lib/plate-map-values";
import { classifyZPrime, readPerPlateQc, readPlateLayerQc } from "../lib/qc-metrics";
import type { PlateData, Run } from "../types";
import { Z_PRIME_BADGE } from "./z-prime-badge";

export function PlateQualitySummary({
  run,
  plate,
  readoutId,
  layer,
  values,
  outliers,
  showCoverage,
  valueLabel,
}: {
  run: Run;
  plate: PlateData;
  readoutId?: string;
  layer: string;
  values: ReadonlyMap<string, number>;
  outliers: ReadonlySet<string>;
  showCoverage: boolean;
  valueLabel: string;
}) {
  const layerQc = readoutId
    ? readPlateLayerQc(run.qc_metrics)[plate.plate_id]?.[readoutId]?.[layer]
    : undefined;
  const qc = layerQc ?? readPerPlateQc(run.qc_metrics)[plate.plate_id];
  const zPrime = typeof qc?.z_prime === "number" && Number.isFinite(qc.z_prime) ? qc.z_prime : null;
  const quality = zPrime === null ? null : Z_PRIME_BADGE[classifyZPrime(zPrime)];
  const samples = plate.wells.filter((well) => well.well_type === "sample");
  const present = samples.filter((well) => values.has(well.well_id)).length;
  const excluded = plate.wells.filter((well) => outliers.has(well.well_id)).length;
  const posCount = plate.wells.filter((well) => well.well_type === "positive_control").length;
  const negCount = plate.wells.filter((well) => well.well_type === "negative_control").length;
  const missing = samples.length - present;
  const spread = (value: number | undefined, sd: number | null | undefined) =>
    value == null
      ? "Unavailable"
      : `${formatPlateValue(value)}${sd == null ? "" : ` ± ${formatPlateValue(sd)}`}`;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {zPrime != null && quality ? (
          <>
            <span className="font-medium">
              {layerQc ? "Z′" : "Overall Z′"}{" "}
              <span className="tabular-nums">{zPrime.toFixed(2)}</span>
            </span>
            <Badge variant="outline" className={quality.className}>
              {quality.label}
            </Badge>
          </>
        ) : (
          <span className="text-muted-foreground">QC unavailable</span>
        )}
        {typeof qc?.s2b === "number" && (
          <span className="text-muted-foreground">
            S/B <span className="tabular-nums text-foreground">{formatPlateValue(qc.s2b)}</span>
          </span>
        )}
        {excluded > 0 && (
          <Badge variant="outline" className="border-amber-300 text-amber-800 dark:text-amber-300">
            {excluded} excluded
          </Badge>
        )}
        {showCoverage && missing > 0 && (
          <Badge
            variant="outline"
            className="border-amber-300 text-amber-800 dark:text-amber-300"
            title={`Sample wells without ${valueLabel} values`}
          >
            {missing} without a value
          </Badge>
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {showCoverage ? (
          <span>
            {present}/{samples.length} sample values
          </span>
        ) : (
          <span>{samples.length} sample wells</span>
        )}
        <span>
          {plate.summary.compounds ??
            new Set(samples.map((well) => well.molecule_id).filter(Boolean)).size}{" "}
          compounds
        </span>
        <span>
          {posCount} POS · {negCount} NEG
        </span>
        {plate.summary.replicates > 1 && <span>{plate.summary.replicates}× replicates</span>}
      </div>
      {(qc?.pos_mean != null || qc?.neg_mean != null) && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer hover:text-foreground">
            Control statistics{layerQc ? "" : " · overall QC"}
          </summary>
          <dl className="mt-2 grid grid-cols-2 gap-2 rounded-md bg-muted/30 p-2">
            <div>
              <dt>Positive control · mean ± SD</dt>
              <dd className="mt-1 tabular-nums text-foreground">
                {spread(qc?.pos_mean, qc?.pos_sd)}
              </dd>
            </div>
            <div>
              <dt>Negative control · mean ± SD</dt>
              <dd className="mt-1 tabular-nums text-foreground">
                {spread(qc?.neg_mean, qc?.neg_sd)}
              </dd>
            </div>
          </dl>
        </details>
      )}
    </div>
  );
}
