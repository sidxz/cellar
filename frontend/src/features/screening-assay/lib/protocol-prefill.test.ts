import { describe, expect, it } from "vitest";
import type { Protocol } from "../types";
import { prefillFromProtocol } from "./protocol-prefill";

const source = {
  id: "p1",
  protocol_type: "cell_based",
  category: "Growth inhibition",
  description: "d",
  dose_unit: "uM",
  discriminator: "resazurin",
  targets: [{ id: "t1" }],
  aliases: [{ label: "MABA", kind: "nickname" }],
  ontology_annotations: { organism: [{ term_id: "x", label: "Mtb" }] },
  references: [
    { kind: "doi", value: "10.1021/jm901137j" },
    { kind: "chembl_assay", value: "CHEMBL1054500" },
    { kind: "pmid", value: "19919034" },
  ],
  readout_definitions: [
    {
      name: "MIC",
      data_type: "numeric",
      unit: "uM",
      is_calculated: false,
      display_order: 1,
    },
  ],
  condition_definitions: [
    {
      name: "Stage",
      data_type: "pick_list",
      unit: null,
      pick_list_values: ["a", "b"],
      fixed_value: "a",
    },
  ],
} as unknown as Protocol;

describe("prefillFromProtocol", () => {
  const out = prefillFromProtocol(source);

  it("copies the facts, the form and the conditions with pick lists and fixed values", () => {
    expect(out.values.category).toBe("Growth inhibition");
    expect(out.values.target_ids).toEqual(["t1"]);
    expect(out.values.readouts.map((r) => r.name)).toEqual(["MIC"]);
    expect(out.values.conditions).toEqual([
      {
        name: "Stage",
        data_type: "pick_list",
        unit: "",
        pick_list_values: ["a", "b"],
        fixed_value: "a",
      },
    ]);
    expect(out.ontologyAnnotations).toEqual(source.ontology_annotations);
  });

  it("does not copy the discriminator or nicknames", () => {
    expect(out.values.discriminator).toBe("");
    expect(out).not.toHaveProperty("nicknames");
  });

  it("copies paper-level references only", () => {
    expect(out.references.map((r) => r.kind)).toEqual(["doi", "pmid"]);
  });
});
