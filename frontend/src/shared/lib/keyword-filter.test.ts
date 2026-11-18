import { describe, expect, it } from "vitest";
import { keywordFilter } from "./keyword-filter";

const pptT = ["PptT", "Mycobacterium tuberculosis", "Rv2794c", "O33336"];
const ppa = ["Ppa", "Mycobacterium tuberculosis", "Rv3628", "P9WI55"];

describe("keywordFilter", () => {
  it("matches a contiguous run of letters, not letters scattered across fields", () => {
    expect(keywordFilter("id", "pptt", pptT)).toBeGreaterThan(0);
    // p-p in the name, t-t in the organism: the fuzzy default calls this a match.
    expect(keywordFilter("id", "pptt", ppa)).toBe(0);
  });

  it("ignores case", () => {
    expect(keywordFilter("id", "PPTT", pptT)).toBeGreaterThan(0);
  });

  it("never searches the item's value", () => {
    expect(keywordFilter("3f2a-pptt-uuid", "pptt", ppa)).toBe(0);
  });

  it("finds an item by any keyword, each typed word on its own", () => {
    expect(keywordFilter("id", "rv2794", pptT)).toBeGreaterThan(0);
    expect(keywordFilter("id", "ppt tuberc", pptT)).toBeGreaterThan(0);
    expect(keywordFilter("id", "ppt sapiens", pptT)).toBe(0);
  });

  it("ranks an item whose label starts with the query above one that merely contains it", () => {
    const starts = keywordFilter("id", "ppt", pptT);
    const contains = keywordFilter("id", "ppt", ["TppT", "Mycobacterium tuberculosis"]);
    expect(starts).toBeGreaterThan(contains);
    expect(contains).toBeGreaterThan(0);
  });

  it("matches nothing when the item has no keywords", () => {
    expect(keywordFilter("__action__", "ppt")).toBe(0);
  });
});
