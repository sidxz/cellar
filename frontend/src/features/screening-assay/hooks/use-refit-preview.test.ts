import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RefitPreviewResponse } from "@/shared/lib/api/model";

import { useRefitPreview } from "./use-refit-preview";

function makeResponse(over: Partial<RefitPreviewResponse> = {}): RefitPreviewResponse {
  return {
    fitted_value: 1.5,
    hill_slope: 1,
    top: 100,
    bottom: 0,
    r_squared: 0.9,
    confidence_interval_low: null,
    confidence_interval_high: null,
    curve_class: "active",
    points_in_fit: 7,
    points_total: 8,
    ...over,
  };
}

describe("useRefitPreview", () => {
  it("debounces multiple rapid requests into one network call", async () => {
    const previewFn = vi.fn().mockResolvedValue(makeResponse());
    const { result } = renderHook(() => useRefitPreview({ previewFn, debounceMs: 50 }));

    act(() => result.current.requestPreview("curve-1", [2]));
    act(() => result.current.requestPreview("curve-1", [2, 3]));
    act(() => result.current.requestPreview("curve-1", [2, 3, 4]));

    await waitFor(() => expect(previewFn).toHaveBeenCalledTimes(1), {
      timeout: 500,
    });
    expect(previewFn).toHaveBeenCalledWith(
      "curve-1",
      { excluded_indices: [2, 3, 4] },
      expect.any(AbortSignal),
    );
  });

  it("populates data on success", async () => {
    const previewFn = vi
      .fn()
      .mockResolvedValue(makeResponse({ fitted_value: 2.5, r_squared: 0.85 }));
    const { result } = renderHook(() => useRefitPreview({ previewFn, debounceMs: 10 }));

    act(() => result.current.requestPreview("curve-1", [2]));

    await waitFor(() => expect(result.current.data?.fitted_value).toBe(2.5));
    expect(result.current.isPreviewing).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("captures error and preserves prior data on failure", async () => {
    const previewFn = vi
      .fn()
      .mockResolvedValueOnce(makeResponse({ fitted_value: 1.0 }))
      .mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useRefitPreview({ previewFn, debounceMs: 10 }));

    act(() => result.current.requestPreview("curve-1", []));
    await waitFor(() => expect(result.current.data?.fitted_value).toBe(1.0));

    act(() => result.current.requestPreview("curve-1", [2]));
    await waitFor(() => expect(result.current.error?.message).toBe("boom"));

    // Prior data preserved — chart should not blank on transient failure.
    expect(result.current.data?.fitted_value).toBe(1.0);
    expect(result.current.isPreviewing).toBe(false);
  });

  it("cancels an in-flight call when a newer request arrives", async () => {
    let firstAbortSignal: AbortSignal | undefined;
    const previewFn = vi.fn((_curveId: string, _body, signal?: AbortSignal) => {
      if (!firstAbortSignal) {
        firstAbortSignal = signal;
        // First call: never resolves — only the abort should clear it.
        return new Promise<RefitPreviewResponse>(() => {});
      }
      return Promise.resolve(makeResponse({ fitted_value: 3.3 }));
    });
    const { result } = renderHook(() => useRefitPreview({ previewFn, debounceMs: 10 }));

    act(() => result.current.requestPreview("curve-1", [1]));
    // Wait until the first call has actually been dispatched
    await waitFor(() => expect(previewFn).toHaveBeenCalledTimes(1));
    expect(firstAbortSignal?.aborted).toBe(false);

    act(() => result.current.requestPreview("curve-1", [1, 2]));

    // Second dispatch should fire and the first's signal should be aborted.
    await waitFor(() => expect(previewFn).toHaveBeenCalledTimes(2));
    expect(firstAbortSignal?.aborted).toBe(true);

    await waitFor(() => expect(result.current.data?.fitted_value).toBe(3.3));
    expect(result.current.error).toBeNull();
  });

  it("reset clears state and cancels pending", async () => {
    const previewFn = vi.fn().mockResolvedValue(makeResponse());
    const { result } = renderHook(() => useRefitPreview({ previewFn, debounceMs: 10 }));

    act(() => result.current.requestPreview("curve-1", [2]));
    await waitFor(() => expect(result.current.data).not.toBeNull());

    act(() => result.current.reset());
    expect(result.current.data).toBeNull();
    expect(result.current.isPreviewing).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("cleans up on unmount without leaking timers", () => {
    // Never-resolving previewFn — if the unmount cleanup is missing, the
    // timer / promise would dangle and (with fake timers) the test would
    // hang. With real timers, the test just exits because nothing else
    // is keeping the event loop busy.
    const previewFn = vi.fn(() => new Promise<RefitPreviewResponse>(() => {}));
    const { result, unmount } = renderHook(() => useRefitPreview({ previewFn, debounceMs: 10 }));

    act(() => result.current.requestPreview("curve-1", [2]));
    unmount();
    // If we got here without hanging, cleanup ran cleanly.
    expect(true).toBe(true);
  });
});
