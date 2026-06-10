import { beforeEach, describe, expect, it } from "vitest";
import { readSarHandoff, stashSarHandoff } from "./sar-handoff";

describe("sar handoff", () => {
  beforeEach(() => window.sessionStorage.clear());
  it("round-trips a core + molecule ids", () => {
    stashSarHandoff({ coreSmiles: "c1ccccc1", moleculeIds: ["a", "b"] });
    expect(readSarHandoff()).toEqual({ coreSmiles: "c1ccccc1", moleculeIds: ["a", "b"] });
  });
  it("read clears the stash (one-shot)", () => {
    stashSarHandoff({ coreSmiles: "c1ccccc1", moleculeIds: ["a"] });
    readSarHandoff();
    expect(readSarHandoff()).toBeNull();
  });
  it("returns null for a malformed stash", () => {
    window.sessionStorage.setItem("cellar:sar-handoff", JSON.stringify({ coreSmiles: 123 }));
    expect(readSarHandoff()).toBeNull();
  });
});
