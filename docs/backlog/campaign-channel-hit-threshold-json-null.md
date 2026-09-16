# campaign_channel.hit_threshold stores JSON `null`, not SQL NULL, for empty thresholds

**Found:** 2026-09-11, during migration 074 (campaign hit stages) backfill verification against the dev DB.

**Root cause:** `CampaignChannelModel.hit_threshold` is `mapped_column(JSONB, nullable=True)` with no `none_as_null=True` on the `JSONB` type. SQLAlchemy's default JSON/JSONB bind behavior writes a Python `None` value as the **JSON scalar `null`** (`'null'::jsonb`), not SQL `NULL`, whenever the attribute is set (as opposed to simply never assigned). On the dev DB, `SELECT count(*) FROM campaign_channel WHERE hit_threshold IS NOT NULL` returned 48 rows, but only 14 had a real threshold dict — the other 34 hold the JSON literal `null`.

**Impact:** harmless for ORM-level code (`ch.hit_threshold` round-trips as Python `None` either way — the asyncpg JSONB codec decodes `'null'::jsonb` back to `None`), but any **raw SQL** `WHERE hit_threshold IS NOT NULL` filter (migration 074's backfill query included) silently includes these empty rows. Migration 074's `build_stage_rows` already treats a decoded `None` as "skip" (`if not threshold: continue`), so the backfill produced correct output despite the loose SQL filter — but the next raw-SQL query against this column that assumes `IS NOT NULL` means "has a value" will get it wrong.

**Fix direction:** either add `none_as_null=True` to the `JSONB` type on `hit_threshold` (and backfill the existing `'null'::jsonb` rows to real SQL `NULL`), or always filter with `WHERE hit_threshold IS NOT NULL AND hit_threshold != 'null'::jsonb` in raw SQL going forward. Not fixed here — out of scope for an additive migration; left for whoever next writes raw SQL against this column.
