import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { useColorMode } from "./use-color-mode";

// Mock next/navigation — production code reads URL once on mount via
// useSearchParams(); state transitions are React-owned + window.history side-effects.
let params = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => params,
  usePathname: () => "/",
}));

describe("useColorMode", () => {
  beforeEach(() => {
    params = new URLSearchParams();
  });

  it("defaults to cluster", () => {
    const { result } = renderHook(() =>
      useColorMode({ defaultMode: "cluster" }),
    );
    expect(result.current.mode).toBe("cluster");
  });

  it("switching to activity preserves protocol id", () => {
    const { result } = renderHook(() =>
      useColorMode({ defaultMode: "cluster" }),
    );
    act(() => result.current.setMode("activity", "proto-1"));
    expect(result.current.mode).toBe("activity");
    expect(result.current.protocolId).toBe("proto-1");
  });

  it("switching away from activity clears protocolId", () => {
    const { result } = renderHook(() =>
      useColorMode({ defaultMode: "cluster" }),
    );
    act(() => result.current.setMode("activity", "proto-1"));
    act(() => result.current.setMode("scaffold"));
    expect(result.current.mode).toBe("scaffold");
    expect(result.current.protocolId).toBeNull();
  });

  it("switching back to default clears the color param", () => {
    const { result } = renderHook(() =>
      useColorMode({ defaultMode: "cluster" }),
    );
    act(() => result.current.setMode("scaffold"));
    act(() => result.current.setMode("cluster"));
    expect(result.current.mode).toBe("cluster");
  });

  it("defaults to none when defaultMode is none", () => {
    const { result } = renderHook(() => useColorMode({ defaultMode: "none" }));
    expect(result.current.mode).toBe("none");
  });

  it("reads color mode from URL on mount", () => {
    params = new URLSearchParams("color=activity&color-protocol=proto-42");
    const { result } = renderHook(() =>
      useColorMode({ defaultMode: "cluster" }),
    );
    expect(result.current.mode).toBe("activity");
    expect(result.current.protocolId).toBe("proto-42");
  });

  it("ignores unknown color values from URL", () => {
    params = new URLSearchParams("color=bogus");
    const { result } = renderHook(() =>
      useColorMode({ defaultMode: "cluster" }),
    );
    expect(result.current.mode).toBe("cluster");
  });
});
