# Any-protocol activity search: derived measurement catalog + "Active in" column

**Date:** 2026-09-02
**Status:** Approved design, ready for plan
**Builds on:** commit `8cef97a9` (any-protocol activity criterion: hardcoded Potency + Curve Class, no result columns)

## Problem

A chemist asks "which compounds have shown activity in any protocol?". The
criterion shipped in `8cef97a9` answers it, but:

1. The where-picker under "Any protocol" is hardcoded to two entries. It
   should be derived from what the workspace's protocols actually measure
   (IC50 in 3 protocols, EC90 in 1, "% Inhibition" in 2, ...).
2. Results show the molecule list with no activity at all. The chemist needs
   to see **which assay**, **how potent**, and **whether the curve is
   trustworthy**, without one grid column per measurement (which would fan
   out horizontally with every protocol).

## Decisions (from the design conversation)

- Filter options and result columns are independent. The picker is derived
  and may be long (it is vertical). Results get **one** column.
- The results column lists, per molecule, the protocols it was active in,
  each entry carrying the value that made it match, in the protocol's
  **native** unit, plus a curve-class dot. Best first, max 3 shown, "+N more".
- Normalize to µM only for filtering and sorting, never for display.
- No sparklines in the cell. Click opens the existing compound detail sheet
  with those protocols expanded (full plots already exist there).
- Readout grouping is by normalized name + unit. A controlled readout
  vocabulary is the durable fix; out of scope, but the grouping key must be
  swappable from string to term later.

---

## Part 1 — Derived measurement catalog

### Catalog builder (frontend, no new endpoint)

`buildAnyProtocolWhereOptions(protocols: Protocol[])` in
`features/research-organization/lib/activity-where-options.ts`. The search
form already holds full `Protocol[]` with `readout_definitions`.

Groups:

| Group | Key (option id) | Source | Label |
|---|---|---|---|
| DR intercept | `any:dr:<kind>:<level>` | every DR readout-def's `dose_response_config.intercepts` (fallback: `curve_type` → kind, level 50) | intercept label via existing `interceptLabel` + " · N protocols", unit `µM` |
| Numeric readout | `any:rd:<slug>` where slug = `normalize(name) + "|" + (unit ?? "")` | numeric readout-defs (text / pick-list excluded) | `name (unit) · N protocols` |
| Curve class | `curve_class` | unchanged | unchanged |

`normalize(name)` = lowercase, trim, collapse internal whitespace. The label
uses the first-seen original casing. Groups sort by protocol count desc,
then label. Retired: the hardcoded `potency_um` option. A saved search that
still carries a `dr_curve` condition with neither readout-def nor intercept
key renders as a read-only legacy entry "Potency (primary fit)" so it keeps
round-tripping; new rows can't pick it.

### Wire shapes (where conditions, `protocol_id: null`)

```jsonc
// DR intercept across protocols, cutoff in µM
{ "source": "dr_curve", "intercept_key": { "kind": "ic", "level": 50 },
  "operator": "lt", "value": 1.0 }

// Numeric readout across protocols, name+unit matched, native unit
{ "source": "readout_data", "readout_name": "% Inhibition", "unit": "%",
  "operator": "gt", "value": 50 }

// Legacy (kept): primary fitted value across protocols, µM
{ "source": "dr_curve", "operator": "lt", "value": 1.0 }
```

`parseWhereOptionId` / `whereConditionOptionId(cond, anyProtocol)` gain the
two new id forms. `ActivityWhereCondition` gains optional `readout_name` and
`unit`. `search-form.tsx` cleaning: an any-protocol `readout_data` row is
valid when `readout_name` is set.

### Backend (`_activity_query.py`)

When `protocol_id` is None:

- `dr_curve` + `intercept_key`, no readout-def → value expression is
  `_jsonb_intercept_value(kind, level)` (already exists; curves store the
  primary in `intercept_values` too, so one path serves IC50 and EC90).
  Normalized to µM by generalizing `_fitted_value_micromolar()` into
  `_to_micromolar(expr)` (same CASE over `ConcentrationUnit`, mg/mL via MW).
- `dr_curve`, no readout-def, no intercept key → existing primary
  `fitted_value` path (legacy compat).
- `readout_data` + `readout_name`, no readout-def → join
  `ReadoutDefinitionModel`; match
  `lower(btrim(regexp_replace(name, '\s+', ' ', 'g'))) = normalize(readout_name)`
  and `coalesce(unit, '') = coalesce(cond.unit, '')`; filter
  `value_numeric` with the operator; `is_outlier = false`. No unit
  conversion (unit is part of identity).
- `readout_data` with neither readout-def nor `readout_name` → `ValueError`.

Everything with a `protocol_id` is unchanged.

### Tests

- `tests/unit/test_search_query_composer.py`: three new shapes compile with
  the expected joins/CASE; the rejection.
- `tests/api/test_search.py`: seed protocol A (µM, IC50 + EC90 intercepts)
  and protocol B (nM, IC50); "any IC50 < 1 µM" finds via B only; "any EC90
  < 10 µM" finds via A; two protocols with a "% Inhibition" (%) readout,
  "any % Inhibition > 50" finds the molecule that crosses in either.
- `activity-where-options.test.ts`: catalog grouping, counts, sort, id
  round-trips, legacy fallback.

---

## Part 2 — "Active in" results column

### Contract

New `protocol_columns` token: the literal `any`. The frontend sends it
whenever the query contains an any-protocol activity criterion. Per-protocol
rows keep contributing their own `drc:`/`rd:` tokens; both can coexist.

`activity_data[molecule_id]["any"]` is an `AnyProtocolActivity`:

```python
@dataclass(frozen=True)
class AnyProtocolEntry:
    protocol_id: UUID
    protocol_name: str
    protocol_type: str
    target_names: list[str]        # effective targets, lightweight
    label: str                     # "IC50", "EC90", "% Inhibition"
    source: str                    # "dose_response" | "readout"
    readout_definition_id: UUID
    value: float | None            # native unit
    qualifier: str | None
    unit: str | None               # native unit (protocol dose_unit for DR)
    value_um: float | None         # normalized; None for readouts / mg/mL w/o MW
    curve_class: str | None        # DR only
    run_count: int

@dataclass(frozen=True)
class AnyProtocolActivity:
    entries: list[AnyProtocolEntry]   # sorted value_um asc nulls last, then label
```

Domain types live next to `ActivityValue` in
`domain/screening_assay/activity_types.py`.

### What goes in `entries`

- One entry per (protocol, DR readout-def) where the molecule has curves,
  using the existing multi-run aggregation (`_build_dr_activity` with the
  request's selection rule) and the primary intercept. Fetched with
  `find_all_curves_for_molecules(..., readout_definition_ids=None)` which
  already returns everything.
- If the query's any-protocol criterion names numeric readout groups
  (`readout_name` conditions), one entry per (protocol, readout-def) in that
  group via a new reader method
  `find_aggregated_by_molecules_and_names(workspace_id, molecule_ids, [(normalized_name, unit)])`.
  Presence-only and curve-class-only searches list DR entries only.
- Curve-class `inactive` entries are included (the search may be
  presence-only, where "tested in" is the honest reading) and the cell greys
  them.

### Sorting

`sort_by = "any"` → `_apply_any_sort` in `molecule_reader.py`, mirroring
`_apply_drc_sort`: order by the molecule's minimum µM-normalized primary
`fitted_value` across all its curves (same unit CASE, correlated subquery),
nulls last.

### Frontend

- `search-form.tsx` `deriveProtocolColumns`: any-protocol criterion → push
  `"any"` (replaces the current "derive nothing" ponytail ceiling).
- `lib/protocol-column-id.ts` `resolveColumns`: recognise `any` so
  `uniqueProtocolIds` ignores it and the grid gets a resolved entry.
- `results-grid.tsx`: token `any` → one column, header "Active in", server
  sort key `any`, ~20rem, no group header. New `ActiveInCell`:
  - up to 3 rows: `protocol_name` · `label` · `value unit` · class dot
    (full green, partial amber, bell-shaped/inactive grey, none for readouts)
  - "+N more" when entries exceed 3
  - inactive entries in muted text
  - the row's target chip only when the protocol has exactly one target
    (keeps the cell narrow)
- `search-page.tsx`: on row click, `visibleProtocolIds` for the sheet =
  existing per-protocol column ids ∪ the clicked row's `any` entry protocol
  ids, so those groups expand with full plots and the rest stay collapsed.
- Types: follow how `ActivityValue` is typed on the FE today (activity_data
  is `dict[str, Any]` in OpenAPI, so orval emits nothing for it); alias, do
  not redefine, if a generated shape exists.
- Export (`row_streams/search_results.py`, excel/pdf renderers): the `any`
  column renders as `"<protocol>: <label> <value> <unit>; ..."` text. Must
  not crash on the new token.

### Tests

- Backend unit: enrichment with token `any` builds sorted entries across two
  protocols (µM + nM) and includes a readout entry only when the criterion
  names it.
- API: `protocol_columns: ["any"]` returns entries; `sort_by=any` orders by
  best µM.
- FE: `ActiveInCell` renders 3 + "+N", greys inactive; `deriveProtocolColumns`
  emits `any`; `resolveColumns` tolerates it.

---

## Out of scope

- Protocol-type exclusion ("ignore cytotoxicity/ADMET"). Noted as a likely
  follow-up once chemists use the column.
- Readout controlled vocabulary.
- Sparklines inside the cell.
- The COX-2 / EGFR seed data whose DR readout unit says nM while the
  protocol dose unit says µM (fitted values look like nM). Separate ticket:
  find where the import wrote them.

## Order

Part 1 first: Part 2's entry labels and the catalog's option ids share the
same intercept/readout grouping helpers.
