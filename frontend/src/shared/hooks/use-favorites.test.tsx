import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { favoritesKey, useFavorites, useToggleFavorite } from "./use-favorites";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(async () => [
    { entity_type: "project", entity_id: "p1", created_at: "2026-06-07T00:00:00Z" },
    { entity_type: "project", entity_id: "p2", created_at: "2026-06-07T00:00:00Z" },
  ]),
}));

const customInstanceMock = vi.mocked(customInstance);

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

/** Wrapper bound to a caller-supplied client so a test can seed/inspect the cache. */
function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useFavorites", () => {
  beforeEach(() => vi.clearAllMocks());

  it("maps the favorites list into a Set of entity ids", async () => {
    const { result } = renderHook(() => useFavorites("project"), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.has("p1")).toBe(true);
    expect(result.current.data?.has("p2")).toBe(true);
    expect(result.current.data?.size).toBe(2);
  });
});

describe("useToggleFavorite", () => {
  beforeEach(() => vi.clearAllMocks());

  it("optimistically adds an id to a seeded cache before settlement", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(favoritesKey("project"), new Set(["p1"]));
    // Never resolve, so onSettled invalidation can't refetch and overwrite the optimistic state.
    customInstanceMock.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useToggleFavorite("project"), {
      wrapper: makeWrapper(qc),
    });

    result.current.mutate({ entityId: "p2", favorited: false });

    await waitFor(() => {
      const set = qc.getQueryData<Set<string>>(favoritesKey("project"));
      expect(set?.has("p2")).toBe(true);
    });
    expect(qc.getQueryData<Set<string>>(favoritesKey("project"))?.has("p1")).toBe(true);
  });

  it("optimistically removes an id from a seeded cache before settlement", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(favoritesKey("project"), new Set(["p1", "p2"]));
    customInstanceMock.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useToggleFavorite("project"), {
      wrapper: makeWrapper(qc),
    });

    result.current.mutate({ entityId: "p1", favorited: true });

    await waitFor(() => {
      const set = qc.getQueryData<Set<string>>(favoritesKey("project"));
      expect(set?.has("p1")).toBe(false);
    });
    expect(qc.getQueryData<Set<string>>(favoritesKey("project"))?.has("p2")).toBe(true);
  });

  it("rolls back to undefined on error when the cache started empty", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    // No seed: cache for the key is undefined at onMutate time.
    expect(qc.getQueryData(favoritesKey("project"))).toBeUndefined();
    customInstanceMock.mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useToggleFavorite("project"), {
      wrapper: makeWrapper(qc),
    });

    result.current.mutate({ entityId: "px", favorited: false });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData(favoritesKey("project"))).toBeUndefined();
  });
});
