import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useProtocolTestCounts } from "./use-protocol-test-counts";

const mockInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", () => ({
  customInstance: (cfg: unknown) => mockInstance(cfg),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useProtocolTestCounts", () => {
  it("posts to /api/v1/molecules/test-counts and returns counts", async () => {
    mockInstance.mockResolvedValue({ counts: { "mol-1": 2 } });

    const { result } = renderHook(() => useProtocolTestCounts(["mol-1"], null), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockInstance).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/molecules/test-counts",
        method: "POST",
        data: expect.objectContaining({
          molecule_ids: ["mol-1"],
          project_id: null,
        }),
      }),
    );

    expect(result.current.data?.["mol-1"]).toBe(2);
  });

  it("does not fire when moleculeIds is empty", () => {
    mockInstance.mockClear();
    renderHook(() => useProtocolTestCounts([], null), { wrapper });
    expect(mockInstance).not.toHaveBeenCalled();
  });

  it("includes project_id when provided", async () => {
    mockInstance.mockResolvedValue({ counts: { "mol-2": 1 } });

    const { result } = renderHook(() => useProtocolTestCounts(["mol-2"], "proj-xyz"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockInstance).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ project_id: "proj-xyz" }),
      }),
    );
  });
});
