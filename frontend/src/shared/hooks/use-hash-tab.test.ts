import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useHashTab } from "./use-hash-tab";

function clearHash() {
  window.location.hash = "";
  // Remove the trailing '#' that assigning "" leaves in some jsdom versions.
  window.history.replaceState(null, "", window.location.pathname);
}

describe("useHashTab", () => {
  beforeEach(() => {
    clearHash();
  });

  afterEach(() => {
    clearHash();
  });

  it("returns defaultTab when hash is empty", () => {
    const { result } = renderHook(() => useHashTab("overview"));
    expect(result.current[0]).toBe("overview");
  });

  it("returns the hash value when hash is set", () => {
    window.location.hash = "#results";
    const { result } = renderHook(() => useHashTab("overview"));
    expect(result.current[0]).toBe("results");
  });

  it("setTab updates the hash", () => {
    const { result } = renderHook(() => useHashTab("overview"));
    act(() => {
      result.current[1]("results");
    });
    expect(result.current[0]).toBe("results");
    // When not equal to defaultTab, the hash is written.
    expect(window.location.hash).toBe("#results");
  });

  it("setTab clears the hash when tab equals defaultTab", () => {
    window.location.hash = "#results";
    const { result } = renderHook(() => useHashTab("overview"));
    act(() => {
      result.current[1]("overview");
    });
    expect(result.current[0]).toBe("overview");
    // Hash should be absent when tab matches the default.
    expect(window.location.hash).toBe("");
  });

  it("reconciles tab when defaultTab changes", () => {
    // Hash is empty; first default is "overview".
    const { result, rerender } = renderHook(
      ({ defaultTab }: { defaultTab: string }) => useHashTab(defaultTab),
      { initialProps: { defaultTab: "overview" } },
    );
    expect(result.current[0]).toBe("overview");

    // Changing defaultTab with no hash should reconcile to the new default.
    rerender({ defaultTab: "results" });
    expect(result.current[0]).toBe("results");
  });

  it("does not cause a state update if hashchange resolves to the same tab", () => {
    window.location.hash = "#details";
    let renderCount = 0;
    const { result } = renderHook(() => {
      renderCount++;
      return useHashTab("overview");
    });
    expect(result.current[0]).toBe("details");

    const rendersBefore = renderCount;

    // Fire a hashchange that resolves to the same value — no re-render expected.
    act(() => {
      // Simulate a hashchange event without actually changing the hash.
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(result.current[0]).toBe("details");
    expect(renderCount).toBe(rendersBefore);
  });
});
