/**
 * Build the per-protocol "Readouts" entry list shown by the search-page
 * Customize Report panel.
 *
 * Returns one entry per intercept for DR readouts (so a readout with EC50 +
 * EC90 surfaces as two entries) and one entry per numeric readout. Each
 * entry's ``key`` is the actual grid column-id token, so the customizer's
 * check-state lines up with whatever's already in `protocol_columns`
 * regardless of which surface emitted it (search filter, default columns,
 * or the customizer itself).
 *
 * Token shapes mirror {@link ResolvedColumn}:
 *   - `drc:<rd_id>`                       — DR primary intercept
 *   - `drc:<rd_id>:<kind>:<level>`        — DR secondary intercept (EC90, …)
 *   - `rd:<protocol_id>:<rd_id>`          — raw numeric readout
 */
import { interceptOptionLabel } from "@/features/screening-assay/lib/intercept-label";
import type { Protocol } from "@/features/screening-assay/types";
import { drcColId, drcInterceptColId, rdColId } from "./protocol-column-id";

export interface ReadoutCustomizerEntry {
  /** Full grid column-id token — also the entry's checkbox key. */
  key: string;
  /** Chemist-facing label rendered in the customizer panel. */
  label: string;
}

/**
 * Replace the tokens belonging to one protocol's readout entries with a new
 * set, while preserving every other token's order. Used by the customizer's
 * toggle handler to mutate the global `protocol_columns` SoT.
 *
 * - ``ownedKeys`` is the full set of entry keys for the protocol being edited.
 * - ``nextOwned`` is the new (subset) selection inside that set.
 * - Tokens not in ``ownedKeys`` are left exactly where they were.
 * - New tokens (in ``nextOwned`` but not previously in the list) get appended.
 */
export function replaceProtocolEntries(
  current: string[],
  ownedKeys: Set<string>,
  nextOwned: string[],
): string[] {
  const nextSet = new Set(nextOwned);
  const out: string[] = [];
  for (const t of current) {
    if (ownedKeys.has(t)) {
      if (nextSet.has(t)) out.push(t);
      continue;
    }
    out.push(t);
  }
  for (const t of nextOwned) {
    if (!out.includes(t)) out.push(t);
  }
  return out;
}

export function buildReadoutCustomizerEntries(
  protocol: Protocol | undefined,
  protocolId: string,
): ReadoutCustomizerEntry[] {
  const entries: ReadoutCustomizerEntry[] = [];
  if (!protocol?.readout_definitions) return entries;

  for (const rd of protocol.readout_definitions) {
    const dr = rd.dose_response_config;
    if (dr) {
      const specs = dr.intercepts ?? [];
      if (specs.length === 0) {
        // Legacy DR readout with no declared intercepts — one parent entry.
        entries.push({
          key: drcColId(rd.id),
          label: rd.name + (rd.unit ? ` (${rd.unit})` : ""),
        });
        continue;
      }
      const primary = specs[0];
      for (let i = 0; i < specs.length; i++) {
        const s = specs[i];
        // Every intercept entry uses the narrowed 4-segment token so the
        // customizer can do a plain `set.has(key)` check without parent-
        // awareness. Callers expand any incoming parent `drc:<rd>` token to
        // the full set of narrowed tokens via `expandParentTokens` before
        // computing check-state.
        const key = drcInterceptColId(rd.id, s);
        const label = interceptOptionLabel(rd.name, primary, s);
        entries.push({
          key,
          label: rd.unit ? `${label} (${rd.unit})` : label,
        });
      }
    } else if (rd.data_type === "numeric") {
      entries.push({
        key: rdColId(protocolId, rd.id),
        label: rd.name + (rd.unit ? ` (${rd.unit})` : ""),
      });
    }
  }
  return entries;
}
