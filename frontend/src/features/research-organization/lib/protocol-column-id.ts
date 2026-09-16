/**
 * Resolves "protocol column" string IDs to their owning protocol.
 *
 * The search flow emits a list of column tokens that name what each
 * grid column reads from the activity payload. Token shapes:
 *
 *   `drc:<readout_definition_id>`         best dose-response curve
 *                                         for that DR readout-def —
 *                                         renders one cell per
 *                                         protocol intercept (curve
 *                                         identity is by readout-def
 *                                         post migration 033 — see
 *                                         CLAUDE.md notes)
 *   `drc:<readout_definition_id>:<kind>:<level>`
 *                                         narrowed to a single
 *                                         intercept (EC50, EC90, ...).
 *                                         Emitted by the customizer
 *                                         when the chemist toggles
 *                                         individual intercepts on
 *                                         a multi-intercept DR readout.
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
import { narrowInterceptKey } from "@/features/screening-assay/lib/intercept-label";
import type { InterceptKey, Protocol } from "@/features/screening-assay/types";

// ─── Formatters (paired with the resolver below) ───────────────────────────

/** The single cross-protocol "Active in" column. Carries no protocol id. */
export const ANY_COLUMN_ID = "any";

/** Token for "the best DR curve for this readout-def" — renders one cell per
 *  protocol-declared intercept by default. */
export function drcColId(readoutDefId: string): string {
  return `drc:${readoutDefId}`;
}

/** Token narrowed to a single intercept on a DR readout-def. Use when the
 *  caller wants exactly one intercept column (e.g. user toggled EC90 on
 *  without EC50). */
export function drcInterceptColId(
  readoutDefId: string,
  key: { kind: string; level: number },
): string {
  return `drc:${readoutDefId}:${key.kind}:${key.level}`;
}

/** Token for an aggregated raw readout, scoped to a specific protocol. */
export function rdColId(protocolId: string, readoutDefId: string): string {
  return `rd:${protocolId}:${readoutDefId}`;
}

export interface ResolvedColumn {
  colId: string;
  prefix: "rd" | "drc";
  protocolId: string;
  readoutDefId: string | null;
  /** For `drc:<rd_id>:<kind>:<level>` tokens: the narrowed intercept.
   *  Null for the parent `drc:<rd_id>` token (which renders every
   *  intercept declared on the readout-def). */
  interceptKey: InterceptKey | null;
}

export function resolveColumns(protocolColumns: string[], protocols: Protocol[]): ResolvedColumn[] {
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
      // 4-segment `drc:<rd_id>:<kind>:<level>` narrows to a single intercept.
      // Anything else (including malformed 3-segment) falls back to the
      // parent so a typo still surfaces the row. The (kind, level) narrowing
      // goes through `narrowInterceptKey` (the SoT for string→InterceptKind).
      let interceptKey: InterceptKey | null = null;
      if (parts.length === 4) {
        const level = Number(parts[3]);
        if (!Number.isNaN(level)) {
          interceptKey = narrowInterceptKey({ kind: parts[2], level });
        }
      }
      resolved.push({
        colId,
        prefix,
        protocolId: proto.id,
        readoutDefId: rdId,
        interceptKey,
      });
    } else if (parts.length >= 3) {
      const protoId = parts[1];
      const rdId = parts[2];
      if (!protoId || !rdId) continue;
      resolved.push({
        colId,
        prefix,
        protocolId: protoId,
        readoutDefId: rdId,
        interceptKey: null,
      });
    } else {
      const rdId = parts[1];
      if (!rdId) continue;
      const proto = protoByRdId.get(rdId);
      if (!proto) continue;
      resolved.push({
        colId,
        prefix,
        protocolId: proto.id,
        readoutDefId: rdId,
        interceptKey: null,
      });
    }
  }

  return resolved;
}

/** Unique owning protocol IDs across a `protocol_columns` list.
 *
 *  Used by the search page to decide which protocol cards on the
 *  compound detail drawer count as "selected" (i.e. visible in the
 *  results grid) vs "also tested in N other protocols". */
export function uniqueProtocolIds(protocolColumns: string[], protocols: Protocol[]): string[] {
  return [...new Set(resolveColumns(protocolColumns, protocols).map((r) => r.protocolId))];
}

/** Expand any parent `drc:<rd_id>` token into one explicit
 *  `drc:<rd_id>:<kind>:<level>` token per intercept the protocol declares.
 *
 *  The parent token means "render every declared intercept" — convenient for
 *  storage but it makes per-intercept includes() checks awkward (the
 *  customizer needs to know that the parent implicitly covers EC50 + EC90).
 *  Expanding lets every downstream consumer do a plain `set.has(entryKey)`
 *  without special-casing parents.
 *
 *  Tokens that already carry an intercept (4-segment) pass through unchanged,
 *  as do `rd:` tokens and parents for rd-defs whose intercepts list is empty
 *  (legacy DR readouts — the parent is the only meaningful token there).
 */
export function expandParentTokens(protocolColumns: string[], protocols: Protocol[]): string[] {
  const protoByRdId = new Map<string, Protocol>();
  for (const p of protocols) {
    for (const rd of p.readout_definitions ?? []) protoByRdId.set(rd.id, p);
  }

  const out: string[] = [];
  for (const token of protocolColumns) {
    if (!token.startsWith("drc:")) {
      out.push(token);
      continue;
    }
    const parts = token.split(":");
    if (parts.length !== 2) {
      // Already narrowed (4-segment) or malformed — pass through.
      out.push(token);
      continue;
    }
    const rdId = parts[1];
    const proto = protoByRdId.get(rdId);
    const rd = proto?.readout_definitions?.find((r) => r.id === rdId);
    const intercepts = rd?.dose_response_config?.intercepts ?? [];
    if (intercepts.length === 0) {
      out.push(token);
      continue;
    }
    for (const s of intercepts) {
      // Every intercept gets a narrowed token so downstream consumers can do
      // a plain `set.has(key)` lookup. The customizer's entry keys are also
      // narrowed for the same reason.
      out.push(drcInterceptColId(rdId, s));
    }
  }
  return out;
}

/** Reduce narrowed `drc:<rd_id>:<kind>:<level>` tokens down to their parent
 *  before calling the backend.
 *
 *  The BE only needs to know *which curves to load* — it always returns
 *  every fitted intercept on each curve via `ActivityValue.intercept_values`.
 *  Sending narrowed tokens would (a) cause the BE to crash trying to parse
 *  them as a UUID, and (b) be redundant since the FE grid is what filters
 *  intercepts for display.
 */
export function toBackendProtocolColumns(protocolColumns: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const token of protocolColumns) {
    if (token.startsWith("drc:")) {
      const parts = token.split(":");
      const canonical = drcColId(parts[1] ?? "");
      if (!seen.has(canonical)) {
        seen.add(canonical);
        out.push(canonical);
      }
      continue;
    }
    if (!seen.has(token)) {
      seen.add(token);
      out.push(token);
    }
  }
  return out;
}
