import { describe, expect, it } from "vitest";
import type { DatasetSource, SavedView } from "../types";
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

describe("compared protocols", () => {
  const compared: DatasetSource = {
    kind: "protocol",
    protocolId: "A",
    compare: [{ protocolId: "B" }, { protocolId: "C", runIds: ["r1", "r2"] }],
  };
  /** The query as Next.js hands it to the page: a repeated key becomes a string array. */
  const paramsOf = (href: string) => {
    const params: Record<string, string | string[]> = {};
    for (const [k, v] of new URL(href, "http://x").searchParams) {
      const had = params[k];
      params[k] = had === undefined ? v : [...(Array.isArray(had) ? had : [had]), v];
    }
    return params;
  };

  it("names each compared protocol once, with its runs when not all", () => {
    expect(visualizeHref(compared, "compounds")).toBe(
      "/assays/visualize?protocol=A&compare=B&compare=C%3Ar1%2Cr2&level=compounds",
    );
    expect(
      sourceFromParams({ protocol: "A", compare: ["B", "C:r1,r2"], level: "compounds" }),
    ).toEqual(compared);
    expect(sourceFromParams(paramsOf(visualizeHref(compared, "compounds")))).toEqual(compared);
  });

  it("reads a single compare param and ignores blank ones", () => {
    expect(sourceFromParams({ protocol: "A", compare: "B" })).toEqual({
      kind: "protocol",
      protocolId: "A",
      compare: [{ protocolId: "B" }],
    });
    expect(sourceFromParams({ protocol: "A", compare: ["", "B:"] })).toEqual({
      kind: "protocol",
      protocolId: "A",
      compare: [{ protocolId: "B" }],
    });
    expect(sourceFromParams({ protocol: "A", compare: "" })).toEqual({
      kind: "protocol",
      protocolId: "A",
    });
    expect(sourceFromParams({ run: "r1", compare: "B" })).toEqual({ kind: "run", runId: "r1" });
  });

  it("sends them in the dataset request, all runs as null", () => {
    expect(toDatasetRequest(compared, "compounds")).toEqual({
      level: "compounds",
      source: {
        kind: "protocol",
        protocol_id: "A",
        run_ids: null,
        compare: [
          { protocol_id: "B", run_ids: null },
          { protocol_id: "C", run_ids: ["r1", "r2"] },
        ],
      },
    });
    expect(fromDatasetRequest(toDatasetRequest(compared, "compounds"))).toEqual({
      source: compared,
      level: "compounds",
    });
    // Without added protocols the request is what it always was.
    expect(
      toDatasetRequest({ kind: "protocol", protocolId: "A" }, "compounds").source,
    ).not.toHaveProperty("compare");
  });

  it("survive save and open: URL, source, request, saved view and back", () => {
    const source = sourceFromParams(paramsOf(visualizeHref(compared, "compounds")));
    const level = levelFromParams(paramsOf(visualizeHref(compared, "compounds")));
    if (!source) throw new Error("no source");
    // Saved as the request's wire dict, read back as JSON.
    const view = JSON.parse(
      JSON.stringify({ id: "v1", level, dataset: toDatasetRequest(source, level) }),
    ) as SavedView;
    if (!view.dataset) throw new Error("no dataset");
    const opened = fromDatasetRequest(view.dataset);
    expect(opened).toEqual({ source: compared, level: "compounds" });
    const href = visualizeHref(opened.source, opened.level, view.id);
    expect(sourceFromParams(paramsOf(href))).toEqual(compared);
    expect(levelFromParams(paramsOf(href))).toBe("compounds");
  });
});
