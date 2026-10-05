# The Assays page shows only the first 50 protocols

**Found:** 2026-10-04, loading the distilled legacy catalog (425 protocols) into SACLAB-DEV for review. The page read "50 shown" and its facet counts added up to 50.

**Root cause:** `useProtocols` (`frontend/src/features/screening-assay/hooks/use-protocols.ts`) calls `GET /api/v1/protocols` without a `limit` and keeps only the first page. The route clamps a missing limit to `DEFAULT_PAGE_SIZE = 50` (`backend/src/cellar/application/shared/pagination.py`, max 200). The library view then filters, groups and counts facets in the browser over those 50 rows, so every protocol past the first page is invisible and the Type, Target and Category counts are wrong. It never showed while the workspace had about 20 protocols.

**Fix direction:** page through the list (or move the facet counts and filtering server-side, behind the existing `useProtocolFacets` seam) so the library always reflects every protocol in the workspace. Add a hook test with more than one page of protocols.
