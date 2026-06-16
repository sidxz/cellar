import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { channelFromColorSpec, useActivityProjection } from "./use-activity-projection";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const SPEC = {
  protocolId: "p1",
  column: "drc:rd1",
  interceptKey: { kind: "ic", level: 50 },
  source: "dr_curve",
  label: "EGFR · IC50",
} as const;

describe("channelFromColorSpec", () => {
  it("maps a SarColorSpec + aggregation mode to the channel request", () => {
    expect(channelFromColorSpec(SPEC, "gmean")).toEqual({
      column: "drc:rd1",
      source: "dr_curve",
      intercept_key: { kind: "ic", level: 50 },
      selection_rule: "geometric_mean",
      protocol_id: "p1",
      label: "EGFR · IC50",
    });
  });
});

describe("useActivityProjection", () => {
  it("polls a pending projection to ready", async () => {
    const startFn = vi
      .fn()
      .mockResolvedValue({ projection_id: "proj-1", status: "pending", value_count: 0 });
    const pollFn = vi
      .fn()
      .mockResolvedValue({ projection_id: "proj-1", status: "ready", value_count: 7 });
    const { result } = renderHook(
      () =>
        useActivityProjection({
          collectionId: "c1",
          channel: channelFromColorSpec(SPEC, "latest"),
          startFn,
          pollFn,
          pollIntervalMs: 5,
        }),
      { wrapper: wrap() },
    );
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.projectionId).toBe("proj-1");
  });

  it("is disabled with no channel", () => {
    const startFn = vi.fn();
    renderHook(
      () => useActivityProjection({ collectionId: "c1", channel: null, startFn, pollFn: vi.fn() }),
      {
        wrapper: wrap(),
      },
    );
    expect(startFn).not.toHaveBeenCalled();
  });
});
