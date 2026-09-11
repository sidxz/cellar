import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { CampaignChannelResponse, CampaignResponse } from "../../types";
import { ChannelsSection } from "./channels-section";

vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocolSummaries: () => ({
    data: [
      { id: "proto-1", name: "Kinase Panel" },
      { id: "proto-2", name: "Resazurin Viability" },
    ],
  }),
  useProtocol: () => ({ data: undefined }),
}));

function makeChannel(overrides: Partial<CampaignChannelResponse>): CampaignChannelResponse {
  return {
    id: "ch-default",
    label: "Readout",
    protocol_id: "proto-1",
    readout_definition_id: "rd-1",
    source_kind: "readout_data",
    selection_rule: "latest_approved_run",
    qualifier_handling: "include_qualified",
    display_order: 0,
    ...overrides,
  };
}

const campaign = {
  id: "c1",
  channels: [
    makeChannel({
      id: "ch-1",
      label: "IC50",
      protocol_id: "proto-1",
      source_kind: "dose_response_curve",
      selection_rule: "latest_approved_run",
      display_order: 0,
    }),
    makeChannel({
      id: "ch-2",
      label: "% Viability",
      protocol_id: "proto-2",
      selection_rule: "mean_across_runs",
      display_order: 1,
    }),
  ],
} as unknown as CampaignResponse;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("ChannelsSection", () => {
  it("groups readouts under a heading per protocol, with no threshold text", () => {
    render(<ChannelsSection campaign={campaign} projectId="p1" readOnly />, { wrapper });

    expect(screen.getByText("Kinase Panel")).toBeInTheDocument();
    expect(screen.getByText("Resazurin Viability")).toBeInTheDocument();
    expect(screen.getByText("IC50")).toBeInTheDocument();
    expect(screen.getByText("% Viability")).toBeInTheDocument();
    expect(screen.queryByText(/hit if/i)).not.toBeInTheDocument();
  });
});
