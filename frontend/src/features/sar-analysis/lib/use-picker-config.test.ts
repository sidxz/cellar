import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { usePickerConfig } from "./use-picker-config";

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

  it("defaults to maxmin n=50", () => {
    const { result } = renderHook(() => usePickerConfig());
    expect(result.current.picker).toBe("maxmin");
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

  it("switching back to maxmin restores default n", () => {
    const { result } = renderHook(() => usePickerConfig());
    act(() => result.current.setPicker("butina"));
    act(() => result.current.setPicker("maxmin"));
    expect(result.current.picker).toBe("maxmin");
    expect(result.current.n).toBe(50);
  });

  it("reads picker from URL on mount", () => {
    params = new URLSearchParams("picker=butina&t=0.6");
    const { result } = renderHook(() => usePickerConfig());
    expect(result.current.picker).toBe("butina");
    expect(result.current.threshold).toBe(0.6);
  });
});
