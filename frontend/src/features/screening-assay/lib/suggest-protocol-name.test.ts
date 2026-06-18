import { describe, expect, it } from "vitest";
import { suggestProtocolName } from "./suggest-protocol-name";

describe("suggestProtocolName", () => {
  it("joins targets, primary readout, and a type label", () => {
    expect(
      suggestProtocolName({
        targetNames: ["ArgB", "ArgC"],
        readoutNames: ["IC50", "Hill slope"],
        protocolType: "biochemical",
      }),
    ).toBe("ArgB / ArgC · IC50 · Biochemical");
  });

  it("omits empty segments", () => {
    expect(
      suggestProtocolName({
        targetNames: [],
        readoutNames: ["% Inhibition"],
        protocolType: "cell_based",
      }),
    ).toBe("% Inhibition · Cell based");
  });

  it("returns '' when there is no signal", () => {
    expect(suggestProtocolName({ targetNames: [], readoutNames: [], protocolType: "" })).toBe("");
  });
});
