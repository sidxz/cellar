import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CampaignSummaryResponse } from "@/shared/lib/api/model";
import { CampaignList } from "./campaign-list";

// The list is summary-driven: items carry `result_count`, not result rows.
// Stubbing the transport (rather than the hook) keeps the list → useCampaigns
// → query-param wiring under test.
const customInstance = vi.fn(async (args: { url: string }): Promise<unknown> => {
  if (args.url.endsWith("/campaigns")) return { items: campaigns, next_cursor: null };
  // Everything else the filter pills fetch (tags, targets, the project) —
  // an empty list keeps them rendered but inert.
  return [];
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/projects/p1/campaigns",
}));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: { url: string }) => customInstance(args),
}));

const campaigns = [
  {
    id: "c1",
    name: "Kinase triage",
    status: "draft",
    result_count: 42,
    channels: [{ id: "ch-1" }, { id: "ch-2" }],
    stages: [],
    targets: [],
    created_at: "2026-08-01T00:00:00Z",
    closed_at: null,
  },
] as unknown as CampaignSummaryResponse[];

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function paramsOfLastListCall() {
  const calls = customInstance.mock.calls.filter(([a]) => a.url.endsWith("/campaigns"));
  return (calls.at(-1)?.[0] as { params?: Record<string, unknown> }).params;
}

describe("CampaignList", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the server's result_count, not a row tally", async () => {
    render(<CampaignList projectId="p1" />, { wrapper });

    const row = await screen.findByTestId("campaign-row-c1");
    expect(within(row).getByText("42")).toBeInTheDocument();
    // Readouts column still counts the channels the payload carries.
    expect(within(row).getByText("2")).toBeInTheDocument();
  });

  it("sends no status by default and the picked one after filtering", async () => {
    render(<CampaignList projectId="p1" />, { wrapper });

    await waitFor(() => expect(paramsOfLastListCall()).toBeDefined());
    expect(paramsOfLastListCall()).toEqual({ project_id: "p1" });

    // Radix Tabs switch on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Closed" }), { button: 0 });

    await waitFor(() => expect(paramsOfLastListCall()?.status).toBe("closed"));
  });
});
