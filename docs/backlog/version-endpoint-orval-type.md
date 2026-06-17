# `/version` frontend type: regenerate via orval

**Status:** open — sanctioned deviation from the versioning feature (2026-06-17).

The backend `GET /version` endpoint returns a Pydantic `VersionResponse`
(`backend/src/cellar/interface/routes/version.py`). The frontend hook
`frontend/src/shared/hooks/use-api-version.ts` currently declares a **local**
`ApiVersionResponse` interface that mirrors that DTO field-for-field, because
the backend could not be booted to run `pnpm generate:api` during the feature
work.

This violates the standing CLAUDE.md orval rule ("never hand-roll a TS
interface that mirrors a backend DTO"). The fields match exactly today, so
there is no live drift, but the mirror is the exact thing the rule forbids.

**Follow-up:** with the backend running on `:8000`, run `pnpm generate:api`
from `frontend/`, then replace the local `ApiVersionResponse` interface in
`use-api-version.ts` with the generated `VersionResponse` type (alias if a
domain name is wanted). Remove the local interface.
