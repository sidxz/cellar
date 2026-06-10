/**
 * Activity color spec for the SAR R-group table.
 *
 * `SarColorSpec` names one (protocol, readout/intercept) pair — the single
 * readout the R-group heatmap colors by. `whereOptionToColorSpec` converts a
 * picker `WhereOption` into this shape; `colorSpecScalar` extracts the numeric
 * value from an `ActivityValue` cell.
 */
import type { WhereOption } from "@/features/research-organization/lib/activity-where-options";
import { drcColId, rdColId } from "@/features/research-organization/lib/protocol-column-id";
import type { ActivityValue } from "@/features/research-organization/types";
import type { InterceptKey } from "@/features/research-organization/types";
import { findInterceptValue } from "@/features/screening-assay/lib/intercept-label";

// ─── Type ─────────────────────────────────────────────────────────────────────

export interface SarColorSpec {
  protocolId: string;
  /** Activity_data column key: `drc:<rd>` or `rd:<proto>:<rd>`. */
  column: string;
  /** DR: which intercept's scalar (null = primary → av.value). */
  interceptKey: InterceptKey | null;
  source: "dr_curve" | "readout_data";
  /** Chemist-facing label, e.g. "EGFR · IC50". */
  label: string;
}

// ─── Pure functions ───────────────────────────────────────────────────────────

/**
 * Build a `SarColorSpec` from a protocol + a `WhereOption` from the activity
 * picker. Mirrors the column-id convention used by the search grid so the
 * color lookup uses the same key as the activity_data map.
 */
export function whereOptionToColorSpec(
  protocolId: string,
  protocolName: string,
  opt: WhereOption,
): SarColorSpec {
  const column =
    opt.source === "readout_data"
      ? rdColId(protocolId, opt.readout_definition_id)
      : drcColId(opt.readout_definition_id);

  return {
    protocolId,
    column,
    interceptKey: opt.intercept_key,
    source: opt.source === "readout_data" ? "readout_data" : "dr_curve",
    label: `${protocolName} · ${opt.label}`,
  };
}

/**
 * Extract the single scalar value that `spec` names from an `ActivityValue`
 * cell. Returns null when the cell is absent or the intercept hasn't been fit.
 *
 * - `interceptKey === null` → primary scalar (`av.value`).
 * - Otherwise → look up the intercept in `av.intercept_values` via
 *   `findInterceptValue`, which matches on `(kind, level)` only (survives
 *   label renames). The `InterceptSpec` arg needs a `basis` field; we default
 *   to `"relative_percent"` because `findInterceptValue` never uses `basis` in
 *   its match predicate — it compares only `kind` and `level`.
 */
export function colorSpecScalar(av: ActivityValue | undefined, spec: SarColorSpec): number | null {
  if (!av) return null;

  if (spec.interceptKey) {
    const interceptSpec = {
      kind: spec.interceptKey.kind,
      level: spec.interceptKey.level,
      // findInterceptValue matches on (kind, level) only — basis is required
      // by InterceptSpec but never used in the predicate.
      basis: "relative_percent" as const,
    };
    const iv = findInterceptValue(av.intercept_values as never, interceptSpec);
    return iv?.value ?? null;
  }

  return av.value ?? null;
}
