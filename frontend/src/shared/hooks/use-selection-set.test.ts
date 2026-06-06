import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useSelectionSet } from "./use-selection-set";

describe("useSelectionSet", () => {
  it("starts empty by default", () => {
    const { result } = renderHook(() => useSelectionSet<string>());
    expect(result.current.selected.size).toBe(0);
    expect(result.current.has("a")).toBe(false);
  });

  it("seeds from an initial iterable", () => {
    const { result } = renderHook(() => useSelectionSet<string>(["a", "b"]));
    expect(result.current.selected.size).toBe(2);
    expect(result.current.has("a")).toBe(true);
    expect(result.current.has("b")).toBe(true);
  });

  it("set(id, true) adds and set(id, false) removes", () => {
    const { result } = renderHook(() => useSelectionSet<string>());
    act(() => result.current.set("a", true));
    expect(result.current.has("a")).toBe(true);
    act(() => result.current.set("a", false));
    expect(result.current.has("a")).toBe(false);
  });

  it("set(id, false) on an absent id is a no-op", () => {
    const { result } = renderHook(() => useSelectionSet<string>());
    act(() => result.current.set("missing", false));
    expect(result.current.selected.size).toBe(0);
  });

  it("toggle(id) flips membership", () => {
    const { result } = renderHook(() => useSelectionSet<string>());
    act(() => result.current.toggle("a"));
    expect(result.current.has("a")).toBe(true);
    act(() => result.current.toggle("a"));
    expect(result.current.has("a")).toBe(false);
  });

  it("clear() empties the selection", () => {
    const { result } = renderHook(() => useSelectionSet<string>(["a", "b"]));
    act(() => result.current.clear());
    expect(result.current.selected.size).toBe(0);
  });

  it("treats the backing set immutably (new reference per change)", () => {
    const { result } = renderHook(() => useSelectionSet<string>());
    const before = result.current.selected;
    act(() => result.current.set("a", true));
    expect(result.current.selected).not.toBe(before);
  });

  it("keeps set/toggle/clear references stable across renders", () => {
    const { result, rerender } = renderHook(() => useSelectionSet<string>());
    const first = {
      set: result.current.set,
      toggle: result.current.toggle,
      clear: result.current.clear,
    };
    act(() => result.current.set("a", true));
    rerender();
    expect(result.current.set).toBe(first.set);
    expect(result.current.toggle).toBe(first.toggle);
    expect(result.current.clear).toBe(first.clear);
  });
});
