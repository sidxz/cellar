import { PROTOCOL_STATUS_LABELS, PROTOCOL_TYPE_LABELS, type Protocol } from "../types";

export type FacetDimension =
  | "type"
  | "target"
  | "category"
  | "assay_format"
  | "detection"
  | "organism"
  | "status"
  | "readout_kind";

export type GroupBy = "target" | "category" | "type" | "assay_format" | "status" | "none";

export interface FacetItem {
  value: string;
  label: string;
}

export type FacetSelections = Partial<Record<FacetDimension, Set<string>>>;

/** Sidebar render order + display labels. */
export const FACET_DIMENSIONS: { dimension: FacetDimension; label: string }[] = [
  { dimension: "type", label: "Type" },
  { dimension: "target", label: "Target" },
  { dimension: "category", label: "Category" },
  { dimension: "assay_format", label: "Assay format" },
  { dimension: "detection", label: "Detection" },
  { dimension: "organism", label: "Organism" },
  { dimension: "status", label: "Status" },
  { dimension: "readout_kind", label: "Readout kind" },
];

const ONTOLOGY_SLOTS: Partial<Record<FacetDimension, string>> = {
  assay_format: "assay_format",
  detection: "detection",
  organism: "organism",
};

/** Canonical comparable key: lower / trim / collapse-ws. Mirrors the backend
 *  fingerprint's normalize_facet_id / _normalize_readout_name so buckets agree. */
export function normFacet(s: string): string {
  return s.trim().toLowerCase().split(/\s+/).join(" ");
}

function ontologyItems(p: Protocol, slot: string): FacetItem[] {
  const terms = p.ontology_annotations?.[slot] ?? [];
  return terms.map((t) => ({
    value:
      t.ontology_source === "free_text"
        ? `free_text:${normFacet(t.label)}`
        : t.term_id.trim().toLowerCase(),
    label: t.label,
  }));
}

/** Distinct (value,label) facet items a protocol contributes to a dimension.
 *  Deduped by value (first label wins). */
export function extractFacetItems(p: Protocol, dim: FacetDimension): FacetItem[] {
  let raw: FacetItem[];
  switch (dim) {
    case "type":
      raw = [
        { value: p.protocol_type, label: PROTOCOL_TYPE_LABELS[p.protocol_type] ?? p.protocol_type },
      ];
      break;
    case "status":
      raw = [{ value: p.status, label: PROTOCOL_STATUS_LABELS[p.status] ?? p.status }];
      break;
    case "target":
      raw = p.targets.map((t) => ({ value: t.id, label: t.name }));
      break;
    case "category":
      raw = p.category?.trim() ? [{ value: normFacet(p.category), label: p.category.trim() }] : [];
      break;
    case "readout_kind":
      raw = p.readout_definitions
        .filter((rd) => rd.name.trim())
        .map((rd) => ({ value: normFacet(rd.name), label: rd.name.trim() }));
      break;
    default: {
      const slot = ONTOLOGY_SLOTS[dim];
      raw = slot ? ontologyItems(p, slot) : [];
    }
  }
  const seen = new Set<string>();
  const out: FacetItem[] = [];
  for (const item of raw) {
    if (!seen.has(item.value)) {
      seen.add(item.value);
      out.push(item);
    }
  }
  return out;
}

/** Substring match on name + target names + category (case-insensitive). */
export function matchesProtocolText(p: Protocol, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (p.name.toLowerCase().includes(q)) return true;
  if (p.category?.toLowerCase().includes(q)) return true;
  return p.targets.some((t) => t.name.toLowerCase().includes(q));
}

export function protocolMatchesSelections(p: Protocol, selections: FacetSelections): boolean {
  for (const dim of Object.keys(selections) as FacetDimension[]) {
    const selected = selections[dim];
    if (!selected || selected.size === 0) continue;
    const values = extractFacetItems(p, dim).map((i) => i.value);
    if (!values.some((v) => selected.has(v))) return false; // AND across; OR within
  }
  return true;
}

export function filterProtocols(protocols: Protocol[], selections: FacetSelections): Protocol[] {
  return protocols.filter((p) => protocolMatchesSelections(p, selections));
}
