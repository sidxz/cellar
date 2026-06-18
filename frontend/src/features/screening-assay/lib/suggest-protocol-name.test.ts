import { describe, expect, it } from "vitest";
import { suggestProtocolName } from "./suggest-protocol-name";

describe("suggestProtocolName", () => {
  it("joins targets, primary readout, and the type label", () => {
    expect(
      suggestProtocolName({
        targetNames: ["ArgB", "ArgC"],
        readoutNames: ["IC50", "Hill slope"],
        typeLabel: "Biochemical",
      }),
    ).toBe("ArgB / ArgC · IC50 · Biochemical");
  });

  it("omits empty segments", () => {
    expect(
      suggestProtocolName({ targetNames: [], readoutNames: ["% Inhibition"], typeLabel: "Cell-Based" }),
    ).toBe("% Inhibition · Cell-Based");
  });

  it("returns '' when there is no signal", () => {
    expect(suggestProtocolName({ targetNames: [], readoutNames: [], typeLabel: "" })).toBe("");
  });
});
