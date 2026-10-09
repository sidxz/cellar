import { describe, expect, it } from "vitest";
import { buildSuggestions, tokenAtCursor, validateFormula } from "./formula-tokens";

const protocols = [{ code: "PRT-00142", name: "PptT inhibition [FP]" }];

describe("cross-protocol references by code", () => {
  it("suggests by name and inserts the code", () => {
    const token = tokenAtCursor("@ppt", 4);
    expect(buildSuggestions(token, [], protocols)).toEqual([
      { value: "@{PRT-00142}.", kind: "protocol", hint: "PptT inhibition [FP]" },
    ]);
  });

  it("suggests by code", () => {
    const token = tokenAtCursor("@PRT-001", 8);
    expect(token.kind).toBe("@protocol");
    expect(buildSuggestions(token, [], protocols).map((s) => s.value)).toEqual(["@{PRT-00142}."]);
  });

  it("does not flag code references as unknown identifiers", () => {
    expect(validateFormula("@{PRT-00142}.{IC50} * Raw", ["Raw"]).unknownIdentifiers).toEqual([]);
    expect(validateFormula("@PRT-00142.IC50 * Raw", ["Raw"]).unknownIdentifiers).toEqual([]);
  });
});
