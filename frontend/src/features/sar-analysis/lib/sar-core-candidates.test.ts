import { describe, expect, it } from "vitest";
import { NO_SCAFFOLD_SENTINEL, type ScaffoldTreeResult } from "../types/scaffold-tree";
import { buildCoreCandidates, pickDefaultCore } from "./sar-core-candidates";

const BENZENE = "c1ccccc1";
const PYRIMIDINE = "c1ccncn1";
const QUINAZOLINE = "c1ccc2ncncc2c1";
const PHENYLQUINAZOLINE = "c1ccc(-c2ccc3ncncc3c2)cc1";
const INDOLE = "c1ccc2[nH]ccc2c1";

/**
 * A congeneric series: all 6 molecules are quinazolines; 3 of them carry an
 * extra phenyl (a more-specific descendant). Benzene + pyrimidine are the
 * generic ring-removed ancestors with NO direct members (molecule_count 0) —
 * exactly the frameworks the old molecule_count ranking buried at "0".
 *
 * Edges form a diamond (benzene reaches phenyl-quinazoline both directly and via
 * quinazoline) so coverage must Set-dedupe.
 */
const analogSeries: ScaffoldTreeResult = {
  nodes: [
    { scaffold_smiles: BENZENE, molecule_ids: [], molecule_count: 0, subtree_molecule_count: 6 },
    { scaffold_smiles: PYRIMIDINE, molecule_ids: [], molecule_count: 0, subtree_molecule_count: 6 },
    {
      scaffold_smiles: QUINAZOLINE,
      molecule_ids: ["m4", "m5", "m6"],
      molecule_count: 3,
      subtree_molecule_count: 6,
    },
    {
      scaffold_smiles: PHENYLQUINAZOLINE,
      molecule_ids: ["m1", "m2", "m3"],
      molecule_count: 3,
      subtree_molecule_count: 3,
    },
  ],
  edges: [
    { parent_smiles: BENZENE, child_smiles: QUINAZOLINE },
    { parent_smiles: PYRIMIDINE, child_smiles: QUINAZOLINE },
    { parent_smiles: QUINAZOLINE, child_smiles: PHENYLQUINAZOLINE },
    { parent_smiles: BENZENE, child_smiles: PHENYLQUINAZOLINE }, // diamond
  ],
  stats: { node_count: 4, elapsed_ms: 0, cache_hit: false },
};

/** A diverse, non-congeneric set: 5 singleton chemotypes + one pair. Nothing
 *  reaches the coverage floor (3). */
const diverseSet: ScaffoldTreeResult = {
  nodes: [
    {
      scaffold_smiles: BENZENE,
      molecule_ids: ["m1"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    },
    {
      scaffold_smiles: "c1ccoc1",
      molecule_ids: ["m2"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    },
    {
      scaffold_smiles: "c1ccncc1",
      molecule_ids: ["m3"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    },
    {
      scaffold_smiles: "c1ccsc1",
      molecule_ids: ["m4"],
      molecule_count: 1,
      subtree_molecule_count: 1,
    },
    {
      scaffold_smiles: INDOLE,
      molecule_ids: ["m5", "m6"],
      molecule_count: 2,
      subtree_molecule_count: 2,
    },
  ],
  edges: [],
  stats: { node_count: 5, elapsed_ms: 0, cache_hit: false },
};

/** Two sub-series (4 quinazolines + 4 indoles) that share only benzene, plus an
 *  acyclic (no-scaffold) bucket that must be excluded from candidates. */
const twoSeries: ScaffoldTreeResult = {
  nodes: [
    { scaffold_smiles: BENZENE, molecule_ids: [], molecule_count: 0, subtree_molecule_count: 8 },
    { scaffold_smiles: PYRIMIDINE, molecule_ids: [], molecule_count: 0, subtree_molecule_count: 4 },
    {
      scaffold_smiles: QUINAZOLINE,
      molecule_ids: ["m1", "m2", "m3", "m4"],
      molecule_count: 4,
      subtree_molecule_count: 4,
    },
    {
      scaffold_smiles: INDOLE,
      molecule_ids: ["m5", "m6", "m7", "m8"],
      molecule_count: 4,
      subtree_molecule_count: 4,
    },
    {
      scaffold_smiles: NO_SCAFFOLD_SENTINEL,
      molecule_ids: ["m9", "m10", "m11"],
      molecule_count: 3,
      subtree_molecule_count: 3,
    },
  ],
  edges: [
    { parent_smiles: BENZENE, child_smiles: QUINAZOLINE },
    { parent_smiles: PYRIMIDINE, child_smiles: QUINAZOLINE },
    { parent_smiles: BENZENE, child_smiles: INDOLE },
  ],
  stats: { node_count: 5, elapsed_ms: 0, cache_hit: false },
};

const coverageOf = (res: ReturnType<typeof buildCoreCandidates>, smiles: string) =>
  res.candidates.find((c) => c.scaffoldSmiles === smiles)?.coverage;

describe("buildCoreCandidates", () => {
  it("ranks/filters by coverage, surfacing generic frameworks that have 0 direct members", () => {
    const { candidates, total } = buildCoreCandidates(analogSeries);
    expect(total).toBe(6);
    const smiles = candidates.map((c) => c.scaffoldSmiles);
    // benzene/pyrimidine have molecule_count 0 but coverage 6 — they MUST appear.
    expect(smiles).toContain(BENZENE);
    expect(smiles).toContain(PYRIMIDINE);
    expect(coverageOf({ candidates, total }, BENZENE)).toBe(6);
    expect(coverageOf({ candidates, total }, QUINAZOLINE)).toBe(6);
    // the more-specific descendant still clears the floor (coverage 3)
    expect(coverageOf({ candidates, total }, PHENYLQUINAZOLINE)).toBe(3);
  });

  it("dedupes coverage across a diamond DAG — never exceeds the set size", () => {
    const res = buildCoreCandidates(analogSeries);
    // phenyl-quinazoline (3) is reachable from benzene via two paths; benzene
    // coverage is 6, not 9.
    expect(coverageOf(res, BENZENE)).toBe(6);
    for (const c of res.candidates) expect(c.coverage).toBeLessThanOrEqual(res.total);
  });

  it("preserves the direct molecule_count as directCount", () => {
    const res = buildCoreCandidates(analogSeries);
    expect(res.candidates.find((c) => c.scaffoldSmiles === BENZENE)?.directCount).toBe(0);
    expect(res.candidates.find((c) => c.scaffoldSmiles === QUINAZOLINE)?.directCount).toBe(3);
  });

  it("excludes the NO_SCAFFOLD bucket even when it clears the floor", () => {
    const { candidates, total } = buildCoreCandidates(twoSeries);
    expect(total).toBe(11); // m1..m11 incl. the 3 acyclic
    expect(candidates.map((c) => c.scaffoldSmiles)).not.toContain(NO_SCAFFOLD_SENTINEL);
    // benzene is the shared framework of both ring sub-series: coverage 8.
    expect(coverageOf({ candidates, total }, BENZENE)).toBe(8);
  });

  it("filters cores below the coverage floor (default 3) — diverse set yields nothing", () => {
    expect(buildCoreCandidates(diverseSet).candidates).toEqual([]);
  });

  it("honors a custom floor", () => {
    const res = buildCoreCandidates(diverseSet, { floor: 2 });
    // only the indole pair (coverage 2) clears a floor of 2
    expect(res.candidates.map((c) => c.scaffoldSmiles)).toEqual([INDOLE]);
  });

  it("sorts by coverage desc, then specificity desc", () => {
    const res = buildCoreCandidates(twoSeries);
    // benzene (8) leads; the sub-series cores (4) follow.
    expect(res.candidates[0].scaffoldSmiles).toBe(BENZENE);
  });
});

describe("pickDefaultCore", () => {
  it("picks the specific shared core, not the generic ancestor, in a congeneric series", () => {
    const { candidates } = buildCoreCandidates(analogSeries);
    // benzene/pyrimidine/quinazoline all cover all 6; quinazoline is the most
    // specific of them → the chemist's natural starting core. NOT benzene, and
    // NOT the lone phenyl-quinazoline descendant (covers only 3).
    expect(pickDefaultCore(candidates)).toBe(QUINAZOLINE);
  });

  it("returns null when there is no shared scaffold (→ draw-a-core guidance)", () => {
    const { candidates } = buildCoreCandidates(diverseSet);
    expect(pickDefaultCore(candidates)).toBeNull();
  });

  it("defaults to the true common framework when the set splits into sub-series", () => {
    const { candidates } = buildCoreCandidates(twoSeries);
    // benzene covers all 8 ring compounds; quinazoline/indole cover only half
    // each, so the broad common core is the honest default (sub-series cores
    // remain one click away as chips).
    expect(pickDefaultCore(candidates)).toBe(BENZENE);
  });
});
