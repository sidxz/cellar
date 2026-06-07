import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement } from "react";
import type React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock customInstance so tests don't require a live Sentinel/localStorage.
const mockCustomInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (...args: unknown[]) => mockCustomInstance(...args),
}));

// Mock downloadFile so tests don't require a live auth session or blob URLs.
const mockDownloadFile = vi.fn();
vi.mock("@/shared/lib/api/download", () => ({
  downloadFile: (...args: unknown[]) => mockDownloadFile(...args),
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

// useExport composes useJobPoll, which runs as a TanStack Query — so the hook
// needs a QueryClientProvider. A fresh client per test keeps the poll cache
// isolated. retry:false so a rejected poll surfaces immediately.
function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return createElement(QueryClientProvider, { client: qc }, children);
}

const renderUseExport = () => renderHook(() => useExport(), { wrapper });

// ── setup ─────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockCustomInstance.mockReset();
  mockDownloadFile.mockReset();
  mockDownloadFile.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── tests ─────────────────────────────────────────────────────────────────

describe("useExport", () => {
  it("starts idle: job null, isPending false, error null", () => {
    const { result } = renderUseExport();
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

    const { result } = renderUseExport();

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await waitFor(() => expect(result.current.job?.status).toBe("ready"), { timeout: 3000 });

    expect(result.current.isPending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(mockDownloadFile).toHaveBeenCalledOnce();
    expect(mockDownloadFile).toHaveBeenCalledWith({
      url: "/api/v1/exports/j1/download",
      method: "GET",
      filename: "export.csv",
    });
  });

  it("sets error on failed status", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ job_id: "j2" })
      .mockResolvedValueOnce(
        makeJob({ id: "j2", status: "failed", error_message: "Out of memory" }),
      );

    const { result } = renderUseExport();

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await waitFor(() => expect(result.current.error).toBe("Out of memory"), { timeout: 3000 });
    expect(result.current.isPending).toBe(false);
  });

  it("sets error when poll throws", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ job_id: "j3" })
      .mockRejectedValueOnce(new Error("Network offline"));

    const { result } = renderUseExport();

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await waitFor(() => expect(result.current.error).toContain("Network offline"), {
      timeout: 3000,
    });
  });

  it("reset clears job and error", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ job_id: "j4" })
      .mockResolvedValueOnce(makeJob({ id: "j4", status: "failed", error_message: "bad" }));

    const { result } = renderUseExport();

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await waitFor(() => expect(result.current.error).toBe("bad"), { timeout: 3000 });

    act(() => {
      result.current.reset();
    });

    expect(result.current.job).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isPending).toBe(false);
  });

  it("isPending true while job is running", async () => {
    // POST → job_id; every poll returns "running" so the job never reaches a
    // terminal state — isPending stays true.
    mockCustomInstance.mockImplementation(async (cfg: { method: string; url: string }) => {
      if (cfg.method === "POST" && cfg.url.endsWith("/exports")) return { job_id: "j5" };
      return makeJob({ id: "j5", status: "running" });
    });

    const { result } = renderUseExport();

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await waitFor(() => expect(result.current.job?.status).toBe("running"), { timeout: 3000 });
    expect(result.current.isPending).toBe(true);
  });

  it("cancel stops polling and calls the cancel endpoint", async () => {
    mockCustomInstance.mockImplementation(async (cfg: { method: string; url: string }) => {
      if (cfg.method === "POST" && cfg.url.endsWith("/exports")) return { job_id: "j6" };
      if (cfg.url.includes("/cancel")) return undefined;
      return makeJob({ id: "j6", status: "running" });
    });

    const { result } = renderUseExport();

    await act(async () => {
      await result.current.start({ source: "search", format: "csv", payload: {} });
    });

    await waitFor(() => expect(result.current.job?.status).toBe("running"), { timeout: 3000 });

    await act(async () => {
      await result.current.cancel();
    });

    const cancelCall = mockCustomInstance.mock.calls.find(
      (c) =>
        typeof c[0]?.url === "string" && c[0].url.includes("/cancel") && c[0].method === "POST",
    );
    expect(cancelCall).toBeDefined();
  });
});
