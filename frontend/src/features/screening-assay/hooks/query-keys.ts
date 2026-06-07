/**
 * Shared React Query root keys (and nested-key factories) for the
 * screening-assay feature. Declared once here so invalidation and reads stay
 * in lockstep across hooks — re-declaring a key per file silently desyncs the
 * cache. Mirrors chemical-registration/hooks/query-keys.ts.
 */

export const PROTOCOLS_KEY = ["protocols"];
export const RUNS_KEY = ["runs"];
/** Singular run detail cache (distinct from the RUNS_KEY list). */
export const RUN_KEY = ["run"];
export const DOSE_RESPONSE_KEY = ["dose-response-curves"];
export const READOUT_DATA_KEY = ["readout-data"];
export const PLATE_MAP_KEY = ["plate-map"];
export const COMPOUND_CURVES_KEY = ["compound-curves"];
export const MULTI_COMPOUND_CURVES_KEY = ["multi-compound-curves"];
export const PROTOCOL_ACTIVITY_KEY = ["protocol-activity"];
export const RUN_IMPORT_TEMPLATES_KEY = ["run-import-templates"];

/** Rich effective-target list for a protocol (nested under PROTOCOLS_KEY). */
export const protocolTargetsKey = (protocolId: string) => [...PROTOCOLS_KEY, protocolId, "targets"];
