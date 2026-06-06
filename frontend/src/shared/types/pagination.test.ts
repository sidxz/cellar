import { describe, expect, it } from "vitest";
import { unwrapList } from "./pagination";

describe("unwrapList", () => {
  it("returns a bare array unchanged", () => {
    const items = [1, 2, 3];
    expect(unwrapList(items)).toBe(items);
  });

  it("unwraps a paginated envelope to its items", () => {
    const items = [{ id: "a" }, { id: "b" }];
    expect(unwrapList({ items })).toBe(items);
  });

  it("handles an empty bare array", () => {
    expect(unwrapList<number>([])).toEqual([]);
  });

  it("handles an empty envelope", () => {
    expect(unwrapList<number>({ items: [] })).toEqual([]);
  });
});
