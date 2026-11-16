import { describe, expect, it } from "vitest";
import type { DatasetSource } from "../types";
import {
  fromDatasetRequest,
  levelFromParams,
  sourceFromParams,
  toDatasetRequest,
  visualizeHref,
} from "./source-url";

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

describe("visualize URL level", () => {
  const run: DatasetSource = { kind: "run", runId: "r1" };

  it("names the level unless it is wells", () => {
    expect(visualizeHref(run, "runs")).toBe("/assays/visualize?run=r1&level=runs");
    expect(visualizeHref(run, "wells")).toBe("/assays/visualize?run=r1");
    expect(visualizeHref({ kind: "protocol", protocolId: "p1" }, "compounds")).toBe(
      "/assays/visualize?protocol=p1&level=compounds",
    );
  });

  it("reads the level back, falling back to wells", () => {
    expect(levelFromParams({ level: "compounds" })).toBe("compounds");
    expect(levelFromParams({ level: ["batches"] })).toBe("batches");
    expect(levelFromParams({ level: "bogus" })).toBe("wells");
    expect(levelFromParams({ level: "toString" })).toBe("wells");
    expect(levelFromParams({})).toBe("wells");
  });

  it("keeps the source when a level is named", () => {
    const query = Object.fromEntries(
      new URL(visualizeHref(run, "batches"), "http://x").searchParams,
    );
    expect(sourceFromParams(query)).toEqual(run);
    expect(levelFromParams(query)).toBe("batches");
  });
});

describe("saved view URL", () => {
  it("opens a view at its own path, naming the level always", () => {
    const src: DatasetSource = { kind: "protocol", protocolId: "p1", runIds: ["r1"] };
    const href = visualizeHref(src, "compounds", "v1");
    expect(href.startsWith("/assays/visualize/v1?")).toBe(true);
    expect(href).toContain("level=compounds");
    // Wells too: without it the view's own saved level would win over the switch.
    expect(visualizeHref(src, "wells", "v1")).toContain("level=wells");
  });
});

describe("dataset request", () => {
  it("round-trips a run source and a protocol source with or without runs", () => {
    const sources: DatasetSource[] = [
      { kind: "run", runId: "r1" },
      { kind: "protocol", protocolId: "p1", runIds: ["r1", "r2"] },
      { kind: "protocol", protocolId: "p1" },
    ];
    for (const source of sources) {
      expect(fromDatasetRequest(toDatasetRequest(source, "runs"))).toEqual({
        source,
        level: "runs",
      });
    }
    expect(toDatasetRequest(sources[1], "wells")).toEqual({
      level: "wells",
      source: { kind: "protocol", protocol_id: "p1", run_ids: ["r1", "r2"] },
    });
  });
});
