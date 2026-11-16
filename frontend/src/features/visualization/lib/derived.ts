import { fragmentDisplay } from "@/features/sar-analysis/lib/sar-fragment-label";
import { buildSubtreeMolIdMap } from "@/features/sar-analysis/lib/scaffold-tree-math";
import type { ScaffoldTreeResult, UmapResult } from "@/features/sar-analysis/types";
import type { DecompositionAssignmentsResponse } from "@/shared/lib/api/model";
import type { Dataset, DatasetColumn } from "../types";
import { moleculeStructures } from "./dataset";

/** One series: compounds under a scaffold-tree node, or matching an R-groups set's core
 * (exactly one of the two). */
export type SeriesMember = { name: string; scaffold?: string; rgroupsId?: string };

/** What a derived column set was computed from. R-groups sets are `rg1`, `rg2`, … ("Core A",
 * "Core B", …); there is at most one clusters set and one series set. */
export type DerivedSpec =
  | { id: string; kind: "rgroups"; coreSmiles: string; name: string }
  | { id: "clusters"; kind: "clusters"; threshold: number }
  | { id: "series"; kind: "series"; members: SeriesMember[] };

type Cell = string | number | null;

/** Compound-level columns keyed by molecule id, joined onto any level by `withDerived`. Every
 * compound of the dataset it was computed on has an entry (all null without a structure). */
export interface DerivedSet {
  spec: DerivedSpec;
  columns: DatasetColumn[];
  byMolecule: Map<string, Record<string, Cell>>;
  summary: string;
  warning?: string;
}

const fmt = (n: number) => n.toLocaleString();

const col = (
  key: string,
  label: string,
  kind: DatasetColumn["kind"],
  group: string,
  hidden = false,
): DatasetColumn => ({ key, label, kind, group, provenance: {}, ...(hidden && { hidden }) });

/** One record per dataset compound: `valuesOf(id)` for those with a structure, all null for
 * the rest (counted, so summaries can say so). */
function perCompound(
  ds: Dataset,
  columns: DatasetColumn[],
  valuesOf: (id: string) => Record<string, Cell>,
) {
  const nulls = Object.fromEntries(columns.map((c) => [c.key, null]));
  const byMolecule = new Map<string, Record<string, Cell>>();
  let without = 0;
  for (const [id, structured] of moleculeStructures(ds)) {
    if (!structured) without++;
    byMolecule.set(id, structured ? valuesOf(id) : nulls);
  }
  return { byMolecule, total: byMolecule.size, without };
}

const withoutNote = (n: number) => (n ? ` · ${fmt(n)} without a structure` : "");

const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`;

/** R1…Rn (chemist labels, raw fragments in hidden `:smiles` siblings) + "Matches core". */
export function rgroupSet(
  spec: Extract<DerivedSpec, { kind: "rgroups" }>,
  ds: Dataset,
  a: DecompositionAssignmentsResponse,
): DerivedSet {
  const p = `chem:${spec.id}`;
  const group = `R-groups · ${spec.name}`;
  const columns = [
    ...a.labels.flatMap((r) => [
      col(`${p}:${r}`, r, "category", group),
      col(`${p}:${r}:smiles`, `${r} fragment`, "structure", group, true),
    ]),
    col(`${p}:match`, "Matches core", "category", group),
  ];
  let matched = 0;
  const { byMolecule, total, without } = perCompound(ds, columns, (id) => {
    const frags = a.assignments[id];
    if (frags) matched++;
    const row: Record<string, Cell> = { [`${p}:match`]: frags ? "Matches" : "No match" };
    for (const r of a.labels) {
      const smiles = frags?.[r] ?? null;
      row[`${p}:${r}`] = smiles === null ? null : fragmentDisplay(smiles).label;
      row[`${p}:${r}:smiles`] = smiles;
    }
    return row;
  });
  const [first, last] = [a.labels[0], a.labels.at(-1)];
  const positions = first ? `${first === last ? first : `${first}–${last}`} · ` : "";
  return {
    spec,
    columns,
    byMolecule,
    summary: `${positions}${fmt(matched)} of ${fmt(total)} match${withoutNote(without)}`,
    ...(matched < total / 2 && {
      warning: `Only ${fmt(matched)} of ${fmt(total)} compounds match this core`,
    }),
  };
}

/** "Cluster {n}" (1-based) + the cluster map's X/Y. */
export function clusterSet(
  spec: Extract<DerivedSpec, { kind: "clusters" }>,
  ds: Dataset,
  r: UmapResult,
): DerivedSet {
  const group = "Cluster";
  const columns = [
    col("chem:clusters:id", "Cluster", "category", group),
    col("chem:clusters:x", "Cluster map X", "number", group),
    col("chem:clusters:y", "Cluster map Y", "number", group),
  ];
  const cluster = new Map(r.clusters.map((c) => [c.moleculeId, c.clusterId]));
  const point = new Map(r.points.map((pt) => [pt.moleculeId, pt]));
  let unclustered = 0;
  const { byMolecule, without } = perCompound(ds, columns, (id) => {
    const c = cluster.get(id);
    if (c === undefined) unclustered++;
    return {
      "chem:clusters:id": c === undefined ? null : `Cluster ${c + 1}`,
      "chem:clusters:x": point.get(id)?.x ?? null,
      "chem:clusters:y": point.get(id)?.y ?? null,
    };
  });
  const skipped = unclustered ? ` · ${fmt(unclustered)} not clustered` : "";
  return {
    spec,
    columns,
    byMolecule,
    summary: `${plural(r.clusterCount, "cluster", "clusters")}${skipped}${withoutNote(without)}`,
  };
}

/** One "Series" column: the first member a compound belongs to, else "Other". */
export function seriesSet(
  spec: Extract<DerivedSpec, { kind: "series" }>,
  ds: Dataset,
  tree: ScaffoldTreeResult | null,
  rgroupSets: DerivedSet[],
): DerivedSet {
  const subtrees = spec.members.some((m) => m.scaffold) && tree ? buildSubtreeMolIdMap(tree) : null;
  const problems: string[] = [];
  const memberIds = spec.members.map((m): Set<string> => {
    if (m.scaffold) {
      const ids = subtrees?.get(m.scaffold);
      if (!ids) problems.push(`${m.name}: its scaffold is not in this dataset`);
      return new Set(ids);
    }
    const set = rgroupSets.find((s) => s.spec.id === m.rgroupsId);
    if (!set) {
      problems.push(`${m.name}: its R-group columns are not ready`);
      return new Set();
    }
    const match = `chem:${set.spec.id}:match`;
    return new Set([...set.byMolecule].filter(([, v]) => v[match] === "Matches").map(([id]) => id));
  });
  const columns = [col("chem:series", "Series", "category", "Series")];
  const counts = new Map<string, number>();
  let overlaps = 0;
  const { byMolecule, without } = perCompound(ds, columns, (id) => {
    const hits = spec.members.filter((_, k) => memberIds[k].has(id));
    if (hits.length > 1) overlaps++;
    const name = hits[0]?.name ?? "Other";
    counts.set(name, (counts.get(name) ?? 0) + 1);
    return { "chem:series": name };
  });
  if (overlaps) {
    problems.push(
      `${plural(overlaps, "compound is", "compounds are")} in more than one series; ${overlaps === 1 ? "it counts" : "each counts"} in the first`,
    );
  }
  const parts = [...spec.members.map((m) => m.name), "Other"].map(
    (name) => `${name} ${fmt(counts.get(name) ?? 0)}`,
  );
  return {
    spec,
    columns,
    byMolecule,
    summary: parts.join(" · ") + withoutNote(without),
    ...(problems.length && { warning: problems.join(" · ") }),
  };
}

/** The dataset with every set's columns appended, values aligned to its rows by molecule id
 * (wells of a compound share its values; rows without a compound get null). */
export function withDerived(ds: Dataset, sets: DerivedSet[]): Dataset {
  if (sets.length === 0) return ds;
  const molecules = ds.values.molecule_id ?? [];
  const values = { ...ds.values };
  for (const set of sets) {
    for (const c of set.columns) {
      values[c.key] = ds.row_ids.map((_, i) => {
        const id = molecules[i];
        return typeof id === "string" ? (set.byMolecule.get(id)?.[c.key] ?? null) : null;
      });
    }
  }
  return { ...ds, columns: [...ds.columns, ...sets.flatMap((s) => s.columns)], values };
}

/** How many of the dataset's compounds the set was computed for. */
export function coverage(ds: Dataset, set: DerivedSet): { covered: number; total: number } {
  const ids = [...moleculeStructures(ds).keys()];
  return { covered: ids.filter((id) => set.byMolecule.has(id)).length, total: ids.length };
}
