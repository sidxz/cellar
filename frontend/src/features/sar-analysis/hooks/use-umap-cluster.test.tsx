import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { useUmapCluster } from "./use-umap-cluster";
import type { UmapResult, UmapJob } from "../types";

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const makeResultDto = () => ({
  points: [{ molecule_id: "a", x: 1.0, y: 2.0 }],
  clusters: [{ molecule_id: "a", cluster_id: 0 }],
  representatives: [{ molecule_id: "a", cluster_id: 0 }],
  cluster_count: 1,
  picker: "maxmin",
  picker_params: { n: 5 },
  skipped_molecule_ids: [],
});

const makeJobDto = (status: string, extra: Record<string, unknown> = {}) => ({
  id: "job-1",
  status,
  picker: "maxmin",
  picker_params: { n: 5 },
  ...extra,
});

describe("useUmapCluster", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns inline result when BE replies synchronously (small set)", async () => {
    const startFn = vi.fn(async () => ({ result: makeResultDto(), job: null }));
    const pollFn = vi.fn();

    const { result } = renderHook(
      () =>
        useUmapCluster({
          moleculeIds: ["a"],
          picker: "maxmin",
          n: 5,
          enabled: true,
          startFn,
          pollFn,
        }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.result).not.toBeNull());

    expect(result.current.result!.points).toHaveLength(1);
    expect(result.current.result!.points[0].moleculeId).toBe("a");
    expect(result.current.result!.clusterCount).toBe(1);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(pollFn).not.toHaveBeenCalled();
  });

  it("polls until job is ready then returns result", async () => {
    const startFn = vi.fn(async () => ({
      result: null,
      job: makeJobDto("pending"),
    }));

    let pollCount = 0;
    const pollFn = vi.fn(async () => {
      pollCount++;
      if (pollCount < 2) return makeJobDto("running");
      return { ...makeJobDto("ready"), result: makeResultDto() };
    });

    const { result } = renderHook(
      () =>
        useUmapCluster({
          moleculeIds: ["a", "b"],
          picker: "maxmin",
          n: 5,
          enabled: true,
          startFn,
          pollFn,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.result).not.toBeNull(), {
      timeout: 3000,
    });

    expect(pollFn).toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("surfaces error when job fails", async () => {
    const startFn = vi.fn(async () => ({
      result: null,
      job: makeJobDto("pending"),
    }));

    const pollFn = vi.fn(async () =>
      makeJobDto("failed", { error_message: "compute boom" }),
    );

    const { result } = renderHook(
      () =>
        useUmapCluster({
          moleculeIds: ["a"],
          picker: "maxmin",
          n: 5,
          enabled: true,
          startFn,
          pollFn,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.error).not.toBeNull(), {
      timeout: 3000,
    });

    expect(result.current.error).toContain("compute boom");
    expect(result.current.result).toBeNull();
  });

  it("does nothing when enabled=false", () => {
    const startFn = vi.fn();
    const pollFn = vi.fn();

    renderHook(
      () =>
        useUmapCluster({
          moleculeIds: ["a"],
          picker: "maxmin",
          n: 5,
          enabled: false,
          startFn: startFn as any,
          pollFn: pollFn as any,
        }),
      { wrapper },
    );

    expect(startFn).not.toHaveBeenCalled();
    expect(pollFn).not.toHaveBeenCalled();
  });

  it("does nothing when moleculeIds is empty and no collectionId", () => {
    const startFn = vi.fn();

    renderHook(
      () =>
        useUmapCluster({
          moleculeIds: [],
          picker: "maxmin",
          n: 5,
          enabled: true,
          startFn: startFn as any,
        }),
      { wrapper },
    );

    expect(startFn).not.toHaveBeenCalled();
  });

  it("cancel callback invokes pollFn-based cancellation path", async () => {
    const startFn = vi.fn(async () => ({
      result: null,
      job: makeJobDto("pending"),
    }));
    // poll always stays pending so we can call cancel before completion
    const pollFn = vi.fn(async () => makeJobDto("pending"));
    const cancelFn = vi.fn(async () => {});

    const { result } = renderHook(
      () =>
        useUmapCluster({
          moleculeIds: ["a"],
          picker: "maxmin",
          n: 5,
          enabled: true,
          startFn,
          pollFn,
          cancelFn,
          pollIntervalMs: 200,
        }),
      { wrapper },
    );

    // Wait for async job to be set (poll starts)
    await waitFor(() => expect(result.current.job).not.toBeNull(), {
      timeout: 1000,
    });

    result.current.cancel();

    await waitFor(() => expect(cancelFn).toHaveBeenCalled(), { timeout: 1000 });
  });
});
