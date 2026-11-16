import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import { formatCount, formatMeasurementValue } from "@/shared/lib/format-number";
import type { Dataset } from "../types";
import { column, numberAt, siblingAt } from "./dataset";

/** A table cell's number: integers as they are, the rest at 3 significant figures. */
export function cellText(v: number): string {
  return Number.isInteger(v) ? String(v) : formatMeasurementValue(v);
}

const sig4 = (v: number) => formatMeasurementValue(v, 4);

const QUALIFIER_SYMBOLS: Record<string, string> = { ">=": "≥", "<=": "≤" };

/** A value qualifier as cells show it: inclusive bounds as ≥ / ≤, the rest as sent. */
export function qualifierText(q: unknown): string {
  return typeof q === "string" ? (QUALIFIER_SYMBOLS[q] ?? q) : "";
}

function statAt(ds: Dataset, key: string, stat: string, i: number): number | null {
  const v = siblingAt(ds, key, stat, i);
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** A numeric readout's aggregation (``provenance.aggregation`` without ``replicate_``). */
const AGGREGATION_NAMES: Record<string, string> = {
  mean: "Mean",
  geomean: "Geometric mean",
  median: "Median",
  min: "Lowest",
  max: "Highest",
};

/** How an aggregated value came about, for its popover: the column label and one line per
 * fact (aggregation and contributing n, SD, best, censored and inactive counts, the run's fit
 * and CI). Null for a Wells value and for a cell with no data behind it. */
export function describeValue(
  ds: Dataset,
  key: string,
  i: number,
): { title: string; lines: string[] } | null {
  const c = column(ds, key);
  const aggregation = c?.provenance.aggregation;
  if (!c || !aggregation) return null;
  const value = numberAt(ds, key, i);
  const at = (stat: string) => statAt(ds, key, stat, i);
  const withUnit = (v: number) => (c.unit ? `${sig4(v)} ${c.unit}` : sig4(v));
  const lines: string[] = [];

  if (aggregation === "p") {
    if (value === null) return null;
    lines.push("−log10 of the value in M");
  } else if (aggregation === "fit") {
    const curveClass = siblingAt(ds, key, "curve_class", i);
    if (value === null && curveClass == null) return null;
    if (curveClass === "inactive") lines.push("Inactive curve — no fitted value");
    const r2 = at("r_squared");
    const hill = at("hill_slope");
    lines.push(
      ["This run's fit", r2 !== null && `R² ${sig4(r2)}`, hill !== null && `Hill ${sig4(hill)}`]
        .filter(Boolean)
        .join(" · "),
    );
    const lo = at("ci_low");
    const hi = at("ci_high");
    if (lo !== null && hi !== null) {
      lines.push(`95% CI ${sig4(lo)}–${sig4(hi)}${c.unit ? ` ${c.unit}` : ""}`);
    }
  } else if (!c.provenance.layer) {
    // A dose-response value across runs: the geometric mean of the active curves' fits.
    const tested = at("n_tested");
    if (tested === null) return null;
    lines.push(`Geometric mean of ${at("n_used") ?? 0} of ${formatCount(tested, "curve")}`);
    const inactive = at("n_inactive") ?? 0;
    if (inactive > 0) lines.push(formatCount(inactive, "inactive curve"));
    const best = at("best");
    if (best !== null) lines.push(`Best ${withUnit(best)}`);
  } else {
    const inRun = aggregation.startsWith("replicate_");
    const name = inRun ? aggregation.slice("replicate_".length) : aggregation;
    const n = at("n") ?? 0;
    const censored = at("n_censored") ?? 0;
    if (n === 0 && censored === 0) return null;
    if (n > 0) {
      const label = AGGREGATION_NAMES[name] ?? "Mean";
      lines.push(
        inRun
          ? `${label} of ${formatCount(n, "replicate well")} in this run`
          : `${label} of ${formatCount(n, "value")}`,
      );
      // An arithmetic SD says nothing about a geometric mean's spread.
      const sd = name === "geomean" ? null : at("sd");
      if (sd !== null) lines.push(`SD ${sig4(sd)}`);
      const best = at("best");
      if (best !== null) lines.push(`Best ${withUnit(best)}`);
      if (censored > 0) {
        const set = name === "mean" || name === "geomean" ? "not averaged" : "left out";
        lines.push(`${formatCount(censored, "censored value")} ${set}`);
      }
      const nonpositive = at("n_nonpositive") ?? 0;
      if (nonpositive > 0) {
        lines.push(`${formatCount(nonpositive, "value")} ≤ 0 not in the geometric mean`);
      }
    } else if (value !== null) {
      lines.push(
        censored === 1
          ? "The only value is censored — showing its bound"
          : `All ${censored} values censored — showing the tightest bound`,
      );
    } else {
      lines.push("Censored both ways — no value");
    }
  }
  return { title: c.label, lines };
}

/** "Inactive 1/3 curves" when some of the row's curves for this readout were inactive. */
export function inactiveBadge(ds: Dataset, key: string, i: number): string | null {
  const inactive = statAt(ds, key, "n_inactive", i);
  const tested = statAt(ds, key, "n_tested", i);
  return inactive && tested ? `Inactive ${inactive}/${tested} curves` : null;
}

/** A Runs row's fitted curve for the dose-response value ``key``, from the value and its fit
 * siblings, ready for the shared curve renderer; null without measured points. */
export function curveSnapshotAt(ds: Dataset, key: string, i: number): CurveSnapshot | null {
  const points = siblingAt(ds, key, "points", i);
  if (!Array.isArray(points) || points.length === 0) return null;
  const at = (stat: string) => statAt(ds, key, stat, i);
  const top = at("top");
  const bottom = at("bottom");
  const hill = at("hill_slope");
  if (top === null || bottom === null || hill === null) return null;
  const curveClass = siblingAt(ds, key, "curve_class", i);
  return {
    // An inactive curve has no value; the renderer draws its points only, and any positive
    // scalar satisfies the shape.
    fitted_value:
      numberAt(ds, key, i) ?? (curveClass === "inactive" ? at("max_dose") : null) ?? Number.NaN,
    fitted_unit: column(ds, key)?.unit ?? null,
    top,
    bottom,
    hill_slope: hill,
    r_squared: at("r_squared"),
    curve_class: typeof curveClass === "string" ? curveClass : null,
    confidence_interval_low: at("ci_low"),
    confidence_interval_high: at("ci_high"),
    raw_data: points,
  };
}
