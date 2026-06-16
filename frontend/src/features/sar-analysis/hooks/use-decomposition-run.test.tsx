import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useDecompositionRun } from "./use-decomposition-run";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const READY = {
  run_id: "run-1",
  status: "ready",
  rgroup_labels: ["R1", "R2"],
  matched_count: 8,
  unmatched_count: 2,
  total_count: 10,
  error_message: null,
};

describe("useDecompositionRun", () => {
  it("returns the run header inline when start is ready", async () => {
    const startFn = vi.fn().mockResolvedValue(READY);
    const pollFn = vi.fn();
    const { result } = renderHook(
      () => useDecompositionRun({ collectionId: "c1", coreSmiles: "c1ccccc1", startFn, pollFn }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.runId).toBe("run-1");
    expect(result.current.labels).toEqual(["R1", "R2"]);
    expect(result.current.counts).toEqual({ matched: 8, unmatched: 2, total: 10 });
    expect(pollFn).not.toHaveBeenCalled();
  });

  it("polls a pending run until ready", async () => {
    const startFn = vi.fn().mockResolvedValue({
      ...READY,
      status: "pending",
      rgroup_labels: [],
      matched_count: 0,
      unmatched_count: 0,
      total_count: 0,
    });
    const pollFn = vi.fn().mockResolvedValue(READY);
    const { result } = renderHook(
      () =>
        useDecompositionRun({
          collectionId: "c1",
          coreSmiles: "c1ccccc1",
          startFn,
          pollFn,
          pollIntervalMs: 5,
        }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.runId).toBe("run-1");
    expect(result.current.counts?.total).toBe(10);
    expect(pollFn).toHaveBeenCalled();
  });

  it("is disabled without a core", () => {
    const startFn = vi.fn();
    renderHook(
      () => useDecompositionRun({ collectionId: "c1", coreSmiles: null, startFn, pollFn: vi.fn() }),
      {
        wrapper: wrap(),
      },
    );
    expect(startFn).not.toHaveBeenCalled();
  });

  it("surfaces a cancelled poll via isCancelled, not error", async () => {
    const startFn = vi.fn().mockResolvedValue({ ...READY, status: "running" });
    const pollFn = vi.fn().mockResolvedValue({ ...READY, status: "cancelled" });
    const { result } = renderHook(
      () =>
        useDecompositionRun({
          collectionId: "c1",
          coreSmiles: "c1ccccc1",
          startFn,
          pollFn,
          pollIntervalMs: 5,
        }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.isCancelled).toBe(true));
    expect(result.current.error).toBeNull();
    expect(result.current.isPolling).toBe(false);
  });

  it("cancel() calls cancelFn and flips isCancelled optimistically", async () => {
    const startFn = vi.fn().mockResolvedValue({ ...READY, status: "running" });
    const pollFn = vi.fn().mockResolvedValue({ ...READY, status: "running" });
    const cancelFn = vi.fn().mockResolvedValue({ ...READY, status: "cancelled" });
    const { result } = renderHook(
      () =>
        useDecompositionRun({
          collectionId: "c1",
          coreSmiles: "c1ccccc1",
          startFn,
          pollFn,
          cancelFn,
          pollIntervalMs: 5,
        }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.runId).toBe("run-1"));
    act(() => result.current.cancel());
    expect(cancelFn).toHaveBeenCalledWith("run-1");
    await waitFor(() => expect(result.current.isCancelled).toBe(true));
  });

  it("runAgain() re-starts (a fresh POST) and clears the cancelled flag", async () => {
    const startFn = vi.fn().mockResolvedValue({ ...READY, status: "running" });
    const pollFn = vi.fn().mockResolvedValue({ ...READY, status: "cancelled" });
    const cancelFn = vi.fn().mockResolvedValue({ ...READY, status: "cancelled" });
    const { result } = renderHook(
      () =>
        useDecompositionRun({
          collectionId: "c1",
          coreSmiles: "c1ccccc1",
          startFn,
          pollFn,
          cancelFn,
          pollIntervalMs: 5,
        }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.isCancelled).toBe(true));
    act(() => result.current.runAgain());
    // No flicker: the nonce bump re-keys both the start and poll queries, so
    // startRun/runId/polledData reset atomically — isCancelled is false
    // immediately, not only after the new start resolves.
    expect(result.current.isCancelled).toBe(false);
    await waitFor(() => expect(startFn).toHaveBeenCalledTimes(2));
    expect(result.current.isCancelled).toBe(false);
  });
});
