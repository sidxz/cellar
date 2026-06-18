import { describe, expect, it } from "vitest";
import { ontologyAnnotationWrites } from "./ontology-annotation-writes";

const term = (id: string) => ({
  term_id: id,
  label: id,
  ontology_source: "BAO",
  uri: null,
});

describe("ontologyAnnotationWrites", () => {
  it("emits one write per non-empty slot, skipping empties", () => {
    const writes = ontologyAnnotationWrites({
      organism: [term("NCBITaxon:1773")],
      detection: [],
      assay_format: [term("BAO:0000019")],
    });
    expect(writes).toHaveLength(2);
    expect(writes.map((w) => w.slot).sort()).toEqual(["assay_format", "organism"]);
    expect(writes.find((w) => w.slot === "organism")?.terms[0].term_id).toBe("NCBITaxon:1773");
  });

  it("returns [] when nothing is annotated", () => {
    expect(ontologyAnnotationWrites({ organism: [], detection: [] })).toEqual([]);
  });
});
