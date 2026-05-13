import type { HeaderSuggestion, ImportRole, RunImportTemplate } from "../hooks/use-run-import";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface MappingDraft {
  // role per header (null = unassigned/ignore)
  roles: Record<string, ImportRole | null>;
  // header → readout_definition_id, only for headers with role=readout
  readoutDefByHeader: Record<string, string>;
  acknowledgedLowConfidence: boolean;
}

// ─── Factories ───────────────────────────────────────────────────────────────

export function emptyDraft(): MappingDraft {
  return {
    roles: {},
    readoutDefByHeader: {},
    acknowledgedLowConfidence: false,
  };
}

// ─── Seed from backend suggestions ───────────────────────────────────────────

/**
 * Build an initial MappingDraft from the backend's header-inference output.
 * ``readout_definition_id`` is set when the header's normalized name matched
 * a protocol-defined readout; the FE doesn't need its own auto-bind heuristic.
 */
export function suggestionToInitialDraft(suggestions: HeaderSuggestion[]): MappingDraft {
  const roles: Record<string, ImportRole | null> = {};
  const readoutDefByHeader: Record<string, string> = {};
  for (const s of suggestions) {
    roles[s.header] = s.role;
    if (s.role === "readout" && s.readout_definition_id) {
      readoutDefByHeader[s.header] = s.readout_definition_id;
    }
  }
  return {
    roles,
    readoutDefByHeader,
    acknowledgedLowConfidence: false,
  };
}

// ─── Template application ─────────────────────────────────────────────────────

/**
 * Overlay a saved template onto an existing draft, restricting to headers
 * that are actually present in the file being imported.
 */
export function applyTemplateToDraft(
  draft: MappingDraft,
  template: RunImportTemplate,
  headers: string[],
): MappingDraft {
  const next: MappingDraft = {
    ...draft,
    roles: { ...draft.roles },
  };
  const mapping = template.column_mapping as Record<string, unknown>;
  const setIfPresent = (header: unknown, role: ImportRole) => {
    if (typeof header === "string" && headers.includes(header)) {
      next.roles[header] = role;
    }
  };
  setIfPresent(mapping.well, "well");
  setIfPresent(mapping.plate_name, "plate_name");
  setIfPresent(mapping.concentration, "concentration");
  setIfPresent(mapping.batch_ref, "batch_ref");
  setIfPresent(mapping.compound_ref, "compound_ref");
  if (Array.isArray(mapping.readout_headers)) {
    for (const h of mapping.readout_headers) {
      if (typeof h === "string" && headers.includes(h)) {
        next.roles[h] = "readout";
      }
    }
  }
  return next;
}

// ─── Template scoring / selection ─────────────────────────────────────────────

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function scoreTemplate(t: RunImportTemplate, headerSet: Set<string>): number {
  const m = t.column_mapping as Record<string, unknown>;
  const refs: string[] = [];
  for (const [k, v] of Object.entries(m)) {
    if (k === "readout_headers" && Array.isArray(v)) {
      refs.push(...v.filter((x): x is string => typeof x === "string"));
    } else if (typeof v === "string" && v) {
      refs.push(v);
    }
  }
  if (refs.length === 0) return 0;
  if (typeof m.well === "string" && !headerSet.has(normalize(m.well))) return 0;
  const hits = refs.filter((r) => headerSet.has(normalize(r))).length;
  return hits / refs.length;
}

/**
 * Return the best-matching template for the given set of file headers, or
 * null if no template scores at least 0.7 (i.e. 70 % header overlap).
 */
export function pickBestTemplate(
  templates: RunImportTemplate[],
  headers: string[],
): RunImportTemplate | null {
  let best: RunImportTemplate | null = null;
  let bestScore = 0;
  const headerSet = new Set(headers.map((h) => normalize(h)));
  for (const t of templates) {
    const score = scoreTemplate(t, headerSet);
    if (score > bestScore) {
      bestScore = score;
      best = t;
    }
  }
  return bestScore >= 0.7 ? best : null;
}
