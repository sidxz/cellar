/**
 * Shared React Query root keys (and nested-key factories) for the
 * screening-assay feature. Declared once here so invalidation and reads stay
 * in lockstep across hooks — re-declaring a key per file silently desyncs the
 * cache. Mirrors chemical-registration/hooks/query-keys.ts.
 */

export const PROTOCOLS_KEY = ["protocols"];
export const RUNS_KEY = ["runs"];
export const DOSE_RESPONSE_KEY = ["dose-response-curves"];

/** Rich effective-target list for a protocol (nested under PROTOCOLS_KEY). */
export const protocolTargetsKey = (protocolId: string) => [...PROTOCOLS_KEY, protocolId, "targets"];
