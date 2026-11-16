import type { ScaffoldTreeResult, UmapResult } from "@/features/sar-analysis/types";
import type { DecompositionAssignmentsResponse } from "@/shared/lib/api/model";
import { describe, expect, it } from "vitest";
import type { Dataset } from "../types";
import {
  type DerivedSpec,
  clusterSet,
  coverage,
  jobMoleculeIds,
  rgroupSet,
  seriesSet,
  withDerived,
} from "./derived";
import { dataset } from "./traces/test-fixtures";

// Wells: m1 three times, m2 and m4 structured, m3 without a structure, one control well.
const wells = (): Dataset =>
  dataset(
    {
      molecule_id: ["m1", "m1", "m1", "m2", "m3", "m4", null],
      structure: ["Clc1ccccc1", "Clc1ccccc1", "Clc1ccccc1", "CCO", null, "c1ccncc1", null],
      well_type: ["sample", "sample", "sample", "sample", "sample", "sample", "negative_control"],
      y: [1, 2, 3, 4, 5, 6, 7],
    },
    { structure: "structure" },
  );

const rgSpec: DerivedSpec = { id: "rg1", kind: "rgroups", coreSmiles: "c1ccccc1", name: "Core A" };
const assignments: DecompositionAssignmentsResponse = {
  core_smiles: "c1ccccc1",
  labels: ["R1", "R2"],
  // m3 has no structure: whatever the server says, it gets nulls.
  assignments: {
    m1: { R1: "Cl[*:1]", R2: "[H][*:2]" },
    m3: { R1: "Br[*:1]", R2: "[H][*:2]" },
  },
};

describe("rgroupSet", () => {
  const set = rgroupSet(rgSpec, wells(), assignments);

  it("builds R columns, hidden raw-fragment siblings and a match column", () => {
    expect(set.columns.map((c) => [c.key, c.label, c.kind, c.hidden ?? false])).toEqual([
      ["chem:rg1:R1", "R1", "category", false],
      ["chem:rg1:R1:smiles", "R1 fragment", "structure", true],
      ["chem:rg1:R2", "R2", "category", false],
      ["chem:rg1:R2:smiles", "R2 fragment", "structure", true],
      ["chem:rg1:match", "Matches core", "category", false],
    ]);
    for (const c of set.columns) {
      expect(c.group).toBe("R-groups · Core A");
      expect(c.provenance).toEqual({});
    }
  });

  it("labels fragments for chemists and keeps the raw SMILES hidden", () => {
    expect(set.byMolecule.get("m1")).toEqual({
      "chem:rg1:R1": "Cl",
      "chem:rg1:R1:smiles": "Cl[*:1]",
      "chem:rg1:R2": "–H",
      "chem:rg1:R2:smiles": "[H][*:2]",
      "chem:rg1:match": "Matches",
    });
  });

  it("gives a structured compound outside the core blank R values and No match", () => {
    expect(set.byMolecule.get("m2")).toEqual({
      "chem:rg1:R1": null,
      "chem:rg1:R1:smiles": null,
      "chem:rg1:R2": null,
      "chem:rg1:R2:smiles": null,
      "chem:rg1:match": "No match",
    });
  });

  it("leaves a compound without a structure out (null everywhere, match included)", () => {
    expect(set.byMolecule.has("m3")).toBe(false);
  });

  it("summarizes matches among the analysed compounds, notes those without a structure, and warns under half", () => {
    expect(set.summary).toBe("R1–R2 · 1 of 3 match · 1 without a structure");
    expect(set.warning).toBe("Only 1 of 3 compounds match this core");
  });

  it("does not warn when at least half match", () => {
    const all = rgroupSet(rgSpec, wells(), {
      ...assignments,
      assignments: { ...assignments.assignments, m2: { R1: "C[*:1]" }, m4: { R1: "C[*:1]" } },
    });
    expect(all.warning).toBeUndefined();
    expect(all.summary).toBe("R1–R2 · 3 of 3 match · 1 without a structure");
    // A position the decomposition left out stays blank.
    expect(all.byMolecule.get("m2")?.["chem:rg1:R2"]).toBeNull();
  });
});

const umap = (patch: Partial<UmapResult> = {}): UmapResult => ({
  points: [
    { moleculeId: "m1", x: 1.5, y: -2 },
    { moleculeId: "m4", x: 3, y: 4 },
  ],
  clusters: [
    { moleculeId: "m1", clusterId: 0 },
    { moleculeId: "m4", clusterId: 2 },
  ],
  representatives: [],
  clusterCount: 3,
  picker: "butina",
  pickerParams: { threshold: 0.4 },
  skippedMoleculeIds: ["m2"],
  ...patch,
});

describe("clusterSet", () => {
  const spec: DerivedSpec = { id: "clusters", kind: "clusters", threshold: 0.4 };
  const set = clusterSet(spec, wells(), umap());

  it("builds the cluster and map columns", () => {
    expect(set.columns.map((c) => [c.key, c.label, c.kind, c.group])).toEqual([
      ["chem:clusters:id", "Cluster", "category", "Cluster"],
      ["chem:clusters:x", "Cluster map X", "number", "Cluster"],
      ["chem:clusters:y", "Cluster map Y", "number", "Cluster"],
    ]);
  });

  it("numbers clusters from 1 and leaves skipped and structureless compounds null", () => {
    expect(set.byMolecule.get("m1")).toEqual({
      "chem:clusters:id": "Cluster 1",
      "chem:clusters:x": 1.5,
      "chem:clusters:y": -2,
    });
    expect(set.byMolecule.get("m4")?.["chem:clusters:id"]).toBe("Cluster 3");
    expect(set.byMolecule.get("m2")).toEqual({
      "chem:clusters:id": null,
      "chem:clusters:x": null,
      "chem:clusters:y": null,
    });
    expect(set.byMolecule.has("m3")).toBe(false);
  });

  it("counts clusters, unclustered and structureless compounds", () => {
    expect(set.summary).toBe("3 clusters · 1 not clustered · 1 without a structure");
    expect(set.warning).toBeUndefined();
  });
});

// S1 contains S2: S1's subtree holds m1 and m2.
const tree: ScaffoldTreeResult = {
  nodes: [
    { scaffold_smiles: "S1", molecule_ids: ["m1"], molecule_count: 1, subtree_molecule_count: 2 },
    { scaffold_smiles: "S2", molecule_ids: ["m2"], molecule_count: 1, subtree_molecule_count: 1 },
  ],
  edges: [{ parent_smiles: "S1", child_smiles: "S2" }],
  stats: { node_count: 2, elapsed_ms: 1, cache_hit: false },
};

describe("seriesSet", () => {
  const rg = rgroupSet(rgSpec, wells(), assignments);
  const spec: DerivedSpec = {
    id: "series",
    kind: "series",
    members: [
      { name: "Series A", rgroupsId: "rg1" },
      { name: "Series B", scaffold: "S1" },
      { name: "Series C", scaffold: "S9" },
    ],
  };
  const set = seriesSet(spec, wells(), tree, [rg]);

  it("builds one Series column", () => {
    expect(set.columns.map((c) => [c.key, c.label, c.kind, c.group])).toEqual([
      ["chem:series", "Series", "category", "Series"],
    ]);
  });

  it("puts a compound in the first member it belongs to, else Other", () => {
    const of = (id: string) => set.byMolecule.get(id)?.["chem:series"];
    expect(of("m1")).toBe("Series A"); // R-group match and S1 subtree: first wins
    expect(of("m2")).toBe("Series B"); // S1 subtree via S2
    expect(of("m4")).toBe("Other");
    expect(of("m3")).toBeUndefined(); // no structure
  });

  it("summarizes every member and warns about an absent scaffold and overlaps", () => {
    expect(set.summary).toBe(
      "Series A 1 · Series B 1 · Series C 0 · Other 1 · 1 without a structure",
    );
    expect(set.warning).toBe(
      "Series C: its scaffold is not in this dataset · 1 compound is in more than one series; it counts in the first",
    );
  });

  it("names an R-groups member whose set is not ready", () => {
    const s = seriesSet(
      { id: "series", kind: "series", members: [{ name: "Series A", rgroupsId: "rg2" }] },
      wells(),
      null,
      [rg],
    );
    expect(s.byMolecule.get("m1")?.["chem:series"]).toBe("Other");
    expect(s.warning).toBe("Series A: its R-group columns are not ready");
  });
});

describe("withDerived", () => {
  const rg = rgroupSet(rgSpec, wells(), assignments);

  it("gives every well of a compound its value and rows without a compound null", () => {
    const ds = wells();
    const out = withDerived(ds, [rg]);
    expect(out.revision).toBe(ds.revision);
    expect(out.row_ids).toBe(ds.row_ids);
    expect(out.columns.slice(ds.columns.length).map((c) => c.key)).toEqual(
      rg.columns.map((c) => c.key),
    );
    expect(out.values["chem:rg1:R1"]).toEqual(["Cl", "Cl", "Cl", null, null, null, null]);
    expect(out.values["chem:rg1:match"]).toEqual([
      "Matches",
      "Matches",
      "Matches",
      "No match",
      null,
      "No match",
      null,
    ]);
    expect(out.values.y).toBe(ds.values.y);
  });

  it("gives one value per row at the compounds level", () => {
    const compounds = dataset(
      {
        molecule_id: ["m4", "m1", "m2"],
        structure: ["c1ccncc1", "Clc1ccccc1", "CCO"],
      },
      { structure: "structure" },
    );
    expect(withDerived(compounds, [rg]).values["chem:rg1:R1"]).toEqual([null, "Cl", null]);
  });

  it("returns the dataset itself without sets", () => {
    const ds = wells();
    expect(withDerived(ds, [])).toBe(ds);
  });
});

describe("coverage", () => {
  it("counts the dataset compounds the set was computed for", () => {
    const small = dataset(
      { molecule_id: ["m1", "m2", null], structure: ["Clc1ccccc1", "CCO", null] },
      { structure: "structure" },
    );
    const set = rgroupSet(rgSpec, small, assignments);
    const larger = dataset(
      { molecule_id: ["m1", "m1", "m2", "m5", null], structure: ["C", "C", "C", "C", null] },
      { structure: "structure" },
    );
    expect(coverage(larger, set)).toEqual({ covered: 2, total: 3 });
  });
});

describe("a set whose job started before the dataset grew", () => {
  // The job ran over m1 and m2; m4 was added to the dataset since.
  const ran = ["m1", "m2"];

  it("holds only the compounds its job analysed: a newer one is blank, not No match", () => {
    const set = rgroupSet(rgSpec, wells(), assignments, ran);
    expect(set.byMolecule.has("m4")).toBe(false);
    expect(set.summary).toBe("R1–R2 · 1 of 2 match · 1 without a structure");
    expect(withDerived(wells(), [set]).values["chem:rg1:match"]).toEqual([
      "Matches",
      "Matches",
      "Matches",
      "No match",
      null,
      null,
      null,
    ]);
    expect(coverage(wells(), set)).toEqual({ covered: 2, total: 3 });
  });

  it("leaves a newer compound out of clusters and series too", () => {
    const clusters = clusterSet(
      { id: "clusters", kind: "clusters", threshold: 0.4 },
      wells(),
      umap(),
      ran,
    );
    expect(clusters.byMolecule.has("m4")).toBe(false);
    expect(coverage(wells(), clusters)).toEqual({ covered: 2, total: 3 });
    const s = seriesSet(
      { id: "series", kind: "series", members: [{ name: "Series B", scaffold: "S1" }] },
      wells(),
      tree,
      [],
      ran,
    );
    expect(s.byMolecule.has("m4")).toBe(false);
    expect(s.summary).toBe("Series B 2 · Other 0 · 1 without a structure");
  });
});

describe("jobMoleculeIds", () => {
  it("runs over every dataset compound with a structure, once, sorted", () => {
    expect(jobMoleculeIds(wells())).toEqual(["m1", "m2", "m4"]);
  });
});
