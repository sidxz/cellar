/**
 * Shared React Query root keys for the inventory feature. Declared once here so
 * invalidation and reads stay in lockstep across hooks — re-declaring a key per
 * file silently desyncs the cache. Mirrors chemical-registration/hooks/query-keys.ts.
 */

export const BATCHES_KEY = ["batches"];
export const PLATES_KEY = ["plates"] as const;
export const PLATE_GROUPS_KEY = ["plate-groups"] as const;
export const LOANS_KEY = ["plate-loans"] as const;
