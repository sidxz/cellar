import { describe, expect, it } from "vitest";
import { SHORT_ID_LEN, shortId } from "./utils";

describe("shortId", () => {
  it("returns the first SHORT_ID_LEN characters of a UUID", () => {
    const id = "0f8fad5b-d9cb-469f-a165-70867728950e";
    expect(shortId(id)).toBe("0f8fad5b");
    expect(shortId(id)).toHaveLength(SHORT_ID_LEN);
  });

  it("does not append an ellipsis", () => {
    expect(shortId("abcdefghijkl")).toBe("abcdefgh");
  });

  it("returns the whole string when shorter than SHORT_ID_LEN", () => {
    expect(shortId("abc")).toBe("abc");
  });

  it("returns an empty string for an empty input", () => {
    expect(shortId("")).toBe("");
  });
});
