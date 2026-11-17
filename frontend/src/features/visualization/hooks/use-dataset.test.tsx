import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(() => new Promise(() => {})),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useDataset } from "./use-dataset";

const wrapperOf =
  (client: QueryClient) =>
  ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

describe("useDataset", () => {
  it("posts the compared protocols with the source", () => {
    renderHook(
      () =>
        useDataset(
          { kind: "protocol", protocolId: "A", compare: [{ protocolId: "B", runIds: ["r1"] }] },
          "compounds",
        ),
      { wrapper: wrapperOf(new QueryClient()) },
    );
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith(
      expect.objectContaining({
        data: {
          level: "compounds",
          source: {
            kind: "protocol",
            protocol_id: "A",
            run_ids: null,
            compare: [{ protocol_id: "B", run_ids: ["r1"] }],
          },
        },
      }),
    );
  });

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
