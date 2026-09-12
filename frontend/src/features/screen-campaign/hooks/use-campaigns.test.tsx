import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { campaignKeys, useCampaignSummary, useCampaigns } from "./use-campaigns";

const customInstance = vi.fn(async (_args: unknown) => ({ items: [], next_cursor: null }));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));
const getSummary = vi.fn(async () => ({ id: "c1", result_count: 7 }));
vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  getCampaignApiV1CampaignsCampaignIdGet: vi.fn(),
  getCampaignSummaryApiV1CampaignsCampaignIdSummaryGet: () => getSummary(),
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

describe("useCampaigns status param", () => {
  beforeEach(() => vi.clearAllMocks());

  it("omits status unless asked", async () => {
    renderHook(() => useCampaigns("p1"), { wrapper });
    await waitFor(() => expect(customInstance).toHaveBeenCalled());
    const arg = customInstance.mock.calls[0][0] as { params?: Record<string, unknown> };
    expect(arg.params).toEqual({ project_id: "p1" });
  });

  it("forwards status", async () => {
    renderHook(() => useCampaigns("p1", { status: "superseded" }), { wrapper });
    await waitFor(() => expect(customInstance).toHaveBeenCalled());
    const arg = customInstance.mock.calls[0][0] as { params?: Record<string, unknown> };
    expect(arg.params?.status).toBe("superseded");
  });
});

describe("useCampaignSummary", () => {
  beforeEach(() => vi.clearAllMocks());

  it("caches the summary under its own key, not the detail key", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useCampaignSummary("c1"), {
      wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>,
    });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(qc.getQueryData(campaignKeys.summary("c1"))).toEqual({ id: "c1", result_count: 7 });
    expect(qc.getQueryData(campaignKeys.detail("c1"))).toBeUndefined();
  });
});
