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
  return values.find(
    (iv) => iv.spec.kind === spec.kind && iv.spec.level === spec.level,
  );
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
}

const TOOLTIP_INACTIVE =
  "Inactive curve — no determination. The fit didn't represent a real response, so this intercept is not reported.";
const TOOLTIP_MISSING =
  "No value for this intercept. Recompute the curve to refresh.";
const TOOLTIP_QUALIFIER =
  "Response did not reach this intercept within the tested concentration range. Reported as an upper-bound qualifier.";
const TOOLTIP_AT_BOUND_NO_RANGE =
  "Fit hit a bound, and no tested concentration is available to report as an upper bound.";

/**
 * Decide how an intercept cell should display its value.
 *
 *   - `curve_class === "inactive"` → "ND". The Hill fit doesn't represent
 *     real activity, so we never report a scalar (industry: CDD, Genedata).
 *   - `value == null`             → "—" with a recompute hint (intercept
 *     was added to the protocol after this curve was fit).
 *   - `at_bound === true`         → "> {max_dose}" qualifier when we know
 *     the tested range; otherwise "ND" (we don't fabricate a bound).
 *   - else                        → scalar `value.toPrecision(4)`.
 *
 * Unit-agnostic — callers append units only when `kind === "scalar" ||
 * "qualifier"`.
 */
export function formatInterceptDisplay(args: {
  value: number | null;
  at_bound: boolean | undefined | null;
  curve_class: string | null | undefined;
  max_dose: number | null;
}): InterceptDisplay {
  if (args.curve_class === "inactive") {
    return { kind: "nd", text: "ND", tooltip: TOOLTIP_INACTIVE, warning: false };
  }
  if (args.value == null) {
    return { kind: "missing", text: "—", tooltip: TOOLTIP_MISSING, warning: false };
  }
  if (args.at_bound) {
    if (args.max_dose != null && Number.isFinite(args.max_dose) && args.max_dose > 0) {
      return {
        kind: "qualifier",
        text: `> ${args.max_dose.toPrecision(4)}`,
        tooltip: TOOLTIP_QUALIFIER,
        warning: true,
      };
    }
    return { kind: "nd", text: "ND", tooltip: TOOLTIP_AT_BOUND_NO_RANGE, warning: false };
  }
  return { kind: "scalar", text: args.value.toPrecision(4), tooltip: "", warning: false };
}

/**
 * Pull the largest positive concentration from a raw_data list. Accepts
 * both `{x, y}` (the chart-normalized shape) and `{concentration,
 * response}` (the persisted shape on `DoseResponseCurve.raw_data`).
 *
 * Returns null when the list is empty or every entry is non-positive /
 * non-finite — caller falls back to "ND" rather than fabricating a
 * qualifier.
 */
export function maxDoseFromRawData(
  rawData:
    | Array<{ x?: number; concentration?: number }>
    | null
    | undefined,
): number | null {
  if (!rawData || rawData.length === 0) return null;
  let max = -Infinity;
  for (const pt of rawData) {
    const raw = pt.x ?? pt.concentration;
    if (typeof raw === "number" && Number.isFinite(raw) && raw > 0 && raw > max) {
      max = raw;
    }
  }
  return max === -Infinity ? null : max;
}
