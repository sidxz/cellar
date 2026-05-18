import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  useCollectionScaffoldSearch,
  scaffoldSearchQueryKey,
} from "./use-collection-scaffold-search";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  customInstance: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";

const mockCustomInstance = customInstance as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useCollectionScaffoldSearch", () => {
  beforeEach(() => {
    mockCustomInstance.mockReset();
    mockCustomInstance.mockResolvedValue({ items: [] });
  });

  it("posts an AND'd group with collection + exact_match_in scaffold criterion", async () => {
    const { result } = renderHook(
      () =>
        useCollectionScaffoldSearch({
          collectionId: "col-1",
          scaffoldSmiles: ["c1ccccc1", "c1ccncc1"],
        }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockCustomInstance).toHaveBeenCalledTimes(1);
    const call = mockCustomInstance.mock.calls[0][0];
    expect(call.url).toBe("/api/v1/search/execute");
    expect(call.method).toBe("POST");
    expect(call.data.query.criteria[0]).toMatchObject({
      type: "group",
      logic: "and",
      criteria: [
        { type: "collection", collection_id: "col-1" },
        {
          type: "scaffold",
          mode: "exact_match_in",
          scaffold_smiles_list: expect.arrayContaining(["c1ccccc1", "c1ccncc1"]),
        },
      ],
    });
  });

  it("disabled when enabled === false", () => {
    const { result } = renderHook(
      () =>
        useCollectionScaffoldSearch({
          collectionId: "col-1",
          scaffoldSmiles: ["c1ccccc1"],
          enabled: false,
        }),
      { wrapper: makeWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockCustomInstance).not.toHaveBeenCalled();
  });

  it("disabled when scaffoldSmiles is empty", () => {
    renderHook(
      () =>
        useCollectionScaffoldSearch({
          collectionId: "col-1",
          scaffoldSmiles: [],
        }),
      { wrapper: makeWrapper() },
    );
    expect(mockCustomInstance).not.toHaveBeenCalled();
  });

  it("query key is stable across scaffold input order", () => {
    expect(scaffoldSearchQueryKey("col-1", ["b", "a", "c"])).toEqual(
      scaffoldSearchQueryKey("col-1", ["c", "a", "b"]),
    );
    expect(scaffoldSearchQueryKey("col-1", ["a"])).not.toEqual(
      scaffoldSearchQueryKey("col-1", ["b"]),
    );
  });
});
