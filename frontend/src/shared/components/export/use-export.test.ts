import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Mock customInstance so tests don't require a live Sentinel/localStorage.
const mockCustomInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", () => ({
  customInstance: (...args: unknown[]) => mockCustomInstance(...args),
}));

import { useExport } from "./use-export";

// ── helpers ────────────────────────────────────────────────────────────────

function makeJob(overrides: Record<string, unknown> = {}) {
  return {
    id: "j1",
    status: "running",
    format: "csv",
    row_count: 100,
    progress: 0,
    error_message: null,
    download_url: null,
    byte_size: null,
    filename: "export.csv",
    requested_at: "2026-05-16T00:00:00Z",
    completed_at: null,
    expires_at: null,
    ...overrides,
  };
}

// ── setup ─────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers();
  mockCustomInstance.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

// Helper: flush all pending timers + microtasks inside act so React state
// updates are applied. Works with vi.useFakeTimers().
async function flushTimers() {
  await act(async () => {
    await vi.runAllTimersAsync();
  });
}

// Helper: flush a single timer tick (fires the next pending timer then drains microtasks).
async function flushNextTimer() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(600);
  });
}

// ── tests ─────────────────────────────────────────────────────────────────

describe("useExport", () => {
  it("starts idle: job null, isPending false, error null", () => {
    const { result } = renderHook(() => useExport());
    expect(result.current.job).toBeNull();
    expect(result.current.isPending).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("starts then polls until ready and triggers download", async () => {
    mockCustomInstance
      // POST /exports → { job_id }
      .mockResolvedValueOnce({ job_id: "j1" })
      // GET /exports/j1 → running
      .mockResolvedValueOnce(makeJob({ status: "running", progress: 0.3 }))
      // GET /exports/j1 → ready
      .mockResolvedValueOnce(
        makeJob({
          status: "ready",
          progress: 1.0,
          download_url: "/api/v1/exports/j1/download",
          byte_size: 1234,
          completed_at: "2026-05-16T00:00:01Z",
          expires_at: "2026-05-16T01:00:00Z",
        }),
      );

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const { result } = renderHook(() => useExport());

    // Kick off: POST fires, poll() called immediately (no timer), first GET fires.
    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    // At this point: first GET either resolved or is in-flight.
    // Drain microtasks + fire the 500ms timer for the second poll.
    await flushTimers();
    // Drain microtasks from the second poll resolving.
    await flushTimers();

    expect(result.current.job?.status).toBe("ready");
    expect(result.current.isPending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(clickSpy).toHaveBeenCalledOnce();
  });

  it("sets error on failed status", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ job_id: "j2" })
      .mockResolvedValueOnce(
        makeJob({ id: "j2", status: "failed", error_message: "Out of memory" }),
      );

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    // First poll → failed (no retry timer scheduled)
    await flushTimers();

    expect(result.current.error).toBe("Out of memory");
    expect(result.current.isPending).toBe(false);
  });

  it("sets error when poll throws", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ job_id: "j3" })
      .mockRejectedValueOnce(new Error("Network offline"));

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await flushTimers();

    expect(result.current.error).toBe("Network offline");
  });

  it("reset clears job and error", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ job_id: "j4" })
      .mockResolvedValueOnce(
        makeJob({ id: "j4", status: "failed", error_message: "bad" }),
      );

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await flushTimers();
    expect(result.current.error).toBe("bad");

    act(() => {
      result.current.reset();
    });

    expect(result.current.job).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isPending).toBe(false);
  });

  it("isPending true while job is running", async () => {
    // POST → job_id; first poll → running. We assert BEFORE the second poll fires.
    mockCustomInstance
      .mockResolvedValueOnce({ job_id: "j5" })
      .mockResolvedValueOnce(makeJob({ id: "j5", status: "running" }));

    const { result } = renderHook(() => useExport());

    // start() fires POST then immediately calls poll() (no timer).
    // act flushes the POST + the first GET resolution + setJob("running") call.
    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    // Advance time to flush the first poll's Promise resolution (it was fired without a timer).
    // The second poll is scheduled 500ms later — we only advance 1ms so it doesn't fire.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    // job should now be "running" and isPending should be true.
    expect(result.current.job?.status).toBe("running");
    expect(result.current.isPending).toBe(true);
  });

  it("cancel stops polling and calls the cancel endpoint", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ job_id: "j6" })
      .mockResolvedValueOnce(makeJob({ id: "j6", status: "running" }))
      // cancel endpoint (POST /exports/j6/cancel)
      .mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(result.current.job?.status).toBe("running");

    await act(async () => {
      await result.current.cancel();
    });

    const calls = mockCustomInstance.mock.calls;
    const cancelCall = calls.find(
      (c) => typeof c[0]?.url === "string" && c[0].url.includes("/cancel") && c[0].method === "POST",
    );
    expect(cancelCall).toBeDefined();
  });
});
