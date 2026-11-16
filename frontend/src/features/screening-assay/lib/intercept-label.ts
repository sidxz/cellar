/**
 * Single source of truth for intercept display labels + cell-side matching.
 *
 * Spec: docs/superpowers/specs/2026-05-13-dynamic-intercept-columns-design.md
 *
 * Principle: every label, header, and column name on dose-response UI comes
 * from the protocol's `dose_response_config.intercepts` list. No component
 * anywhere in the frontend should contain the string literals "EC50",
 * "EC90", "IC50", "IC90", etc.
 */
import type { AggregationMode } from "@/features/research-organization/lib/use-aggregation-mode";
import type { InterceptKey, InterceptSpec, InterceptValue } from "../types";

/** Canonical chemist-facing format for an intercept identified only by
 *  (kind, level): e.g. `("ec", 50)` → `"EC50"`, `("ec", 12.5)` → `"EC12.5"`.
 *  Shared by `interceptLabel` (when no protocol-side custom label is set)
 *  and `interceptKeyLabel` (which has no spec at all). */
function formatKindLevel(kind: string, level: number): string {
  const lvl = level % 1 === 0 ? String(level) : level.toFixed(1);
  return `${kind.toUpperCase()}${lvl}`;
}

/**
 * Display label for a protocol intercept spec.
 *
 *   - If `spec.label` is set by the protocol, use it verbatim.
 *   - Otherwise fall back to `${KIND}${LEVEL}` (e.g. "EC50", "IC90").
 *   - Integer levels render without a trailing `.0`.
 *
 * Used everywhere a chemist-facing column header, chip label, or
 * dropdown option names an intercept.
 */
export function interceptLabel(spec: InterceptSpec): string {
  return spec.label ?? formatKindLevel(spec.kind, spec.level);
}

/**
 * Find the curve's `InterceptValue` row that matches a protocol spec.
 *
 * Matching is by `(kind, level)` — *not* by label — so the lookup
 * survives a protocol-level rename of an intercept after curves were
 * fit. Returns `undefined` when the curve hasn't been refit since the
 * spec was added (caller renders "—" with a recompute prompt).
 */
export function findInterceptValue(
  values: InterceptValue[] | null | undefined,
  spec: InterceptSpec,
): InterceptValue | undefined {
  if (!values) return undefined;
  return values.find((iv) => iv.spec.kind === spec.kind && iv.spec.level === spec.level);
}

/**
 * Display label for a bare `InterceptKey` — used in contexts that have a
 * key (e.g. a `HitCriterion.intercept_key` or `hit_threshold.intercept_key`)
 * but not the originating `InterceptSpec` with its protocol-defined label.
 *
 * Always returns the canonical `${KIND}${LEVEL}` (e.g. "EC50", "IC90").
 * Use `interceptLabel(spec)` instead when you have the full spec — it
 * respects custom protocol labels like "Coverage EC90".
 */
export function interceptKeyLabel(key: InterceptKey): string {
  return formatKindLevel(key.kind, key.level);
}

/**
 * Display label for "this readout-def's intercept N" — used by any picker
 * or table that lists one row per `(readout-def, intercept)` pair.
 *
 * Dedupes the redundant case: when a chemist names a readout-def the same
 * as its primary intercept (a CDD-style habit — readout "EC50" with
 * intercepts EC50 + EC90), the naive `${rdName} ${interceptLabel(spec)}`
 * produces "EC50 EC50" / "EC50 EC90". This helper drops the readout-def
 * prefix in that case so the labels read as "EC50" / "EC90".
 *
 * Other shapes pass through untouched: "Resazurin" + EC50 stays
 * "Resazurin EC50"; "Resazurin" + EC90 stays "Resazurin EC90".
 */
export function interceptOptionLabel(
  rdName: string,
  primary: InterceptSpec,
  spec: InterceptSpec,
): string {
  const thisLabel = interceptLabel(spec);
  const primaryLabel = interceptLabel(primary);
  // Case-insensitive — the chemist may have typed "ec50" or "EC50".
  if (rdName.toLowerCase() === primaryLabel.toLowerCase()) {
    return thisLabel;
  }
  return `${rdName} ${thisLabel}`;
}

/** Stable, parseable id for an intercept — used as a form value /
 *  radio-group key. Stringified `${kind}:${level}` so the round-trip
 *  through `parseInterceptKeyId` is exact. */
export function interceptKeyId(key: Pick<InterceptKey, "kind" | "level">): string {
  return `${key.kind}:${key.level}`;
}

/** Inverse of `interceptKeyId`. Returns null when the string isn't a
 *  valid `${kind}:${level}` id (defensive — e.g. a saved form state
 *  predating this field, or a key on a deleted intercept). */
export function parseInterceptKeyId(id: string | undefined | null): InterceptKey | null {
  if (!id) return null;
  const colon = id.indexOf(":");
  if (colon < 0) return null;
  const kind = id.slice(0, colon);
  const level = Number(id.slice(colon + 1));
  if ((kind !== "ec" && kind !== "ic") || Number.isNaN(level)) return null;
  return { kind, level };
}

/** Narrow a `{kind: string, level: number}` (orval emits `kind: string` from
 *  the OpenAPI schema; the protocol-side `InterceptKey` uses a literal
 *  `"ec" | "ic"` union). Returns null when the input is null/undefined or
 *  carries an invalid `kind`. Use at the boundary between wire types and
 *  the hand-typed domain. */
export function narrowInterceptKey(
  raw: { kind: string; level: number } | null | undefined,
): InterceptKey | null {
  if (!raw) return null;
  if (raw.kind !== "ec" && raw.kind !== "ic") return null;
  return { kind: raw.kind, level: raw.level };
}

/**
 * Structured display result for an intercept cell.
 *
 * Renderers branch on `kind` to pick markup (`qualifier` uses an amber
 * warning Badge; `scalar` / `nd` / `missing` use a plain span). `text` is
 * the already-formatted numeric/qualifier string; the caller appends the
 * unit only when `kind === "scalar"` or `"qualifier"` (an ND cell should
 * never read "ND uM").
 */
export type InterceptDisplayKind = "scalar" | "qualifier" | "nd" | "missing";

export interface InterceptDisplay {
  kind: InterceptDisplayKind;
  text: string;
  tooltip: string;
  warning: boolean;
  /**
   * Value AG Grid (and any other sorter) should compare on.
   *
   * Mirrors `kind` so the sort order matches the chemist's mental model:
   *   - `scalar`   → the value (lowest = most potent)
   *   - `qualifier`→ +Infinity (some response, weaker than the tested
   *     range — sorts after all finite scalars but before nulls)
   *   - `nd`       → null (no information — sinks to the bottom)
   *   - `missing`  → null (same; no value to compare)
   *
   * Without this, sorting EC50 ascending would put Inactive curves at
   * the top of the table next to truly potent compounds, since the Hill
   * fitter parks an arbitrary asymptote-bound scalar on `fitted_value`
   * even when the curve doesn't represent real activity.
   */
  sortValue: number | null;
  // ---- NEW: multi-run decoration ----
  /** Alias for `text`. Prefer this name in new code; `text` kept for
   *  back-compat with the 3 existing callers (run-dr-results-columns,
   *  readout-data-table, activity-tab-columns) until Task 12's
   *  <InterceptCell /> replaces them on the search grid. */
  primary: string;
  /** Subscript run count + mode-conditional fold-range chip. Null when
   *  runCount <= 1 AND no fold-range chip applies. */
  decoration: {
    runCountSubscript: string | null;
    foldRangeChip: string | null;
  } | null;
}

export const TOOLTIP_INACTIVE =
  "Inactive: no response within the tested doses, so the value lies above the top dose.";
const TOOLTIP_INACTIVE_NO_RANGE =
  "ND = Not Determined. Curve was classified inactive, and no tested concentration is available to report as a bound.";
const TOOLTIP_ABOVE_RANGE =
  "The fit puts this value above the tested doses; it is reported as a bound, not the extrapolated number.";
const TOOLTIP_BELOW_RANGE =
  "The fit puts this value below the tested doses; it is reported as a bound, not the extrapolated number.";
const TOOLTIP_MISSING = "No value for this intercept. Recompute the curve to refresh.";
const TOOLTIP_QUALIFIER =
  "Response did not reach this intercept within the tested concentration range. Reported as an upper-bound qualifier.";
const TOOLTIP_AT_BOUND_NO_RANGE =
  "ND = Not Determined. Fit hit a bound, and no tested concentration is available to report as an upper bound.";

/** Map of ASCII digits → Unicode subscript digits, used for chemistry-style
 *  run-count typography (`H₂O`-style "₃" superimposed on the cell value to
 *  surface multi-run aggregation depth without stealing column width). */
const SUBSCRIPT_DIGITS: Record<string, string> = {
  "0": "₀",
  "1": "₁",
  "2": "₂",
  "3": "₃",
  "4": "₄",
  "5": "₅",
  "6": "₆",
  "7": "₇",
  "8": "₈",
  "9": "₉",
};

function toSubscript(n: number): string {
  return String(n)
    .split("")
    .map((d) => SUBSCRIPT_DIGITS[d] ?? d)
    .join("");
}

/**
 * Decide how an intercept cell should display its value.
 *
 *   - `curve_class === "inactive"` → "> {max_dose}" (muted, not a warning): no response in
 *     the tested doses, so the value lies above them — the fit's number never shows.
 *   - `value == null`             → "—" with a recompute hint (intercept
 *     was added to the protocol after this curve was fit).
 *   - `at_bound === true`         → "> {max_dose}" qualifier when we know
 *     the tested range (the intercept resolver's and the workbench's censoring rule).
 *   - value above `max_dose` / below `min_dose` → "> {max_dose}" / "< {min_dose}": an
 *     extrapolated value is censored at the dose range, as the external platform reports it.
 *   - else                        → scalar `value.toPrecision(4)`.
 *
 * Without a tested dose to quote, an inactive or at-bound cell reads "ND" (we don't
 * fabricate a bound).
 *
 * Unit-agnostic — callers append units only when `kind === "scalar" ||
 * "qualifier"`.
 *
 * Multi-run decoration (optional): when the cell summarizes ≥2 runs, the
 * returned `decoration` carries a subscript count (always) and a fold-range
 * chip (only when the aggregation `mode` is `gmean` or `mean`, i.e. an
 * actual aggregate — `latest` / `best_r2` pick a single source curve and
 * don't have a meaningful spread to report). `warning` is OR'd with
 * `disagreement` so a scalar cell can still flash amber when the underlying
 * runs disagree on classification (e.g. one run Inactive, another Active).
 */
export function formatInterceptDisplay(args: {
  value: number | null;
  at_bound: boolean | undefined | null;
  curve_class: string | null | undefined;
  max_dose: number | null;
  /** The lowest tested dose; without it nothing is censored below the range. */
  min_dose?: number | null;
  // ---- NEW: multi-run aggregation context (all optional, defaults
  // preserve current single-run behavior) ----
  runCount?: number;
  mode?: AggregationMode;
  foldRange?: number | null;
  disagreement?: boolean;
}): InterceptDisplay {
  const runCount = args.runCount ?? 1;
  const mode = args.mode ?? "latest";
  const foldRange = args.foldRange ?? null;
  const disagreement = args.disagreement ?? false;

  // Compute the existing kind / text / tooltip / warning / sortValue per
  // the current display rules.
  let base: Omit<InterceptDisplay, "primary" | "decoration">;

  const maxDose = positive(args.max_dose);
  const minDose = positive(args.min_dose);
  const above = (tooltip: string, warning: boolean) => ({
    kind: "qualifier" as const,
    text: `> ${boundText(maxDose as number)}`,
    tooltip,
    warning,
    // Weaker than the tested range — sorts after every finite scalar in
    // ascending order but ahead of nulls.
    sortValue: Number.POSITIVE_INFINITY,
  });
  const nd = (tooltip: string) => ({
    kind: "nd" as const,
    text: "ND",
    tooltip,
    warning: false,
    sortValue: null,
  });

  if (args.curve_class === "inactive") {
    base = maxDose != null ? above(TOOLTIP_INACTIVE, false) : nd(TOOLTIP_INACTIVE_NO_RANGE);
  } else if (args.value == null) {
    base = {
      kind: "missing",
      text: "—",
      tooltip: TOOLTIP_MISSING,
      warning: false,
      sortValue: null,
    };
  } else if (args.at_bound) {
    base = maxDose != null ? above(TOOLTIP_QUALIFIER, true) : nd(TOOLTIP_AT_BOUND_NO_RANGE);
  } else if (maxDose != null && args.value > maxDose) {
    base = above(TOOLTIP_ABOVE_RANGE, true);
  } else if (minDose != null && args.value < minDose) {
    base = {
      kind: "qualifier",
      text: `< ${boundText(minDose)}`,
      tooltip: TOOLTIP_BELOW_RANGE,
      warning: true,
      // More potent than the tested range — ahead of every finite scalar.
      sortValue: Number.NEGATIVE_INFINITY,
    };
  } else {
    base = {
      kind: "scalar",
      text: args.value.toPrecision(4),
      tooltip: "",
      warning: false,
      sortValue: args.value,
    };
  }

  // Multi-run decoration: subscript run-count (when ≥2 runs) + mode-
  // conditional fold-range chip. `latest` / `best_r2` pick a single source
  // curve so a fold-range chip would be misleading — only `gmean` / `mean`
  // are true aggregates with a meaningful spread.
  const showFoldRange =
    foldRange !== null && (mode === "gmean" || mode === "mean") && runCount >= 2;
  const decoration =
    runCount >= 2 || showFoldRange
      ? {
          runCountSubscript: runCount >= 2 ? toSubscript(runCount) : null,
          foldRangeChip: showFoldRange ? `×${Math.round(foldRange)}` : null,
        }
      : null;

  return {
    ...base,
    // Alias for `text` — Task 12's <InterceptCell /> reads `.primary`;
    // existing callers stay on `.text`.
    primary: base.text,
    decoration,
    // Underlying-run disagreement can flag a scalar cell amber too, not
    // just qualifier cells.
    warning: base.warning || disagreement,
  };
}

/** A fitted curve's headline value — its primary intercept, `fitted_value` — as
 *  `formatInterceptDisplay` reads it, for a surface that shows one value per curve. */
export function curvePotency(curve: {
  fitted_value: number;
  curve_class?: string | null;
  intercept_values?: readonly unknown[] | null;
  raw_data?: readonly unknown[] | null;
}): InterceptDisplay {
  const primary = curve.intercept_values?.[0] as { at_bound?: boolean } | undefined;
  return formatInterceptDisplay({
    value: curve.fitted_value,
    at_bound: primary?.at_bound,
    curve_class: curve.curve_class,
    ...doseRange(curve.raw_data),
  });
}

/** `curvePotency` as one string, with the unit where a value shows ("> 500 uM", "ND"). */
export function curvePotencyText(
  curve: Parameters<typeof curvePotency>[0] & { fitted_unit?: string | null },
): string {
  const p = curvePotency(curve);
  const valued = p.kind === "scalar" || p.kind === "qualifier";
  return valued ? `${p.text} ${curve.fitted_unit ?? ""}`.trimEnd() : p.text;
}

function positive(v: number | null | undefined): number | null {
  return v != null && Number.isFinite(v) && v > 0 ? v : null;
}

/** A tested dose as a bound reads: 4 significant digits, no trailing zeros ("> 500"). */
function boundText(dose: number): string {
  return String(Number(dose.toPrecision(4)));
}

/**
 * The lowest and highest positive tested dose on a raw_data list. Accepts
 * both `{x, y}` (the chart-normalized shape) and `{concentration,
 * response}` (the persisted shape on `DoseResponseCurve.raw_data`).
 *
 * Nulls when the list is empty or every entry is non-positive / non-finite —
 * the caller then reads "ND" rather than fabricating a qualifier.
 */
export function doseRange(rawData: readonly unknown[] | null | undefined): {
  min_dose: number | null;
  max_dose: number | null;
} {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const pt of rawData ?? []) {
    const { x, concentration } = (pt ?? {}) as { x?: unknown; concentration?: unknown };
    const raw = x ?? concentration;
    if (typeof raw === "number" && Number.isFinite(raw) && raw > 0) {
      min = Math.min(min, raw);
      max = Math.max(max, raw);
    }
  }
  return max === Number.NEGATIVE_INFINITY
    ? { min_dose: null, max_dose: null }
    : { min_dose: min, max_dose: max };
}
