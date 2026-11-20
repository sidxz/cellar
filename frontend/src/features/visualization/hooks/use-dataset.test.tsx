import {
  QueryClient,
  QueryClientProvider,
  focusManager,
  onlineManager,
} from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
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

  it("never refetches a loaded dataset in the background", async () => {
    const fetch = vi.mocked(customInstance);
    fetch.mockClear();
    fetch.mockResolvedValueOnce({ row_count: 0 });
    const wrapper = wrapperOf(new QueryClient());
    const load = () => useDataset({ kind: "run", runId: "r1" }, "wells");
    const { result } = renderHook(load, { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    try {
      // Back to the tab, back online, and a second view of the same dataset mounting.
      await act(async () => {
        focusManager.setFocused(false);
        focusManager.setFocused(true);
        onlineManager.setOnline(false);
        onlineManager.setOnline(true);
      });
      renderHook(load, { wrapper });
      await act(() => new Promise((r) => setTimeout(r, 0)));
      expect(fetch).toHaveBeenCalledTimes(1);
    } finally {
      focusManager.setFocused(undefined);
      onlineManager.setOnline(true);
    }
  });
});
