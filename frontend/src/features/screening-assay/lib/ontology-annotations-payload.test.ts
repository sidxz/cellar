import { describe, expect, it } from "vitest";
import { ontologyAnnotationsPayload } from "./ontology-annotations-payload";

const term = (label: string) => ({
  term_id: `free_text:${label}`,
  label,
  ontology_source: "free_text",
  uri: null,
});

describe("ontologyAnnotationsPayload", () => {
  it("keeps every non-empty slot (create-time facets are atomic — nothing dropped)", () => {
    const payload = ontologyAnnotationsPayload({
      organism: [term("Homo sapiens")],
      assay_format: [term("biochemical")],
      detection: [term("fluorescence")],
    });
    expect(Object.keys(payload).sort()).toEqual(["assay_format", "detection", "organism"]);
    expect(payload.assay_format[0].label).toBe("biochemical");
    expect(payload.detection[0].label).toBe("fluorescence");
  });

  it("drops empty slots so we never POST {slot: []}", () => {
    expect(ontologyAnnotationsPayload({ organism: [], detection: [] })).toEqual({});
  });
});
