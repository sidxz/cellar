import { ReferenceKind } from "@/shared/lib/api/model";
import type { ProtocolReference } from "../types";

/** Display order and labels for the kind select and the reference list. */
export const REFERENCE_KIND_LABELS: Record<ReferenceKind, string> = {
  chembl_assay: "ChEMBL assay",
  pubchem_aid: "PubChem AID",
  doi: "DOI",
  pmid: "PMID",
  url: "URL",
};

export const REFERENCE_KIND_PLACEHOLDERS: Record<ReferenceKind, string> = {
  chembl_assay: "CHEMBL1054500",
  pubchem_aid: "AID 1851",
  doi: "10.1021/jm901137j",
  pmid: "19919034",
  url: "https://…",
};

// Mirror of the backend ProtocolReference VO: same patterns, same prefix stripping. The backend
// stays the authority; this lets the UI (and CSV import) say what is wrong before a round trip.
const PATTERNS: Record<ReferenceKind, RegExp> = {
  chembl_assay: /^CHEMBL\d+$/,
  pubchem_aid: /^\d+$/,
  doi: /^10\.\d{4,9}\/\S+$/,
  pmid: /^\d+$/,
  url: /^https?:\/\/\S+$/,
};
const PREFIXES: Partial<Record<ReferenceKind, RegExp>> = {
  pubchem_aid: /^aid\s?/i,
  doi: /^(https?:\/\/doi\.org\/|doi:)/i,
};
const MAX_LENGTH = 2000;

export function isReferenceKind(kind: string): kind is ReferenceKind {
  return Object.hasOwn(ReferenceKind, kind);
}

/** Strip the kind's prefix and validate. `{ value }` when valid, else `{ error }`. */
export function normalizeReference(
  kind: string,
  raw: string,
): { value: string } | { error: string } {
  if (!isReferenceKind(kind)) return { error: `Unknown reference kind "${kind}"` };
  const value = raw.trim().replace(PREFIXES[kind] ?? /^/, "");
  if (value.length > MAX_LENGTH || !PATTERNS[kind].test(value)) {
    return { error: `Not a valid ${REFERENCE_KIND_LABELS[kind]}` };
  }
  return { value };
}

/** The stable key the API removes a reference by. */
export function referenceKey(ref: ProtocolReference): string {
  return `${ref.kind}:${ref.value}`;
}

const TEMPLATES: Record<ReferenceKind, (v: string) => string> = {
  chembl_assay: (v) => `https://www.ebi.ac.uk/chembl/explore/assay/${v}`,
  pubchem_aid: (v) => `https://pubchem.ncbi.nlm.nih.gov/bioassay/${v}`,
  doi: (v) => `https://doi.org/${v}`,
  pmid: (v) => `https://pubmed.ncbi.nlm.nih.gov/${v}`,
  url: (v) => v,
};

/** A link built only from a fixed template and a value that passes validation again here;
 *  anything else (a `javascript:` url, a tampered id) gets no href. */
export function referenceHref(ref: ProtocolReference): string | null {
  const checked = normalizeReference(ref.kind, ref.value);
  if (!("value" in checked) || checked.value !== ref.value) return null;
  return TEMPLATES[ref.kind](ref.value);
}

const PAPER_LEVEL: ReadonlySet<string> = new Set<ReferenceKind>(["doi", "pmid", "url"]);

/** References a sibling assay shares (the paper or page), not the assay ids (P7). */
export function paperLevelReferences(refs: ProtocolReference[]): ProtocolReference[] {
  return refs.filter((r) => PAPER_LEVEL.has(r.kind));
}
