/**
 * Named `staleTime` tiers for TanStack Query hooks.
 *
 * The global QueryClient (see `shared/providers/query-provider.tsx`) defaults
 * to `STALE_TIME.DEFAULT` (60s). A hook only needs to set `staleTime`
 * explicitly when it wants a *different* tier — restating the default is a
 * no-op and should be dropped.
 *
 * Tiers (semantic intent, not exact data shapes):
 * - SHORT   (30s)  — frequently-changing previews/counts.
 * - DEFAULT (60s)  — the global baseline; same as the QueryClient default.
 * - MEDIUM  (5m)   — semi-static data (compute results, scaffold trees).
 * - LONG    (30m)  — rarely-changing reference data (ontologies, vocab).
 * - STATIC  (∞)    — immutable for the session.
 */
export const STALE_TIME = {
  SHORT: 30_000,
  DEFAULT: 60_000,
  MEDIUM: 5 * 60_000,
  LONG: 30 * 60_000,
  STATIC: Number.POSITIVE_INFINITY,
} as const;

export type StaleTimeTier = (typeof STALE_TIME)[keyof typeof STALE_TIME];
