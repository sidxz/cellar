import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useCherrypickBasket } from "./use-cherrypick-basket";

describe("useCherrypickBasket", () => {
  beforeEach(() => window.localStorage.clear());

  it("starts empty", () => {
    const { result } = renderHook(() => useCherrypickBasket("col-1"));
    expect(result.current.size).toBe(0);
    expect([...result.current.ids]).toEqual([]);
  });

  it("add accumulates and addMany de-dupes overlaps", () => {
    const { result } = renderHook(() => useCherrypickBasket("col-1"));
    act(() => result.current.add("a"));
    act(() => result.current.addMany(["a", "b", "c"]));
    expect(result.current.size).toBe(3);
    expect(result.current.has("b")).toBe(true);
  });

  it("remove and removeMany take ids out", () => {
    const { result } = renderHook(() => useCherrypickBasket("col-1"));
    act(() => result.current.addMany(["a", "b", "c"]));
    act(() => result.current.remove("a"));
    act(() => result.current.removeMany(["b"]));
    expect([...result.current.ids]).toEqual(["c"]);
  });

  it("clear empties the basket", () => {
    const { result } = renderHook(() => useCherrypickBasket("col-1"));
    act(() => result.current.addMany(["a", "b"]));
    act(() => result.current.clear());
    expect(result.current.size).toBe(0);
  });

  it("persists across remounts (localStorage round-trip)", () => {
    const first = renderHook(() => useCherrypickBasket("col-1"));
    act(() => first.result.current.addMany(["a", "b"]));
    first.unmount();
    const second = renderHook(() => useCherrypickBasket("col-1"));
    expect([...second.result.current.ids].sort()).toEqual(["a", "b"]);
  });

  it("keys the basket per collection", () => {
    const a = renderHook(() => useCherrypickBasket("col-1"));
    act(() => a.result.current.add("x"));
    const b = renderHook(() => useCherrypickBasket("col-2"));
    expect(b.result.current.size).toBe(0);
  });
});
