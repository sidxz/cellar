import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSarActivity } from "./use-sar-activity";

const mockMutateAsync = vi.fn();
vi.mock("@/features/research-organization/hooks/use-search", () => ({
  useExecuteSearch: () => ({ mutateAsync: mockMutateAsync, isPending: false }),
}));

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const colorSpec = {
  column: "drc:rd1",
  source: "dr_curve" as const,
  interceptKey: null,
  protocolId: "p1",
  label: "x",
};

describe("useSarActivity", () => {
  beforeEach(() => {
    mockMutateAsync.mockReset();
    mockMutateAsync.mockResolvedValue({
      activity_data: { m1: { "drc:rd1": { value: 12 } } },
    });
  });

  it("calls mutateAsync with keyword_list uuid criterion + protocol_columns + aggregation", async () => {
    const { result } = renderHook(
      () =>
        useSarActivity({
          moleculeIds: ["m1"],
          colorSpec,
          aggregationMode: "latest",
        }),
      { wrapper: makeWrapper() },
    );

    await waitFor(() => expect(result.current.activityByMolecule.m1?.value).toBe(12));

    expect(mockMutateAsync).toHaveBeenCalledTimes(1);
    const callArgs = mockMutateAsync.mock.calls[0][0];
    expect(callArgs.input.query.criteria[0]).toMatchObject({
      type: "keyword_list",
      values: ["m1"],
      ref_type: "uuid",
    });
    expect(callArgs.input.protocol_columns).toEqual(["drc:rd1"]);
    expect(callArgs.input.aggregation).toBe("latest_approved_run");
  });

  it("returns empty when colorSpec is null", () => {
    const { result } = renderHook(
      () =>
        useSarActivity({
          moleculeIds: ["m1"],
          colorSpec: null,
          aggregationMode: "latest",
        }),
      { wrapper: makeWrapper() },
    );

    expect(result.current.activityByMolecule).toEqual({});
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it("returns empty when moleculeIds is empty", () => {
    const { result } = renderHook(
      () =>
        useSarActivity({
          moleculeIds: [],
          colorSpec,
          aggregationMode: "latest",
        }),
      { wrapper: makeWrapper() },
    );

    expect(result.current.activityByMolecule).toEqual({});
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it("returns empty when mutateAsync rejects", async () => {
    mockMutateAsync.mockRejectedValue(new Error("network error"));
    const { result } = renderHook(
      () =>
        useSarActivity({
          moleculeIds: ["m1"],
          colorSpec,
          aggregationMode: "latest",
        }),
      { wrapper: makeWrapper() },
    );

    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(result.current.activityByMolecule).toEqual({});
  });
});
