import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCampaigns } from "./use-campaigns";

const customInstance = vi.fn(async (_args: unknown) => ({ items: [], next_cursor: null }));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));
vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  getCampaignApiV1CampaignsCampaignIdGet: vi.fn(),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useCampaigns target params", () => {
  beforeEach(() => vi.clearAllMocks());

  it("forwards targets + target_logic", async () => {
    renderHook(() => useCampaigns("p1", { targets: ["t1", "t2"], targetLogic: "all" }), {
      wrapper,
    });
    await waitFor(() => expect(customInstance).toHaveBeenCalled());
    const arg = customInstance.mock.calls[0][0] as { params?: Record<string, unknown> };
    expect(arg.params?.targets).toEqual(["t1", "t2"]);
    expect(arg.params?.target_logic).toBe("all");
  });
});
