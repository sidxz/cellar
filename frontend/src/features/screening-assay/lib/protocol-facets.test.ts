import { describe, expect, it } from "vitest";
import type { Protocol } from "../types";
import {
  extractFacetItems,
  filterProtocols,
  matchesProtocolText,
  normFacet,
  protocolMatchesSelections,
} from "./protocol-facets";

// Minimal Protocol factory — only the fields faceting reads.
function proto(over: Partial<Protocol>): Protocol {
  return {
    id: "p",
    workspace_id: "w",
    name: "Protocol",
    description: null,
    protocol_type: "biochemical",
    targets: [],
    category: null,
    protocol_version: 1,
    parent_protocol_id: null,
    status: "active",
    created_by: "u",
    dose_unit: "uM",
    pos_control_signal: "high",
    readout_definitions: [],
    condition_definitions: [],
    control_layouts: null,
    ontology_annotations: null,
    project_ids: [],
    recommended_hit_criteria: null,
    is_locked: false,
    locked_by: null,
    lock_reason: null,
    locked_at: null,
    ...over,
  } as Protocol;
}

describe("normFacet", () => {
  it("lowercases, trims, collapses whitespace", () => {
    expect(normFacet("  % Inhibition ")).toBe("% inhibition");
    expect(normFacet("Whole   Cell")).toBe("whole cell");
  });
});

describe("extractFacetItems", () => {
  it("type uses the canonical label", () => {
    expect(extractFacetItems(proto({ protocol_type: "cell_based" }), "type")).toEqual([
      { value: "cell_based", label: "Cell-Based" },
    ]);
  });

  it("target yields one item per target keyed by id", () => {
    const p = proto({
      targets: [
        { id: "t1", name: "RNAP", target_type: "protein" },
        { id: "t2", name: "InhA", target_type: "protein" },
      ],
    });
    expect(extractFacetItems(p, "target")).toEqual([
      { value: "t1", label: "RNAP" },
      { value: "t2", label: "InhA" },
    ]);
  });

  it("category normalizes the value but keeps the raw label", () => {
    expect(extractFacetItems(proto({ category: "Enzyme" }), "category")).toEqual([
      { value: "enzyme", label: "Enzyme" },
    ]);
    expect(extractFacetItems(proto({ category: "  " }), "category")).toEqual([]);
  });

  it("readout_kind dedupes casing variants within a protocol", () => {
    const p = proto({
      readout_definitions: [
        { name: "% Inhibition" },
        { name: "% inhibition" },
        { name: "IC50" },
      ] as Protocol["readout_definitions"],
    });
    expect(extractFacetItems(p, "readout_kind")).toEqual([
      { value: "% inhibition", label: "% Inhibition" },
      { value: "ic50", label: "IC50" },
    ]);
  });

  it("ontology facet: grounded keyed by term_id, free-text prefixed", () => {
    const p = proto({
      ontology_annotations: {
        assay_format: [
          { term_id: "BAO_0000019", label: "biochemical", ontology_source: "BAO", uri: null },
        ],
        detection: [
          { term_id: "x", label: "Fluorescence", ontology_source: "free_text", uri: null },
        ],
      },
    });
    expect(extractFacetItems(p, "assay_format")).toEqual([
      { value: "bao_0000019", label: "biochemical" },
    ]);
    expect(extractFacetItems(p, "detection")).toEqual([
      { value: "free_text:fluorescence", label: "Fluorescence" },
    ]);
  });
});

describe("matchesProtocolText", () => {
  const p = proto({
    name: "RNAP core IC50",
    category: "Enzyme",
    targets: [{ id: "t1", name: "RNAP", target_type: "protein" }],
  });
  it("matches name / target / category, case-insensitive; empty query passes", () => {
    expect(matchesProtocolText(p, "")).toBe(true);
    expect(matchesProtocolText(p, "rnap")).toBe(true);
    expect(matchesProtocolText(p, "enzyme")).toBe(true);
    expect(matchesProtocolText(p, "xyz")).toBe(false);
  });
});

describe("protocolMatchesSelections / filterProtocols", () => {
  const a = proto({ id: "a", protocol_type: "biochemical", status: "active" });
  const b = proto({ id: "b", protocol_type: "cell_based", status: "active" });
  const c = proto({ id: "c", protocol_type: "biochemical", status: "retired" });

  it("empty selection matches everything", () => {
    expect(filterProtocols([a, b, c], {})).toHaveLength(3);
  });

  it("OR within a facet", () => {
    const sel = { type: new Set(["biochemical", "cell_based"]) };
    expect(filterProtocols([a, b, c], sel).map((p) => p.id)).toEqual(["a", "b", "c"]);
  });

  it("AND across facets", () => {
    const sel = { type: new Set(["biochemical"]), status: new Set(["active"]) };
    expect(filterProtocols([a, b, c], sel).map((p) => p.id)).toEqual(["a"]);
  });

  it("a protocol with none of a selected facet's values is excluded", () => {
    expect(protocolMatchesSelections(a, { status: new Set(["retired"]) })).toBe(false);
  });
});
