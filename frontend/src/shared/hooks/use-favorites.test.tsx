import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useFavorites } from "./use-favorites";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(async () => [
    { entity_type: "project", entity_id: "p1", created_at: "2026-06-07T00:00:00Z" },
    { entity_type: "project", entity_id: "p2", created_at: "2026-06-07T00:00:00Z" },
  ]),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
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
