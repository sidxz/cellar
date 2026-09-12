import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CampaignResponse, CampaignStageResponse } from "../types";
import { StagePopoverForm } from "./stage-popover";

const { addMutate, updateMutate } = vi.hoisted(() => ({
  addMutate: vi.fn(),
  updateMutate: vi.fn(),
}));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useAddCampaignStageApiV1CampaignsCampaignIdStagesPost: () => ({
    mutate: addMutate,
    isPending: false,
  }),
  useUpdateCampaignStageApiV1CampaignsCampaignIdStagesStageIdPatch: () => ({
    mutate: updateMutate,
    isPending: false,
  }),
  useRemoveCampaignStageApiV1CampaignsCampaignIdStagesStageIdDelete: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocolSummaries: () => ({ data: [{ id: "proto-1", name: "Kinase Panel" }] }),
}));

vi.mock("../hooks/use-campaigns", () => ({
  campaignKeys: { detail: (id: string) => ["campaigns", "detail", id] },
}));

// An existing criteria stage, so the edit path has a criterion the manual
// switch has to discard rather than ship alongside kind: "manual".
const existing = {
  id: "stage-screen",
  name: "Screening Hits",
  parent_stage_id: null,
  display_order: 0,
  kind: "criteria",
  criteria: [{ channel_id: "ch-1", operator: "gte", value: 50 }],
  counts: {
    population: 3,
    hit: 2,
    miss: 1,
    untested: 0,
    pending: 0,
    not_in_stage: 0,
    overridden: 0,
  },
} as unknown as CampaignStageResponse;

const campaign = {
  id: "c1",
  channels: [
    {
      id: "ch-1",
      label: "% Inhibition",
      protocol_id: "proto-1",
      display_order: 0,
    },
  ],
  stages: [existing],
  results: [],
} as unknown as CampaignResponse;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  addMutate.mockClear();
  updateMutate.mockClear();
});

describe("StagePopoverForm — stage kind", () => {
  it("adds a manual stage with an empty criteria list", async () => {
    render(<StagePopoverForm campaignId="c1" campaign={campaign} onClose={vi.fn()} />, { wrapper });

    fireEvent.change(screen.getByPlaceholderText(/Screening Hits/), {
      target: { value: "Take Forward" },
    });
    fireEvent.click(screen.getByRole("radio", { name: "manual" }));

    // The criteria editor is replaced by the hand-picked explanation.
    expect(screen.getByText(/compounds start pending/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Criterion/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(addMutate).toHaveBeenCalledTimes(1));
    expect(addMutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: { name: "Take Forward", parent_stage_id: null, kind: "manual", criteria: [] },
    });
  });

  // The backend 422s on manual + criteria, so flipping an existing criteria
  // stage to manual must drop the rows it already had, not send both.
  it("drops an existing stage's criteria when it is switched to manual", async () => {
    render(
      <StagePopoverForm
        campaignId="c1"
        campaign={campaign}
        existing={existing}
        onClose={vi.fn()}
      />,
      { wrapper },
    );

    fireEvent.click(screen.getByRole("radio", { name: "manual" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate).toHaveBeenCalledWith({
      campaignId: "c1",
      stageId: "stage-screen",
      data: {
        name: "Screening Hits",
        parent_stage_id: null,
        kind: "manual",
        criteria: [],
      },
    });
  });

  it("keeps sending kind: criteria (with its rows) for an unchanged stage", async () => {
    render(
      <StagePopoverForm
        campaignId="c1"
        campaign={campaign}
        existing={existing}
        onClose={vi.fn()}
      />,
      { wrapper },
    );

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          kind: "criteria",
          criteria: [{ channel_id: "ch-1", operator: "gte", value: 50 }],
        }),
      }),
    );
  });
});
