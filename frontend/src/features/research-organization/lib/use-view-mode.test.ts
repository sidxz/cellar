import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useViewMode } from "./use-view-mode";

// Mock next/navigation: useRouter().replace + useSearchParams + usePathname.
const replace = vi.fn();
let params = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => params,
  usePathname: () => "/collections/abc-123",
}));

describe("useViewMode", () => {
  beforeEach(() => {
    replace.mockClear();
    params = new URLSearchParams();
  });

  it("returns the default when no ?view= param is set", () => {
    const { result } = renderHook(() => useViewMode("cards"));
    expect(result.current.mode).toBe("cards");
  });

  it("returns the param value when ?view= is set to a valid mode", () => {
    params = new URLSearchParams("view=table");
    const { result } = renderHook(() => useViewMode("cards"));
    expect(result.current.mode).toBe("table");
  });

  it("falls back to default when ?view= is an unknown value", () => {
    params = new URLSearchParams("view=bogus");
    const { result } = renderHook(() => useViewMode("cards"));
    expect(result.current.mode).toBe("cards");
  });

  it("setMode rewrites the URL with the new ?view= param", () => {
    const { result } = renderHook(() => useViewMode("cards"));
    act(() => result.current.setMode("table"));
    expect(replace).toHaveBeenCalledWith("/collections/abc-123?view=table", { scroll: false });
  });

  it("setMode strips ?view= when the new mode matches the default", () => {
    params = new URLSearchParams("view=table");
    const { result } = renderHook(() => useViewMode("cards"));
    act(() => result.current.setMode("cards"));
    expect(replace).toHaveBeenCalledWith("/collections/abc-123", { scroll: false });
  });

  it("accepts 'scaffold-tree' as a valid mode (URL form 'tree')", () => {
    params = new URLSearchParams("view=tree");
    const { result } = renderHook(() => useViewMode("cards"));
    expect(result.current.mode).toBe("scaffold-tree");
  });

  it("setMode writes ?view=tree for scaffold-tree and strips it at default", () => {
    const { result } = renderHook(() => useViewMode("cards"));
    act(() => result.current.setMode("scaffold-tree"));
    expect(replace).toHaveBeenCalledWith("/collections/abc-123?view=tree", { scroll: false });
  });
});
