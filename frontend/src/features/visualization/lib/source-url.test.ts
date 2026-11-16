import { describe, expect, it } from "vitest";
import type { DatasetSource } from "../types";
import { sourceFromParams, visualizeHref } from "./source-url";

describe("visualize URL contract", () => {
  it("round-trips a run, a protocol and a protocol with chosen runs", () => {
    const sources: DatasetSource[] = [
      { kind: "run", runId: "r1" },
      { kind: "protocol", protocolId: "p1" },
      { kind: "protocol", protocolId: "p1", runIds: ["r1", "r2"] },
    ];
    expect(visualizeHref(sources[0])).toBe("/assays/visualize?run=r1");
    expect(visualizeHref(sources[2])).toBe("/assays/visualize?protocol=p1&runs=r1%2Cr2");
    for (const s of sources) {
      const query = Object.fromEntries(new URL(visualizeHref(s), "http://x").searchParams);
      expect(sourceFromParams(query)).toEqual(s);
    }
  });

  it("returns null when the URL names no source", () => {
    expect(sourceFromParams({})).toBeNull();
    expect(sourceFromParams({ runs: "r1" })).toBeNull();
  });
});
