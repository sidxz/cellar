/**
 * Resolves "protocol column" string IDs to their owning protocol.
 *
 * The search flow emits a list of column tokens that name what each
 * grid column reads from the activity payload. Token shapes:
 *
 *   `drc:<readout_definition_id>`         best dose-response curve
 *                                         for that DR readout-def
 *                                         (curve identity is by
 *                                         readout-def post migration
 *                                         033 — see CLAUDE.md notes)
 *   `rd:<protocol_id>:<readout_def_id>`   aggregated raw readout,
 *                                         protocol-scoped
 *   `rd:<protocol_id>:<readout_def_id>:<normalization>`
 *                                         same, viewing a named
 *                                         normalization layer
 *                                         (e.g. percent_inhibition)
 *   `rd:<readout_definition_id>`          aggregated raw readout,
 *                                         legacy/unscoped — caller
 *                                         supplies protocol lookup
 *
 * `parts[1]` is NOT a reliable proto_id key on these tokens — drc:
 * carries an rd_id, not a proto_id. Use {@link resolveColumns} to
 * look the owning protocol up via a reverse readout-def index.
 *
 * Spec: `docs/superpowers/specs/2026-05-13-dynamic-intercept-columns-design.md`
 */
import type { Protocol } from "@/features/screening-assay/types";

export interface ResolvedColumn {
  colId: string;
  prefix: "rd" | "drc";
  protocolId: string;
  readoutDefId: string | null;
}

export function resolveColumns(
  protocolColumns: string[],
  protocols: Protocol[],
): ResolvedColumn[] {
  // Build a reverse index so 2-segment colIds (drc:<rd_id> or legacy
  // rd:<rd_id>) can find their owning protocol.
  const protoByRdId = new Map<string, Protocol>();
  for (const p of protocols) {
    for (const rd of p.readout_definitions ?? []) {
      protoByRdId.set(rd.id, p);
    }
  }

  const resolved: ResolvedColumn[] = [];
  for (const colId of protocolColumns) {
    const parts = colId.split(":");
    const prefix = parts[0];
    if (prefix !== "rd" && prefix !== "drc") continue;

    if (prefix === "drc") {
      const rdId = parts[1];
      if (!rdId) continue;
      const proto = protoByRdId.get(rdId);
      if (!proto) continue;
      resolved.push({ colId, prefix, protocolId: proto.id, readoutDefId: rdId });
    } else if (parts.length >= 3) {
      const protoId = parts[1];
      const rdId = parts[2];
      if (!protoId || !rdId) continue;
      resolved.push({ colId, prefix, protocolId: protoId, readoutDefId: rdId });
    } else {
      const rdId = parts[1];
      if (!rdId) continue;
      const proto = protoByRdId.get(rdId);
      if (!proto) continue;
      resolved.push({ colId, prefix, protocolId: proto.id, readoutDefId: rdId });
    }
  }

  return resolved;
}

/** Unique owning protocol IDs across a `protocol_columns` list.
 *
 *  Used by the search page to decide which protocol cards on the
 *  compound detail drawer count as "selected" (i.e. visible in the
 *  results grid) vs "also tested in N other protocols". */
export function uniqueProtocolIds(
  protocolColumns: string[],
  protocols: Protocol[],
): string[] {
  return [...new Set(resolveColumns(protocolColumns, protocols).map((r) => r.protocolId))];
}
