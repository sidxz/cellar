import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useScaffoldTree } from "./use-scaffold-tree";

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

describe("useScaffoldTree", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns tree directly when BE replies with inline tree", async () => {
    const startMock = vi.fn(async () => ({
      tree: { nodes: [], edges: [], stats: { node_count: 0, elapsed_ms: 5, cache_hit: false } },
      job: null,
    }));
    const { result } = renderHook(
      () => useScaffoldTree({ moleculeIds: ["m1"], startFn: startMock }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.tree).toBeTruthy());
    expect(result.current.tree?.stats.cache_hit).toBe(false);
    expect(result.current.isPolling).toBe(false);
  });

  it("polls when BE replies with job, then returns tree on ready", async () => {
    const startMock = vi.fn(async () => ({
      tree: null,
      job: { id: "job-1", status: "pending" as const, ids_hash: "h", requested_at: "now" },
    }));
    let pollCount = 0;
    const pollMock = vi.fn(async () => {
      pollCount++;
      if (pollCount < 2) {
        return { id: "job-1", status: "running" as const, ids_hash: "h", requested_at: "now" };
      }
      return {
        id: "job-1",
        status: "ready" as const,
        ids_hash: "h",
        requested_at: "now",
        tree: { nodes: [], edges: [], stats: { node_count: 0, elapsed_ms: 50, cache_hit: false } },
      };
    });
    const { result } = renderHook(
      () =>
        useScaffoldTree({
          moleculeIds: ["m1", "m2"],
          startFn: startMock,
          pollFn: pollMock,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.tree).toBeTruthy(), { timeout: 2000 });
    expect(pollMock).toHaveBeenCalled();
  });

  it("surfaces error on job failure", async () => {
    const startMock = vi.fn(async () => ({
      tree: null,
      job: { id: "job-2", status: "pending" as const, ids_hash: "h", requested_at: "now" },
    }));
    const pollMock = vi.fn(async () => ({
      id: "job-2",
      status: "failed" as const,
      ids_hash: "h",
      requested_at: "now",
      error_message: "boom",
    }));
    const { result } = renderHook(
      () =>
        useScaffoldTree({
          moleculeIds: ["m1"],
          startFn: startMock,
          pollFn: pollMock,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.error).toBeTruthy(), { timeout: 2000 });
  });

  it("does not fire when moleculeIds is empty", () => {
    const startMock = vi.fn();
    renderHook(() => useScaffoldTree({ moleculeIds: [], startFn: startMock as any }), { wrapper });
    expect(startMock).not.toHaveBeenCalled();
  });
});
