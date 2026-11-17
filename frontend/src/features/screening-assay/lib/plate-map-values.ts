import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import type { PlateData, ReadoutNormalization } from "../types";

export type PlateColorBy = "response" | "compound" | "concentration" | "well-type";
export type ScaleKind = "linear" | "zscore";
export type Palette = "diverging" | "sequential";

export interface ValueScale {
  low: number;
  high: number;
  kind: ScaleKind;
  zMean?: number;
  zStd?: number;
  marks?: { value: number; text: string }[];
  negMean?: number;
  posMean?: number;
}

export const formatPlateValue = (value: number) => String(Number(value.toPrecision(3)));

const mean = (values: number[]) =>
  values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : undefined;

function bounds(values: number[]): [number, number] {
  if (!values.length) return [0, 1];
  let low = Number.POSITIVE_INFINITY;
  let high = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    low = Math.min(low, value);
    high = Math.max(high, value);
  }
  return [low, high === low ? low + 1 : high];
}

const FIXED_PERCENT: Partial<Record<ReadoutNormalization, [number, number]>> = {
  percent_inhibition: [0, 100],
  percent_activation: [0, 100],
  percent_control: [100, 0],
};

/** The same input plates produce the same colours in every card and expanded map.
 * A shared scale pools eligible wells across the run; per-plate scaling passes one plate.
 * Flagged wells retain their displayed values but never move the scale's anchors. */
export function buildPlateScale({
  plates,
  values,
  outliers,
  kind,
  concentration = false,
  normalization,
  fullIsPositive = false,
  unit,
}: {
  plates: readonly PlateData[];
  values: ReadonlyMap<string, number>;
  outliers: ReadonlySet<string>;
  kind: ScaleKind;
  concentration?: boolean;
  normalization?: ReadoutNormalization;
  fullIsPositive?: boolean;
  unit?: string | null;
}): ValueScale {
  const all: number[] = [];
  const samples: number[] = [];
  const negative: number[] = [];
  const positive: number[] = [];
  for (const plate of plates) {
    for (const well of plate.wells) {
      const value = values.get(well.well_id);
      if (
        value == null ||
        !Number.isFinite(value) ||
        (!concentration && outliers.has(well.well_id))
      )
        continue;
      all.push(value);
      if (well.well_type === "sample") samples.push(value);
      if (well.well_type === "negative_control") negative.push(value);
      if (well.well_type === "positive_control") positive.push(value);
    }
  }
  const negMean = mean(negative);
  const posMean = mean(positive);
  if (kind === "zscore") {
    const mu = mean(all) ?? 0;
    const variance =
      all.length > 1
        ? all.reduce((sum, value) => sum + (value - mu) ** 2, 0) / (all.length - 1)
        : 0;
    const std = Math.sqrt(variance);
    const halfSpan = std > 0 ? 2 * std : 1;
    return { low: mu - halfSpan, high: mu + halfSpan, kind, zMean: mu, zStd: std };
  }
  if (concentration) {
    const [low, high] = bounds(all);
    return { low, high, kind };
  }

  const fixed = normalization ? FIXED_PERCENT[normalization] : undefined;
  const [none, full] = fixed ?? (fullIsPositive ? [negMean, posMean] : [posMean, negMean]);
  if (none != null && full != null && none !== full) {
    const suffix = unit ? ` ${unit}` : "";
    const [noneName, fullName] = fullIsPositive ? ["NEG", "POS"] : ["POS", "NEG"];
    return {
      low: 2 * none - full,
      high: full,
      kind,
      negMean,
      posMean,
      marks: fixed
        ? [
            { value: none, text: `${none} %` },
            { value: full, text: `${full} %` },
          ]
        : [
            { value: none, text: `${noneName} ${formatPlateValue(none)}${suffix}` },
            { value: full, text: `${fullName} ${formatPlateValue(full)}${suffix}` },
          ],
    };
  }
  const [low, high] = bounds(samples.length ? samples : all);
  return { low, high, kind, negMean, posMean };
}

/** Assign once across all plates, so moving a compound never changes its colour. */
export function compoundColorsForPlates(plates: readonly PlateData[]): Map<string, string> {
  const ids = [
    ...new Set(
      plates.flatMap((plate) =>
        plate.wells
          .filter((well) => well.well_type === "sample" && well.molecule_id)
          .map((well) => well.molecule_id as string),
      ),
    ),
  ].sort();
  return new Map(
    ids.map((id, index) => [
      id,
      ids.length <= GROUP_PALETTE.length
        ? GROUP_PALETTE[index]
        : `hsl(${Math.round((index * 360) / ids.length)}, 50%, 55%)`,
    ]),
  );
}

export function plateCompounds(plate: PlateData) {
  const entries = new Map<
    string,
    {
      id: string;
      label: string;
      aliases: Set<string>;
      batches: Set<string>;
      doses: Set<number>;
      wellCount: number;
    }
  >();
  for (const well of plate.wells) {
    if (well.well_type !== "sample" || !well.molecule_id) continue;
    const entry = entries.get(well.molecule_id) ?? {
      id: well.molecule_id,
      label:
        well.registration_number ?? well.molecule_name ?? well.batch_number ?? well.molecule_id,
      aliases: new Set<string>(),
      batches: new Set<string>(),
      doses: new Set<number>(),
      wellCount: 0,
    };
    for (const alias of [well.molecule_name, ...(well.synonyms ?? [])]) {
      if (alias && alias !== entry.label) entry.aliases.add(alias);
    }
    if (well.batch_number) entry.batches.add(well.batch_number);
    if (well.dose != null) entry.doses.add(well.dose);
    entry.wellCount += 1;
    entries.set(entry.id, entry);
  }
  return [...entries.values()].sort((a, b) =>
    a.label.localeCompare(b.label, undefined, { numeric: true }),
  );
}
