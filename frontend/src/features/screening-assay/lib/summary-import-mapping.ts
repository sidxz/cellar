import type {
  SummaryColumnMapping,
  SummaryHeaderSuggestionModel,
  SummaryRole,
} from "../hooks/use-summary-import";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SummaryMappingDraft {
  // role per header
  roles: Record<string, SummaryRole>;
  // header → readout_definition_id, only for headers with role=readout
  readoutDefByHeader: Record<string, string>;
}

// ─── Seed from backend suggestions ───────────────────────────────────────────

/**
 * Build an initial SummaryMappingDraft from the backend's header-inference
 * output. ``readout_definition_id`` is set when the header's normalized name
 * matched a protocol-defined readout; a readout suggestion without a bound def
 * is left unbound for the user to resolve.
 */
export function suggestionsToDraft(
  suggestions: SummaryHeaderSuggestionModel[],
): SummaryMappingDraft {
  const roles: Record<string, SummaryRole> = {};
  const readoutDefByHeader: Record<string, string> = {};
  for (const s of suggestions) {
    const role = s.role as SummaryRole;
    roles[s.header] = role;
    if (role === "readout" && s.readout_definition_id) {
      readoutDefByHeader[s.header] = s.readout_definition_id;
    }
  }
  return { roles, readoutDefByHeader };
}

// ─── Build request mapping ────────────────────────────────────────────────────

/**
 * Build the import request mapping from a draft, or ``null`` if the draft is
 * invalid:
 *  - a header with role=readout has no bound readout_definition_id, OR
 *  - neither a compound_ref nor a batch_ref column is assigned, OR
 *  - there are zero readout columns.
 */
export function buildMapping(draft: SummaryMappingDraft): SummaryColumnMapping | null {
  let compoundRef: string | null = null;
  let batchRef: string | null = null;
  const readoutColumns: Record<string, string> = {};

  for (const [header, role] of Object.entries(draft.roles)) {
    if (role === "compound_ref") {
      if (compoundRef === null) compoundRef = header;
    } else if (role === "batch_ref") {
      if (batchRef === null) batchRef = header;
    } else if (role === "readout") {
      const defId = draft.readoutDefByHeader[header];
      if (!defId) return null;
      readoutColumns[header] = defId;
    }
  }

  if (compoundRef === null && batchRef === null) return null;
  if (Object.keys(readoutColumns).length === 0) return null;

  return {
    compound_ref: compoundRef,
    batch_ref: batchRef,
    readout_columns: readoutColumns,
  };
}
