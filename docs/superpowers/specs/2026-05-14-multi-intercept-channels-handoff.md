# Multi-Intercept Campaign Channels — Architecture Gap & Re-evaluation Brief

**Date:** 2026-05-14 (handoff to fresh session)
**Status:** **CLOSED 2026-05-14 — Option A shipped in commit #16.** Top-level `intercept_key` on `CampaignChannel`; alembic migration `035_cc_intercept_key`; preview/add-from-runs/resolver/route/DTO/FE pivoted to channel-level identity. New regression test (`test_multi_intercept_channels_with_display_only_second_intercept`) covers the chemist's actual workflow. 2454 BE tests + 152 FE tests green; tsc clean; dev DB migrated. Awaiting live smoke against `Mtb_WCA_mc2-7000_Resazurin`. See CLAUDE.md commit #16 entry for the per-layer summary.
**Spec context:** Surface #7 follow-on of `docs/superpowers/specs/2026-05-13-dynamic-intercept-columns-design.md`
**Branch:** `prot-2` (28 commits ahead of `e807dd03`); commits 13-15 attempt this and are *partial* — leave a broken UX state for multi-intercept channels with no threshold

---

## Problem in one sentence

A chemist who declares a protocol with two intercepts (e.g. `Mtb_WCA_mc2-7000_Resazurin` with EC50 + EC90) and imports into a campaign via "Add from runs" should see *two distinct channels* (EC50 + EC90) with *distinct per-compound values* and *independent hit decisions*. Today, even after commits #13–#15, the EC90 channel renders the EC50 number, the aggregate is `0 hits`, and the chemist can't surface EC90 as a display-only column.

---

## The chemist scenario (concrete, reproducible)

1. Protocol `Mtb_WCA_mc2-7000_Resazurin` declares one DR readout-def named `Resazurin` (or `EC50` in some workspaces — CDD-style readout naming) with `dose_response_config.intercepts = [EC50, EC90]`.
2. The protocol has `recommended_hit_criteria = [{readout_name: "Resazurin", operator: "lt", value: 50, intercept_key: null}]` — i.e. "hit if EC50 < 50 µM, primary intercept."
3. Chemist opens a new campaign (e.g. campaign 33), uses the "Add from runs" dialog, picks the protocol, selects a run with 22 molecules.
4. Three channels auto-generate: `EC50` (DR), `EC90` (DR), `RSZ (% Inhibition)` (RD).
5. `EC50` channel: `use_for_filter: ON`, threshold `< 50 µM` (auto-filled from the criterion).
6. `EC90` channel: `use_for_filter: OFF`, **no threshold** (the chemist's intent — informational column only).
7. `RSZ` channel: `use_for_filter: OFF`, no threshold.
8. Chemist clicks **Preview** → expects: `22 molecules · 2 hits · 20 non-hits` (the two compounds with EC50 < 50: CV-00967 at 4.68 µM, CV-00983 at 13.7 µM).
9. **Actual**: `22 molecules · 0 hits · 22 non-hits`, AND the EC50 and EC90 cells show identical numbers per row (4.68 / 4.68, 13.7 / 13.7) — there is no EC90-specific value visible *anywhere* on the campaign.

Screenshots captured 2026-05-14 in the live dev environment.

---

## What was shipped, and why it's still broken

The branch carries three relevant commits on top of Surface #7:

| Commit | Subject | What it does | Why it doesn't fix the chemist scenario |
|---|---|---|---|
| `73bb6f07` | `feat(campaign): channel hit threshold honors intercept_key end-to-end` | Surfaces an intercept picker in the channel popover when the readout-def declares ≥2 intercepts. Save serializes `intercept_key` *inside* `hit_threshold` (Surface #7's null-=-primary wire shape). | If the chemist's channel has *no threshold* (`hit_operator: "none"`), the popover save sets `hit_threshold = null` and the intercept identity is dropped before it leaves the FE. |
| `0003597e` | `feat(campaign): add-from-runs splits multi-intercept DR readouts per intercept` | `flatMap`s readout-defs into one ChannelConfigUI per declared intercept; carries the per-intercept criterion forward via the `interceptKey` filter on `deriveChannelHitDefaults`. | Same root cause: the per-channel intercept_key only survives the wire if there's a numeric threshold. Multi-intercept channels with `use_for_filter: OFF` import with `intercept_key` lost. |
| `e364c07b` | `fix(campaign): multi-intercept channels — proper cells, hits, labels` | Backend: extends `_channel_key` and `existing_by_key` to include `hit_threshold.intercept_key` as the disambiguating fourth axis; introduces `_Picked.eval_value` so cell value + hit_call honor the intercept-specific scalar. FE: dedupes `${rd.name} ${interceptLabel}` when `rd.name` already matches the primary intercept's label. | Cell value + hit logic correctly honor `intercept_key` *when the channel has a threshold carrying one*. The EC90-with-no-threshold case still flows through as "primary" because the channel-identity-disambiguator (`_cfg_intercept`) reads `cfg.hit_threshold.intercept_key` and gets `null` when `hit_threshold` is `None`. |

The label dedupe and the backend test (`test_multi_intercept_channels_disambiguate_cells_and_hits`) both ship correct behavior — the test passes with two thresholds, both intercept-keyed. The chemist's *real* workflow (one threshold, one display-only channel) just doesn't fit the data model.

---

## Root cause

**`intercept_key` is bound to `hit_threshold`, but channel identity is not.**

Surface #7's design located `intercept_key` on `HitCriterion` (= the threshold). That was correct for the protocol-level "recommended_hit_criteria" use case where every entry IS a criterion. But when projected onto a campaign channel:

- A `CampaignChannel` *is* its intercept (the channel's whole reason to exist).
- A `hit_threshold` is *one rule* the channel may or may not have.

The two have different lifetimes. A chemist can have a channel for EC90 *without* a hit rule (display-only column). With the current model, an unrated channel is indistinguishable from a primary-targeting channel — same wire shape (`hit_threshold: null`), same backend lookup behavior (falls through to `c.value` = primary).

The FE actually *knows* the channel's intercept in `ChannelConfigUI.intercept_key` (added in `0003597e`) and in the channel-popover form state (`hit_intercept_key`). But the wire shape forces it into `hit_threshold.intercept_key`, which gets dropped when there's no threshold.

---

## Architectural options

### Option A — `intercept_key` as a top-level field on `CampaignChannel` *(proper fix)*

Surface area:

- **Domain**: `CampaignChannel.intercept_key: InterceptKey | None`.
- **ORM**: `campaign_channel` table gains `intercept_key JSONB NULL` column.
- **Migration**: alembic ALTER TABLE adding the column. Backfill: existing rows → NULL (treated as primary, matches today's behavior).
- **Repository**: hydrate from `model.intercept_key`; save via `to_dict()`.
- **DTOs**: `AddChannelRequest`, `UpdateChannelRequest`, `CampaignChannelResponse`, `ChannelImportConfigDTO` — each gains `intercept_key` at top level.
- **Routes**: `add_campaign_channel`, `update_campaign_channel`, `add_results_from_runs`, `preview_run_import` — accept the new field, pass through to domain.
- **Application use cases**: `ChannelImportConfig` dataclass gets `intercept_key`. `preview_run_import._channel_key` and `existing_by_key` switch their disambiguator from `_cfg_intercept(cfg)` (reading hit_threshold) to `cfg.intercept_key` directly. Same in `add_results_from_runs`.
- **Resolver** (`channel_resolution.py`): refactor `_threshold_input_value(c, threshold)` into a thinner `_intercept_scalar(c, intercept_key)`; threshold-based lookup just composes the two. Channel evaluation in `resolve()` reads `channel.intercept_key`, not `channel.hit_threshold.intercept_key`.
- **Orval**: regenerate FE types.
- **Frontend `channel-popover.tsx`**: send `intercept_key` as a top-level field on the `AddChannelRequest` / `UpdateChannelRequest` mutation payloads; keep the picker UI as-is.
- **Frontend `add-from-runs-dialog.tsx`**: send `intercept_key` as a top-level field on each entry of `channel_configs[]` in the buildPayload output.
- **Frontend `channels-section.tsx::formatThreshold`**: prefer `channel.intercept_key` over `channel.hit_threshold?.intercept_key` (the latter becomes redundant/legacy).
- **Backwards-compat**: `HitCriterion.intercept_key` stays — still used by protocol-level `recommended_hit_criteria` and as the source-of-truth when carrying a criterion forward via `deriveChannelHitDefaults`. The channel's `hit_threshold.intercept_key` becomes informational; channel-level `intercept_key` is authoritative.

Estimated ~13 files. Migration is additive (new column with default null), low risk.

### Option B — Synthesize a "marker" `hit_threshold` on the FE *(hack)*

For multi-intercept channels with no chemist-set threshold, the FE constructs a stub `hit_threshold` that carries `intercept_key` but no real comparison:

```json
{"readout_name": "EC90", "operator": "in", "value": [], "intercept_key": {"kind": "ec", "level": 90}}
```

Pros: no backend schema change.

Cons:
- `operator: "in"` with `value: []` is a perfectly valid criterion that always returns "miss" via `_compute_hit_call`. The hit chip lies — chemist sees "miss" everywhere on the EC90 column when they wanted "no decision."
- Pollutes `HitCriterion` semantics: the type now has a stealth "informational" mode.
- Every consumer of `channel.hit_threshold` has to know about the marker convention.

Rejected as a long-term solution; might be tactically useful if Option A is too costly for the current sprint and the chemist needs the EC50 hit aggregate to work *right now*. Even then, the chip-lie cost may exceed the unblock benefit.

### Option C — Revert commits #13, #14, #15

Pros: existing campaigns (one channel per readout) keep working. No new bugs.

Cons:
- Surface #7's chemist-facing promise (intercept-aware hit criteria) becomes a half-feature: the protocol UI lets you say "EC90 < 50" but campaigns can't honor it.
- Loses the channel-key collision fix in commit #15 even for single-intercept-with-explicit-key scenarios.

Worth considering only if the team decides the multi-intercept campaign work is out of scope for the current quarter.

---

## Open questions for the re-evaluation session

1. **Do we keep `intercept_key` on `HitCriterion` for protocol-level criteria, or also remove it there?** Argument for keeping: protocol's `recommended_hit_criteria` *are* criteria — intercept_key belongs on the criterion. Argument against: now there are two places intercept identity lives and they can drift. Lean toward keep.
2. **Migration backfill for existing campaigns**: any channel with `hit_threshold.intercept_key` non-null today should arguably have its top-level `intercept_key` populated from that. Alembic data migration? Or accept that existing channels migrate lazily (read fall-through) and never have the top-level field populated until re-saved? Lean toward leaving the column NULL on backfill — read-side fall-through handles legacy data cleanly.
3. **Two-channels-same-readout reuse semantics**: a chemist with an existing campaign that has *one* primary channel (intercept_key=null) for `Resazurin` reruns add-from-runs after the protocol added EC90. What happens?
   - Today: would create a second EC90 channel (good).
   - After Option A: same — the (proto, rd, norm, ik) key tuple disambiguates by ik, so EC90 doesn't collide with the existing primary.
   - But: the chemist's `is_hit` recomputation across `mol_is_hit` would now have to factor in the new EC90 channel. Is that intended? Probably yes — re-import is the chemist's explicit signal to refresh.
4. **Channel `label` autoderivation**: currently the FE labels multi-intercept channels via `interceptLabel(spec)`. If a chemist later edits the readout's intercept label on the protocol, existing channels keep their stale label. Acceptable, or should display reach into the protocol's current label via channel.intercept_key? Lean toward storing-label-at-save (current behavior); the chemist's named entity is the channel.
5. **CDD-style readout names** (`rd.name === "EC50"`): commit #15's label dedupe handles the primary intercept correctly ("EC50" → "EC50" not "EC50 EC50"). But a chemist who genuinely has a single-readout assay named "EC50" with only one intercept gets channel label "EC50" — fine, exactly matches the readout name. What about an assay named "IC50" with intercepts `[IC50, IC90]`? Dedupe: primary = "IC50" (drop prefix), secondary = "IC90". Correct.
6. **Per-channel hit-criterion intercept matching at runtime**: `channel_resolution.py`'s `_compute_hit_call(c.value, threshold)` checks `threshold.intercept_key` to decide which scalar to compare. If the threshold has no intercept_key but the channel does, what wins? The channel's intercept (because the channel IS the intercept). Threshold's intercept_key becomes a sanity check at most.

---

## Diagnostic anchors (where to look first)

### Backend
- `backend/src/cellar/domain/research_organization/campaign_channel.py:25` — `CampaignChannel` dataclass; add `intercept_key` field here.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py:216` — `CampaignChannelModel`; add the column.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py:154,173,187` — hydrate / save / update channel; thread the new field.
- `backend/src/cellar/application/research_organization/preview_run_import.py:57` — `ChannelImportConfig`; `:236-252` — `_cfg_intercept` / `_channel_key` (switch from `hit_threshold.intercept_key` to top-level).
- `backend/src/cellar/application/research_organization/add_results_from_runs.py:161-203` — `ChannelKey` tuple + channel creation + reuse logic; same switch.
- `backend/src/cellar/application/research_organization/channel_resolution.py:140-170` — `_threshold_input_value`; refactor into `_intercept_scalar(c, intercept_key)` + thin threshold composer.
- `backend/src/cellar/interface/routes/_campaign_dtos.py` — `AddChannelRequestDTO`, `UpdateChannelRequestDTO`, `ChannelImportConfigDTO`; add `intercept_key`.
- `backend/src/cellar/interface/routes/campaigns.py:195,216` — `preview_run_import` and `add_results_from_runs` route handlers; pass through the new field.
- `backend/alembic/versions/` — new migration (after `034_drc_config_snapshot`).

### Frontend
- `frontend/src/features/screen-campaign/components/channel-popover.tsx:340-400` — `onSubmit`; currently `intercept_key` only goes into `hit_threshold`. Add it to the mutation payload's top-level fields.
- `frontend/src/features/screen-campaign/components/add-from-runs-dialog.tsx:196-260` — `buildPayload`; emit `intercept_key` as a top-level field on each channel_config entry.
- `frontend/src/features/screen-campaign/components/sections/channels-section.tsx:109-125` — `formatThreshold`; prefer `channel.intercept_key` over `parsed.intercept_key` (= `hit_threshold.intercept_key`).
- `frontend/src/features/screening-assay/lib/intercept-label.ts` — helpers already in place; nothing to change.
- `frontend/src/features/screening-assay/lib/hit-criteria-defaults.ts` — `deriveChannelHitDefaults` still useful for filtering criteria per-intercept; no change needed.

### Tests
- `backend/tests/unit/application/research_organization/test_preview_run_import.py:701-820` — `test_multi_intercept_channels_disambiguate_cells_and_hits` covers the WITH-threshold case. Add a sibling test covering the *no-threshold-EC90* case: chemist's actual workflow.
- `frontend/src/features/screening-assay/lib/hit-criteria-defaults.test.ts` — covers `deriveChannelHitDefaults` filtering. Channel-popover and add-from-runs lack colocated tests; consider adding one for the save serialization (sends intercept_key at top level).

---

## Verification scenario for the fresh session

After implementing Option A, the live smoke against `Mtb_WCA_mc2-7000_Resazurin` should:

1. Open a new campaign, "Add from runs", pick the protocol, select the May 12 2026 run (22 mols).
2. Config dialog shows three channels: `EC50` (DR, `use_for_filter: ON`, `< 50 µM`), `EC90` (DR, `use_for_filter: OFF`, `(no threshold)`), `RSZ (% Inhibition)` (RD, `use_for_filter: OFF`, no threshold).
3. Click Preview. Expected summary: `22 molecules · 2 hits · 20 non-hits` (compounds with EC50 < 50: CV-00967 at 4.68 µM, CV-00983 at 13.7 µM).
4. Per-compound cells: EC50 column shows the EC50 number, EC90 column shows the EC90 number — *distinct numbers per row*. CV-00967: EC50=4.68, EC90=somewhere around 40 (depends on the curve shape). RSZ column shows the % inhibition.
5. HIT badges: EC50 cells of CV-00967 + CV-00983 show "HIT"; their EC90 cells are blank/no-decision (no threshold); their RSZ cells are blank/no-decision.
6. Click "Add 2 hits" → channels persist with `channel.intercept_key` set correctly (null for EC50, {ec, 90} for EC90). DB inspection on `campaign_channel` table should show two distinct rows for the Resazurin readout with `intercept_key` JSONB populated on the EC90 row.
7. Edit the EC90 channel via the popover, set a threshold "< 100 µM". Re-render. EC90 column now shows HIT badges for compounds with EC90 < 100. Hit aggregate updates.

---

## Current branch state (2026-05-14 16:30 local)

- Branch `prot-2`, 28 commits ahead of `e807dd03`, nothing pushed.
- Working tree clean (after commits #13 / #14 / #15).
- Backend: 233 tests green (research_organization unit + integration + campaigns API).
- Frontend: 152 tests green, `pnpm exec tsc --noEmit` clean.
- **Smoke status**: commit #15's intended fix (channel-key collision + eval_value) works correctly when channels have intercept-keyed thresholds (test `test_multi_intercept_channels_disambiguate_cells_and_hits` verifies). Real chemist workflow (one channel with threshold, one display-only) still produces 0 hits + identical cell values — the scenario this handoff is about.
- Dev DB: migrations at head (`034_drc_config_snapshot`). No new migration written for the Option A fix; will need one after the schema choice.

If the fresh session chooses Option C (revert), the relevant commits to revert in order: `e364c07b`, `0003597e`, `73bb6f07` (plus the corresponding `docs:` commits if desired).

If the fresh session chooses Option A, the suggested implementation order:
1. Backend domain + ORM + alembic migration (smallest blast radius first).
2. Backend repository hydrate/save.
3. Backend DTOs + routes + orval regen.
4. Backend application (preview, mutation) — switch disambiguator + cell value lookup to use channel.intercept_key.
5. Backend resolver refactor.
6. Frontend mutation payloads (channel popover + add-from-runs).
7. Frontend display (channels-section).
8. Tests at each layer.
9. Live smoke against `Mtb_WCA_mc2-7000_Resazurin`.
