import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defaultNForSize, usePickerConfig } from "./use-picker-config";

// Mock next/navigation — production code reads URL once on mount via
// useSearchParams(); state transitions are React-owned + window.history side-effects.
let params = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => params,
  usePathname: () => "/",
}));

describe("usePickerConfig", () => {
  beforeEach(() => {
    params = new URLSearchParams();
  });

  it("defaults to maxmin n=10 when no collection size given", () => {
    const { result } = renderHook(() => usePickerConfig());
    expect(result.current.picker).toBe("maxmin");
    expect(result.current.n).toBe(10);
  });

  it("uses size-adaptive default N when collectionSize given", () => {
    const { result } = renderHook(() => usePickerConfig({ collectionSize: 22 }));
    // 22 * 0.1 = 2.2 → ceil = 3 → max(5, 3) = 5
    expect(result.current.n).toBe(5);
  });

  it("clamps N default to 50 ceiling for large collections", () => {
    const { result } = renderHook(() => usePickerConfig({ collectionSize: 5000 }));
    expect(result.current.n).toBe(50);
  });

  it("switching to butina swaps n for threshold default", () => {
    const { result } = renderHook(() => usePickerConfig());
    act(() => result.current.setPicker("butina"));
    expect(result.current.picker).toBe("butina");
    expect(result.current.threshold).toBe(0.4);
  });

  it("setN updates n value", () => {
    const { result } = renderHook(() => usePickerConfig());
    act(() => result.current.setN(100));
    expect(result.current.n).toBe(100);
  });

  it("setThreshold updates threshold value", () => {
    const { result } = renderHook(() => usePickerConfig());
    act(() => result.current.setPicker("butina"));
    act(() => result.current.setThreshold(0.7));
    expect(result.current.threshold).toBe(0.7);
  });

  it("switching back to maxmin restores size-adaptive default n", () => {
    const { result } = renderHook(() => usePickerConfig({ collectionSize: 200 }));
    act(() => result.current.setPicker("butina"));
    act(() => result.current.setPicker("maxmin"));
    expect(result.current.picker).toBe("maxmin");
    // 200 * 0.1 = 20
    expect(result.current.n).toBe(20);
  });

  it("defaultNForSize: floor 5, ceiling 50, ~10% midpoint", () => {
    expect(defaultNForSize(22)).toBe(5);
    expect(defaultNForSize(100)).toBe(10);
    expect(defaultNForSize(500)).toBe(50);
    expect(defaultNForSize(5000)).toBe(50);
    expect(defaultNForSize(1)).toBe(5);
  });

  it("reads picker from URL on mount", () => {
    params = new URLSearchParams("picker=butina&t=0.6");
    const { result } = renderHook(() => usePickerConfig());
    expect(result.current.picker).toBe("butina");
    expect(result.current.threshold).toBe(0.6);
  });
});
