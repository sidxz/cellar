import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useCollectionSearch } from "./use-collection-search";

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

describe("useCollectionSearch", () => {
  it("posts to /api/v1/search/execute with a single collection criterion", async () => {
    mockInstance.mockResolvedValue({
      items: [{ id: "mol-1", structure: { smiles: "CCO" } }],
      next_cursor: null,
      total_count: 1,
      activity_data: {},
    });

    const { result } = renderHook(() => useCollectionSearch("col-123"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockInstance).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/search/execute",
        method: "POST",
        data: expect.objectContaining({
          query: expect.objectContaining({
            logic: "and",
            criteria: [{ type: "collection", collection_id: "col-123" }],
          }),
        }),
      }),
    );

    expect(result.current.data?.items).toHaveLength(1);
  });

  it("does not fire when collection_id is empty", () => {
    mockInstance.mockClear();
    renderHook(() => useCollectionSearch(""), { wrapper });
    expect(mockInstance).not.toHaveBeenCalled();
  });
});
