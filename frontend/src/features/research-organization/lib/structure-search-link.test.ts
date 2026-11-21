import { describe, expect, it } from "vitest";

import { parseStructureSearchLink, structureLinkCriterion } from "./structure-search-link";

const ID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";
const parse = (q: string) => parseStructureSearchLink(new URLSearchParams(q));

describe("parseStructureSearchLink", () => {
  it("is null when the URL names no molecule", () => {
    expect(parse("")).toBeNull();
    expect(parse("saved=abc")).toBeNull();
  });

  it("reads a similar link with its threshold", () => {
    expect(parse(`molecule_id=${ID}&mode=similar&threshold=0.55`)).toEqual({
      moleculeId: ID,
      mode: "similar",
      threshold: 0.55,
    });
  });

  it("defaults the threshold to 0.7 when missing or out of range", () => {
    for (const t of ["", "&threshold=0", "&threshold=1.5", "&threshold=abc", "&threshold=-1"]) {
      expect(parse(`molecule_id=${ID}&mode=similar${t}`)).toMatchObject({ threshold: 0.7 });
    }
    expect(parse(`molecule_id=${ID}&mode=similar&threshold=1`)).toMatchObject({ threshold: 1 });
  });

  it("reads a substructure link", () => {
    expect(parse(`molecule_id=${ID}&mode=substructure`)).toEqual({
      moleculeId: ID,
      mode: "substructure",
      threshold: 0.7,
    });
  });

  it("is invalid for an unknown mode or a malformed id", () => {
    expect(parse(`molecule_id=${ID}&mode=exact`)).toBe("invalid");
    expect(parse(`molecule_id=${ID}`)).toBe("invalid");
    expect(parse("molecule_id=not-a-uuid&mode=similar")).toBe("invalid");
  });
});

describe("structureLinkCriterion", () => {
  it("builds a Similar criterion with the threshold", () => {
    expect(
      structureLinkCriterion({ moleculeId: ID, mode: "similar", threshold: 0.6 }, "c1ccccc1O"),
    ).toEqual({
      type: "structure",
      search_type: "similarity",
      kind: "similarity",
      mode: "similar",
      smiles: "c1ccccc1O",
      threshold: 0.6,
    });
  });

  it("builds a substructure criterion from the molecule's SMILES", () => {
    expect(
      structureLinkCriterion({ moleculeId: ID, mode: "substructure", threshold: 0.7 }, "c1ccccc1O"),
    ).toEqual({
      type: "structure",
      search_type: "substructure",
      kind: "substructure",
      smiles_or_smarts: "c1ccccc1O",
      query_kind: "smiles",
    });
  });
});
