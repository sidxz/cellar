import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type React from "react";
import { describe, expect, it, vi } from "vitest";

import { isTerminalJobStatus, useJobPoll } from "./use-job-poll";

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

// Minimal "job-shaped" poll response: the GET returns the job itself.
type Job = { id: string; status: string; payload?: string; error_message?: string };

const jobExtractors = {
  getStatus: (j: Job) => j.status,
  getResult: (j: Job) => (j.status === "ready" ? (j.payload ?? null) : null),
  getError: (j: Job) => (j.status === "failed" ? (j.error_message ?? "compute failed") : null),
};

describe("isTerminalJobStatus", () => {
  it("treats ready/failed/cancelled as terminal and everything else as live", () => {
    expect(isTerminalJobStatus("ready")).toBe(true);
    expect(isTerminalJobStatus("failed")).toBe(true);
    expect(isTerminalJobStatus("cancelled")).toBe(true);
    expect(isTerminalJobStatus("running")).toBe(false);
    expect(isTerminalJobStatus("pending")).toBe(false);
    expect(isTerminalJobStatus(null)).toBe(false);
    expect(isTerminalJobStatus(undefined)).toBe(false);
  });
});

describe("useJobPoll", () => {
  it("does not poll when there is no job", () => {
    const pollFn = vi.fn();
    const { result } = renderHook(
      () =>
        useJobPoll<Job, string>({
          job: null,
          pollFn,
          ...jobExtractors,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );
    expect(pollFn).not.toHaveBeenCalled();
    expect(result.current.isPolling).toBe(false);
    expect(result.current.result).toBeNull();
  });

  it("does not poll when the job is already terminal", () => {
    const pollFn = vi.fn();
    const { result } = renderHook(
      () =>
        useJobPoll<Job, string>({
          job: { id: "j", status: "ready" },
          pollFn,
          ...jobExtractors,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );
    expect(pollFn).not.toHaveBeenCalled();
    expect(result.current.isPolling).toBe(false);
  });

  it("polls a live job until ready, then exposes the result and stops", async () => {
    let count = 0;
    const pollFn = vi.fn(async (): Promise<Job> => {
      count++;
      return count < 2
        ? { id: "j", status: "running" }
        : { id: "j", status: "ready", payload: "done" };
    });

    const { result } = renderHook(
      () =>
        useJobPoll<Job, string>({
          job: { id: "j", status: "pending" },
          pollFn,
          ...jobExtractors,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.result).toBe("done"), { timeout: 2000 });
    expect(result.current.isPolling).toBe(false);
    expect(result.current.error).toBeNull();

    // Poll must stop once terminal — no runaway storm.
    const callsAtReady = pollFn.mock.calls.length;
    await new Promise((r) => setTimeout(r, 60));
    expect(pollFn.mock.calls.length).toBe(callsAtReady);
  });

  it("surfaces an error message on a failed job", async () => {
    const pollFn = vi.fn(
      async (): Promise<Job> => ({ id: "j", status: "failed", error_message: "boom" }),
    );
    const { result } = renderHook(
      () =>
        useJobPoll<Job, string>({
          job: { id: "j", status: "pending" },
          pollFn,
          ...jobExtractors,
          pollIntervalMs: 10,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.error).toBe("boom"), { timeout: 2000 });
    expect(result.current.result).toBeNull();
  });

  it("stops polling on a getError signal even when status is non-terminal (no spin)", async () => {
    // Envelope-shaped response whose job goes missing — getError flags it.
    type Envelope = { job: Job | null; result: string | null };
    const pollFn = vi.fn(async (): Promise<Envelope> => ({ job: null, result: null }));

    const { result } = renderHook(
      () =>
        useJobPoll<Envelope, string>({
          job: { id: "j", status: "pending" },
          pollFn,
          getStatus: (e) => e.job?.status,
          getResult: (e) => (e.job?.status === "ready" ? e.result : null),
          getError: (e) => (e.job ? null : "Job not found"),
          pollIntervalMs: 10,
        }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.error).toBe("Job not found"), { timeout: 2000 });
    const callsAfterError = pollFn.mock.calls.length;
    await new Promise((r) => setTimeout(r, 60));
    expect(pollFn.mock.calls.length).toBe(callsAfterError);
  });
});
