/** Helpers for run conditions — the protocol-declared run-time variables
 *  stored on a Run as a flat `{ name: "value" }` map.
 *
 *  Storage convention (set at run creation, must be preserved on edit): when a
 *  ConditionDefinition declares a unit, it is appended to the value with a
 *  single space — e.g. `{ "ATP": "10 uM" }`. The bare value (`10`) is what the
 *  edit inputs hold, so reads strip the unit and writes re-append it. Doing the
 *  strip on the write side too makes `buildConditionsPayload` idempotent: a
 *  value that already carries the unit won't be doubled to `"10 uM uM"`.
 */

import type { ConditionDefinition } from "../types";

/** Strip a trailing ` <unit>` from a stored condition value to recover the bare
 *  value for an input. No-op when there's no unit or the value doesn't end with
 *  it. */
export function parseConditionValue(stored: string, unit: string | null | undefined): string {
  const u = unit?.trim();
  if (!u) return stored;
  const suffix = ` ${u}`;
  return stored.endsWith(suffix) ? stored.slice(0, -suffix.length) : stored;
}

/** Build the stored conditions map from a list of definitions and a name→bare
 *  value map. Empty values are skipped; a declared unit is appended (idempotently).
 *  Returns null when nothing was recorded, matching the run's "no conditions" state. */
export function buildConditionsPayload(
  defs: ConditionDefinition[],
  values: Record<string, string>,
): Record<string, string> | null {
  const out: Record<string, string> = {};
  for (const cd of defs) {
    const raw = (values[cd.name] ?? "").trim();
    if (!raw) continue;
    const unit = cd.unit?.trim();
    const bare = parseConditionValue(raw, unit);
    out[cd.name] = unit ? `${bare} ${unit}` : bare;
  }
  return Object.keys(out).length > 0 ? out : null;
}

/** A single condition for display — key + already-formatted value (unit inline). */
export interface ConditionEntry {
  key: string;
  value: string;
}

/** Flatten a run's conditions map into ordered display entries, dropping empty
 *  values. Accepts the loose `Record<string, unknown>` shape the Run type carries
 *  (values may be numbers/strings depending on origin, e.g. CDD import). */
export function formatConditionEntries(
  conditions: Record<string, unknown> | null | undefined,
): ConditionEntry[] {
  if (!conditions) return [];
  return Object.entries(conditions)
    .filter(([, v]) => v != null && String(v).trim() !== "")
    .map(([key, v]) => ({ key, value: String(v) }));
}

/** A synthetic ConditionDefinition for a key present on a run but not declared
 *  on the protocol (e.g. imported data, or a definition removed after the run
 *  was created). Rendered as a plain text field so the value stays editable and
 *  is never silently dropped on save. */
export function syntheticDefForKey(key: string): ConditionDefinition {
  return {
    id: `__extra__:${key}`,
    name: key,
    data_type: "text",
    unit: null,
    pick_list_values: null,
  };
}

/** The set of condition fields to edit: every protocol definition, followed by
 *  any keys already on the run that no definition covers (as text fields). Order
 *  is stable — declared fields first, extras in their stored order. */
export function editableConditionDefs(
  defs: ConditionDefinition[],
  conditions: Record<string, unknown> | null | undefined,
): ConditionDefinition[] {
  const declared = new Set(defs.map((d) => d.name));
  const extras = formatConditionEntries(conditions)
    .filter((e) => !declared.has(e.key))
    .map((e) => syntheticDefForKey(e.key));
  return [...defs, ...extras];
}

/** Seed a name→bare-value map from a run's stored conditions, stripping declared
 *  units so the inputs show the bare value. Keys not in `defs` are passed through
 *  verbatim (no unit to strip). */
export function seedConditionValues(
  defs: ConditionDefinition[],
  conditions: Record<string, unknown> | null | undefined,
): Record<string, string> {
  const unitByName = new Map(defs.map((d) => [d.name, d.unit]));
  const out: Record<string, string> = {};
  for (const { key, value } of formatConditionEntries(conditions)) {
    out[key] = parseConditionValue(value, unitByName.get(key));
  }
  return out;
}

// ─── Dynamic grid columns ───────────────────────────────────────────────────────

export type ConditionColumnType = "numeric" | "text";

/** One dynamically-derived condition column for the runs grid. */
export interface ConditionColumnSpec {
  /** The stored conditions-map key this column reads. */
  key: string;
  /** Header label (without unit; numeric columns append the unit in the header). */
  label: string;
  unit: string | null;
  type: ConditionColumnType;
}

/** Derive the condition columns for a set of runs: one per variable that at
 *  least one run actually records. Declared definitions come first in their
 *  declared order, then any keys present on runs but not declared (e.g. imported
 *  data) in first-seen order. Numeric definitions become numeric columns (so the
 *  grid sorts/filters them as numbers); everything else is text. */
export function deriveConditionColumns(
  runs: { conditions?: Record<string, unknown> | null }[] | undefined,
  defs: ConditionDefinition[],
): ConditionColumnSpec[] {
  if (!runs || runs.length === 0) return [];

  const present = new Set<string>();
  const firstSeen: string[] = [];
  for (const run of runs) {
    for (const { key } of formatConditionEntries(run.conditions)) {
      if (!present.has(key)) {
        present.add(key);
        firstSeen.push(key);
      }
    }
  }
  if (present.size === 0) return [];

  const declaredNames = new Set(defs.map((d) => d.name));
  const declared = defs
    .filter((d) => present.has(d.name))
    .map<ConditionColumnSpec>((d) => ({
      key: d.name,
      label: d.name,
      unit: d.unit,
      type: d.data_type === "numeric" ? "numeric" : "text",
    }));
  const extras = firstSeen
    .filter((k) => !declaredNames.has(k))
    .map<ConditionColumnSpec>((k) => ({ key: k, label: k, unit: null, type: "text" }));

  return [...declared, ...extras];
}

/** Read a run's value for one condition column, typed for sort/filter. Numeric
 *  columns return a parsed number (null when missing or non-numeric); text
 *  columns return the raw string (null when missing/blank). */
export function readConditionCell(
  conditions: Record<string, unknown> | null | undefined,
  spec: ConditionColumnSpec,
): number | string | null {
  const raw = conditions?.[spec.key];
  if (raw == null || String(raw).trim() === "") return null;
  if (spec.type === "numeric") {
    const n = Number(parseConditionValue(String(raw), spec.unit));
    return Number.isFinite(n) ? n : null;
  }
  return String(raw);
}
