import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(() => new Promise(() => {})),
}));

import { useDataset } from "./use-dataset";

describe("useDataset", () => {
  it("never refetches a loaded dataset in the background", () => {
    const client = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    renderHook(() => useDataset({ kind: "run", runId: "r1" }, "wells"), { wrapper });
    const [query] = client.getQueryCache().getAll();
    expect(query.options).toMatchObject({
      staleTime: Number.POSITIVE_INFINITY,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    });
  });
});
