import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  customInstance: vi.fn().mockResolvedValue([{ id: "1", slug: "abbvie", name: "AbbVie" }]),
}));

import { useOrgs } from "./use-orgs";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useOrgs", () => {
  it("fetches the org directory", async () => {
    const { result } = renderHook(() => useOrgs(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([{ id: "1", slug: "abbvie", name: "AbbVie" }]);
  });
});
