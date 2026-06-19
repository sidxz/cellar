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

export interface FacetValue {
  value: string;
  label: string;
  count: number;
}

export interface FacetGroup {
  dimension: FacetDimension;
  label: string;
  values: FacetValue[];
}

export interface ProtocolGroup {
  key: string;
  label: string;
  protocols: Protocol[];
  count: number;
}

export const GROUP_BY_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: "target", label: "Target" },
  { value: "category", label: "Category" },
  { value: "type", label: "Type" },
  { value: "assay_format", label: "Assay format" },
  { value: "status", label: "Status" },
  { value: "none", label: "None" },
];

const NONE_KEY = "__none__";

/** Most-frequent label for a value (ties → first seen). */
function pickLabel(counts: Map<string, number>): string {
  let best = "";
  let bestN = -1;
  for (const [label, n] of counts) {
    if (n > bestN) {
      best = label;
      bestN = n;
    }
  }
  return best;
}

/** Per-dimension drill-down: each value's count reflects all OTHER facets'
 *  selections (not its own), the standard faceted-search semantic. */
export function buildFacetModel(protocols: Protocol[], selections: FacetSelections): FacetGroup[] {
  const out: FacetGroup[] = [];
  for (const { dimension, label } of FACET_DIMENSIONS) {
    const others: FacetSelections = { ...selections };
    delete others[dimension];
    const scope = filterProtocols(protocols, others);

    const counts = new Map<string, number>();
    const labels = new Map<string, Map<string, number>>();
    for (const p of scope) {
      for (const item of extractFacetItems(p, dimension)) {
        counts.set(item.value, (counts.get(item.value) ?? 0) + 1);
        const lc = labels.get(item.value) ?? new Map<string, number>();
        lc.set(item.label, (lc.get(item.label) ?? 0) + 1);
        labels.set(item.value, lc);
      }
    }
    if (counts.size === 0) continue; // hide empty facets

    const values: FacetValue[] = [...counts.entries()]
      .map(([value, count]) => ({ value, count, label: pickLabel(labels.get(value) ?? new Map()) }))
      .sort((x, y) => y.count - x.count || x.label.localeCompare(y.label));
    out.push({ dimension, label, values });
  }
  return out;
}

const GROUP_DIMENSION: Record<Exclude<GroupBy, "none">, FacetDimension> = {
  target: "target",
  category: "category",
  type: "type",
  assay_format: "assay_format",
  status: "status",
};

export function groupProtocols(protocols: Protocol[], groupBy: GroupBy): ProtocolGroup[] {
  if (groupBy === "none") {
    return [{ key: "all", label: "All protocols", protocols, count: protocols.length }];
  }
  const dim = GROUP_DIMENSION[groupBy];
  const buckets = new Map<string, { label: string; protocols: Protocol[] }>();
  for (const p of protocols) {
    const items = extractFacetItems(p, dim);
    if (items.length === 0) {
      const g = buckets.get(NONE_KEY) ?? {
        label: `No ${FACET_LABEL[dim].toLowerCase()}`,
        protocols: [],
      };
      g.protocols.push(p);
      buckets.set(NONE_KEY, g);
      continue;
    }
    for (const item of items) {
      const g = buckets.get(item.value) ?? { label: item.label, protocols: [] };
      g.protocols.push(p);
      buckets.set(item.value, g);
    }
  }
  const groups = [...buckets.entries()].map(([key, g]) => ({
    key,
    label: g.label,
    protocols: g.protocols,
    count: g.protocols.length,
  }));
  // count-desc, but the "No X" bucket always pinned last.
  return groups.sort((a, b) => {
    if (a.key === NONE_KEY) return 1;
    if (b.key === NONE_KEY) return -1;
    return b.count - a.count || a.label.localeCompare(b.label);
  });
}

const FACET_LABEL: Record<FacetDimension, string> = Object.fromEntries(
  FACET_DIMENSIONS.map((f) => [f.dimension, f.label]),
) as Record<FacetDimension, string>;
