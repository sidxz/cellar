/**
 * Where-clause option builder for the Activity criterion in /search.
 *
 * The picker surfaces every filterable dimension a chemist has on a
 * protocol's screening data:
 *
 *   - One entry per intercept of each DR readout-def (EC50, EC90, IC10, ...)
 *     — so a protocol that fits both EC50 and EC90 from the same Hill curve
 *     shows up as two separate where options, not one.
 *   - One entry per raw / numeric readout-def.
 *   - One "Curve Class" entry per protocol (when the protocol has at least
 *     one DR readout-def) — filters dose_response_curves.curve_class against
 *     a chemist-picked subset of classes.
 *
 * No hardcoded labels: intercept names come from `dose_response_config.intercepts`
 * via {@link interceptLabel}; curve-class labels come from
 * `CURVE_CLASS_LABELS`; readout names come from `protocol.readout_definitions`.
 *
 * Mirrors the pattern in `screening-assay/lib/hit-criteria-options.ts`: the
 * primary intercept of a DR readout serializes with `intercept_key=null` so
 * legacy saved searches keep round-tripping unchanged; only secondary
 * intercepts persist an explicit `{kind, level}` key.
 */
import {
  interceptOptionLabel,
  narrowInterceptKey,
} from "@/features/screening-assay/lib/intercept-label";
import {
  CURVE_CLASS_LABELS,
  type CurveClass,
  type Protocol,
} from "@/features/screening-assay/types";
import type { ActivityWhereCondition, ActivityWhereSource, InterceptKey } from "../types";

/** Group heading in the picker — kept here so the section component doesn't
 *  carry chemistry vocabulary directly. */
export type WhereOptionGroup = "dose_response" | "numeric_readout" | "curve_class";

export interface WhereOption {
  /** Stable picker value: parseable via {@link parseWhereOptionId}. */
  id: string;
  /** Chemist-facing label. */
  label: string;
  /** Optional unit suffix appended to the label by callers. */
  unit?: string | null;
  /** Drives the where-condition `source` slot. */
  source: ActivityWhereSource;
  /** For DR options: the readout-def id. Empty for ``curve_class`` (which
   *  spans every DR curve in scope). */
  readout_definition_id: string;
  /** For DR options on secondary intercepts: the (kind, level) tag. Null
   *  for the *primary* intercept of a DR readout, for numeric readouts,
   *  and for the curve-class entry. */
  intercept_key: InterceptKey | null;
  /** Which section heading the picker should render this under. */
  group: WhereOptionGroup;
}

/** All allowed curve classes, derived from the FE union/labels map so the
 *  set stays in sync with the domain enum. */
export const CURVE_CLASS_OPTIONS: ReadonlyArray<{ value: CurveClass; label: string }> = (
  Object.keys(CURVE_CLASS_LABELS) as CurveClass[]
).map((value) => ({
  value,
  label: CURVE_CLASS_LABELS[value],
}));

/** Build the picker option list for a protocol. Returns an empty list if
 *  the protocol hasn't loaded yet so the row renders a placeholder. */
export function buildActivityWhereOptions(protocol: Protocol | undefined): WhereOption[] {
  const out: WhereOption[] = [];
  if (!protocol?.readout_definitions) return out;

  let hasAnyDr = false;
  for (const rd of protocol.readout_definitions) {
    const dr = rd.dose_response_config;
    if (dr) {
      hasAnyDr = true;
      const specs = dr.intercepts ?? [];
      if (specs.length === 0) {
        // Legacy DR readout with no declared intercepts — fall back to the
        // headline curve_type so the chemist still gets one option per DR
        // readout-def even on un-migrated protocols.
        out.push({
          id: drOptionId(rd.id, null),
          label: `${rd.name} (${dr.curve_type.toUpperCase()})`,
          unit: rd.unit,
          source: "dr_curve",
          readout_definition_id: rd.id,
          intercept_key: null,
          group: "dose_response",
        });
        continue;
      }
      const primary = specs[0];
      for (let i = 0; i < specs.length; i++) {
        const s = specs[i];
        const isPrimary = i === 0;
        out.push({
          id: drOptionId(rd.id, isPrimary ? null : { kind: s.kind, level: s.level }),
          // Dedupe-aware label: "EC50" readout + EC90 intercept reads as
          // "EC90", not "EC50 EC90". See `interceptOptionLabel`.
          label: interceptOptionLabel(rd.name, primary, s),
          unit: rd.unit,
          source: "dr_curve",
          readout_definition_id: rd.id,
          // Primary stays unkeyed so a saved search survives an intercept
          // relabel and so legacy criteria don't grow an intercept_key just
          // by being re-saved.
          intercept_key: isPrimary ? null : { kind: s.kind, level: s.level },
          group: "dose_response",
        });
      }
    } else if (rd.data_type === "numeric") {
      out.push({
        id: numericOptionId(rd.id),
        label: rd.name,
        unit: rd.unit,
        source: "readout_data",
        readout_definition_id: rd.id,
        intercept_key: null,
        group: "numeric_readout",
      });
    }
  }

  if (hasAnyDr) out.push(CURVE_CLASS_OPTION);

  return out;
}

export const CURVE_CLASS_OPTION_ID = "curve_class";
/** Any-protocol only: primary fitted value of any DR curve, normalized to µM
 *  server-side via each protocol's dose_unit. Serializes as a ``dr_curve``
 *  condition with no readout-def. */
export const POTENCY_UM_OPTION_ID = "potency_um";

const CURVE_CLASS_OPTION: WhereOption = {
  id: CURVE_CLASS_OPTION_ID,
  label: "Curve Class",
  unit: null,
  source: "curve_class",
  readout_definition_id: "",
  intercept_key: null,
  group: "curve_class",
};

/** Picker options for an "Any protocol" row — the only dimensions that are
 *  comparable across protocols. */
export function buildAnyProtocolWhereOptions(): WhereOption[] {
  return [
    {
      id: POTENCY_UM_OPTION_ID,
      label: "Potency (IC50 / EC50)",
      unit: "µM",
      source: "dr_curve",
      readout_definition_id: "",
      intercept_key: null,
      group: "dose_response",
    },
    CURVE_CLASS_OPTION,
  ];
}

function drOptionId(rdId: string, key: InterceptKey | null): string {
  if (!key) return `dr_curve:${rdId}`;
  return `dr_curve:${rdId}:${key.kind}:${key.level}`;
}

function numericOptionId(rdId: string): string {
  return `readout_data:${rdId}`;
}

/** Reverse the picker id back into a where-condition seed. Returns null
 *  when the id is unrecognised (defensive — e.g. saved-search shape from
 *  a future schema). */
export function parseWhereOptionId(
  id: string,
): Pick<ActivityWhereCondition, "source" | "readout_definition_id" | "intercept_key"> | null {
  if (id === CURVE_CLASS_OPTION_ID) {
    return { source: "curve_class", readout_definition_id: "", intercept_key: null };
  }
  if (id === POTENCY_UM_OPTION_ID) {
    return { source: "dr_curve", readout_definition_id: "", intercept_key: null };
  }
  const parts = id.split(":");
  if (parts.length < 2) return null;
  const src = parts[0];
  if (src === "dr_curve") {
    const rdId = parts[1];
    if (parts.length === 2) {
      return { source: "dr_curve", readout_definition_id: rdId, intercept_key: null };
    }
    if (parts.length === 4) {
      const level = Number(parts[3]);
      if (Number.isNaN(level)) return null;
      const intercept_key = narrowInterceptKey({ kind: parts[2], level });
      if (!intercept_key) return null;
      return {
        source: "dr_curve",
        readout_definition_id: rdId,
        intercept_key,
      };
    }
    return null;
  }
  if (src === "readout_data") {
    return {
      source: "readout_data",
      readout_definition_id: parts[1],
      intercept_key: null,
    };
  }
  return null;
}

/** Inverse of `parseWhereOptionId`: given a saved where-condition, find
 *  the option id that should be highlighted in the picker. Returns an
 *  empty string when no readout-def is set (fresh row) — except on an
 *  any-protocol row, where a readout-def-less ``dr_curve`` *is* the
 *  potency option. */
export function whereConditionOptionId(cond: ActivityWhereCondition, anyProtocol = false): string {
  if (cond.source === "curve_class") return CURVE_CLASS_OPTION_ID;
  if (!cond.readout_definition_id) {
    return anyProtocol && cond.source === "dr_curve" ? POTENCY_UM_OPTION_ID : "";
  }
  if (cond.source === "readout_data") return numericOptionId(cond.readout_definition_id);
  return drOptionId(cond.readout_definition_id, cond.intercept_key ?? null);
}
