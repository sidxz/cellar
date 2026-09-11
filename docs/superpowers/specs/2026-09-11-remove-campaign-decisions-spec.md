# Remove campaign result decisions — spec

**Date:** 2026-09-11
**Status:** approved in chat (user: "yes, remove it. we are in dev so data is not problem")
**Builds on:** `2026-09-11-campaign-hit-stages-and-soft-close-spec.md`

## 1. Problem

`CampaignResult.decision` (selected / deferred / rejected, plus `decision_reason`) predates
hit stages. Its only downstream consumer was the auto-published "Hits" collection at close,
which the hit-stages work removed. What remains is a second triage label that can contradict
the funnel — a compound can be "hit at Confirmed" and "Rejected" at once — the same
duplicated-state problem per-readout thresholds had.

Stage outcomes plus per-stage manual overrides (reason required) already express everything
the decision did: *selected* = hit at the stage you care about, *rejected* = demoted with a
reason, *deferred* = not overridden. A hand-curated "take forward" list is a criteria-less child
stage; demote what you drop.

## 2. Decision

Remove `decision` and `decision_reason` from the domain, persistence, API, published payload,
and UI. Keep `notes` (free text per result) and give it its own editing path. No data
migration: dev-only data, columns are dropped outright.

## 3. Behaviour changes

| Surface | Before | After |
|---|---|---|
| Per-row edit | `PATCH /campaigns/{id}/results/{rid}` sets decision + reason + optional notes | Same route sets **notes only**: body `{"notes": string \| null}` |
| Bulk decision | `PATCH /campaigns/{id}/results/bulk-decision` | Route, use case, DTOs, and UI removed |
| Add from campaign | `decision_filter: ["selected", …]` | `stage_id: UUID \| null`. `null` = every result of the source campaign; a stage id = results whose evaluated outcome at that stage is **hit** (overrides honoured, via `evaluate_stages`). Stage must belong to the source campaign, else 422. |
| `CampaignRef` source ref | `decision_filter` list | `stage_id: UUID \| None`; `to_dict` emits `"stage_id": str \| None`; `from_dict` reads `stage_id` and ignores any legacy `decision_filter` key |
| Add from runs | `default_decision` on new rows | Field removed from command, DTO, route, and dialog. `scope` (hits_only / all) is unchanged. |
| Campaign result DTO | `decision`, `decision_reason`, `notes` | `notes` only |
| Published payload | `decision`, `decision_reason` per result | Both removed. **Cross-app contract change**: `backend/tests/api/fixtures/daikon_contract.schema.json` drops them from `required` and `properties`; the consumer app must stop reading them. |
| Filter bar | Selected / Deferred / Rejected chips + stage outcome chips + Overridden | Stage outcome chips + Overridden only. `closedCampaignFilters()` collapses to `emptyFilters()`. |
| Grid | "Decision" column (chip + reason/notes strip, popover editor) | "Notes" column: clamped notes text, click-to-edit popover in draft, inert when read-only |
| Close dialog | decision breakdown badges | Section removed (stage tiles above already carry the funnel counts) |
| Preview-as-published | decision badge per row | Column removed |
| DB | `campaign_result.decision`, `campaign_result.decision_reason` | Dropped by migration 076 |

## 4. Non-goals

- No replacement "final decision" concept. A funnel with several leaf stages has several
  outputs; add-from-campaign picking a stage is the answer.
- No docs/domain-model edits in this change (docs/ is gitignored); tracked separately.
- The consumer app's side of the published contract is out of scope here; flagged in the recap.
