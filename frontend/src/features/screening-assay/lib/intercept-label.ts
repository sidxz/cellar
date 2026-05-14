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
  if (spec.label) return spec.label;
  const lvl = spec.level % 1 === 0 ? String(spec.level) : spec.level.toFixed(1);
  return `${spec.kind.toUpperCase()}${lvl}`;
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
  const lvl = key.level % 1 === 0 ? String(key.level) : key.level.toFixed(1);
  return `${key.kind.toUpperCase()}${lvl}`;
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
