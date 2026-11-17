import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  customInstance: vi.fn(async ({ data }: { data: { labels: string[] } }) => ({
    matches: data.labels.map((label) => ({ label, compound: null })),
  })),
}));
vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", ...api }));

import { useResolvePositionLabels } from "./use-layout-file";

// The API reads at most 500 labels a request; a larger table is asked about in turns.
it("sends the labels to the run's route, 500 a request, and joins the answers in order", async () => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useResolvePositionLabels("run-1"), { wrapper });
  const labels = Array.from({ length: 501 }, (_, i) => `L${i}`);
  const answer = await act(() => result.current.mutateAsync({ labels }));
  expect(api.customInstance.mock.calls.map(([request]) => request)).toEqual([
    {
      url: "/api/v1/runs/run-1/resolve-position-labels",
      method: "POST",
      data: { labels: labels.slice(0, 500) },
    },
    {
      url: "/api/v1/runs/run-1/resolve-position-labels",
      method: "POST",
      data: { labels: ["L500"] },
    },
  ]);
  expect(answer.matches.map((m) => m.label)).toEqual(labels);
});
