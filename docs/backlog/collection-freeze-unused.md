# `Collection.freeze()` / `is_frozen` / `derived_from_campaign_id` are unused

**Found:** 2026-09-11, while documenting the Campaign Hit Stages + Soft Close feature
(`docs/superpowers/specs/2026-09-11-campaign-hit-stages-and-soft-close-spec.md`).

**Root cause:** `Collection.freeze(*, derived_from_campaign_id)`
(`backend/src/cellar/domain/research_organization/collection.py`) marks a collection read-only and
records the campaign it was derived from. It backed the original Screen Campaign design, where
closing a campaign optionally emitted a frozen `Hits — <campaign>` Collection
(`publishes_collection` / `published_collection_id`, migration 026 for the columns, migration 027
for the `collections.derived_from_campaign_id → campaign.id ON DELETE SET NULL` FK). The soft-close
redesign removes campaign-to-Collection publishing entirely — `Campaign.close()` no longer creates
or links a Collection, and `publishes_collection` / `published_collection_id` are gone from the
aggregate — so nothing calls `.freeze()` any more. Confirmed by grep: zero call sites for
`.freeze(` anywhere under `backend/src/cellar/`.

**Impact:** `is_frozen` and `derived_from_campaign_id` are now dead weight rather than a bug — a
domain method with no caller, two ORM columns plus the migration-027 FK, and two read-only fields
on `GET /collections` (`CollectionResponse.is_frozen` / `.derived_from_campaign_id`) that are
always `False` / `None` in practice, since nothing in the codebase can set them to anything else.
Not unsafe: `Collection.update()` still checks `is_frozen` and would refuse writes if it were ever
true, so the guard degrades safely to a no-op rather than silently allowing something it shouldn't.

**Fix direction:** remove `Collection.freeze()`, `is_frozen`, and `derived_from_campaign_id` from
the domain aggregate; drop the two `collections` columns (and the migration-027 FK) via a new
migration; drop the two fields from the collections API response
(`interface/routes/collections.py`). Already called out as an explicit non-goal of the hit-stages
spec (§13 "Out of scope") — not done as part of that change. Do it as its own small cleanup once
nothing else references the fields; verify with
`grep -rn "is_frozen\|derived_from_campaign_id\|\.freeze(" backend/src/cellar/` returning nothing
outside the files being deleted.
