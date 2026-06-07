/**
 * Shared React Query root keys (and nested-key factories) for the
 * research-organization feature. Declared once here so invalidation and reads
 * stay in lockstep across hooks — re-declaring a key per file silently desyncs
 * the cache. Mirrors chemical-registration/hooks/query-keys.ts.
 */

export const COLLECTIONS_KEY = ["collections"];
/** Singular collection detail cache (distinct from the COLLECTIONS_KEY list). */
export const COLLECTION_KEY = ["collection"];
export const COLLECTION_SEARCH_KEY = ["collection-search"];
export const PROJECTS_KEY = ["projects"];
export const SAVED_SEARCHES_KEY = ["saved-searches"];

/** Per-project member list (nested under PROJECTS_KEY). */
export const projectMembersKey = (projectId: string) => [...PROJECTS_KEY, projectId, "members"];
/** Project scope-stats cache (nested under PROJECTS_KEY). */
export const PROJECT_SCOPE_STATS_KEY = [...PROJECTS_KEY, "scope-stats"];
