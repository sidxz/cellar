import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type {
  CampaignChannelResponse,
  CampaignResponse,
  CampaignResultResponse,
  CampaignStageResponse,
  StageCountsResponse,
} from "../../types";
import { StagesSection } from "./stages-section";

vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocolSummaries: () => ({
    data: [{ id: "proto-1", name: "Kinase Panel" }],
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

function makeCounts(overrides: Partial<StageCountsResponse> = {}): StageCountsResponse {
  const c = {
    hit: 0,
    miss: 0,
    untested: 0,
    pending: 0,
    not_in_stage: 0,
    overridden: 0,
    ...overrides,
  };
  return { ...c, population: c.hit + c.miss + c.untested + c.pending };
}

function makeStage(overrides: Partial<CampaignStageResponse>): CampaignStageResponse {
  return {
    id: "stage-default",
    name: "Stage",
    parent_stage_id: null,
    display_order: 0,
    kind: "criteria",
    criteria: [],
    counts: makeCounts(),
    ...overrides,
  };
}

function makeResult(
  id: string,
  outcomes: Array<{ stage_id: string; outcome: string }>,
): CampaignResultResponse {
  return {
    id,
    molecule_id: `mol-${id}`,
    measurements: [],
    stage_outcomes: outcomes.map((o) => ({
      stage_id: o.stage_id,
      outcome: o.outcome,
      overridden: false,
      checks: [],
    })),
  };
}

// Screening Hits (root, 2/3 hit) -> Confirmed Hits (child, 1/2 hit, one
// gated out as not_in_stage) — mirrors the spec's worked funnel example at
// a size a test fixture can hand-check. Tile numbers come from the server's
// `counts`, deliberately NOT derivable from the `results` fixture below, so
// a regression back to client-side tallying fails these assertions.
const screeningStage = makeStage({
  id: "stage-screen",
  name: "Screening Hits",
  display_order: 0,
  criteria: [{ channel_id: "ch-1", operator: "gte", value: 50 }],
  counts: makeCounts({ hit: 2, miss: 1, untested: 1 }),
});
const confirmedStage = makeStage({
  id: "stage-confirmed",
  name: "Confirmed Hits",
  parent_stage_id: "stage-screen",
  display_order: 1,
  criteria: [],
  counts: makeCounts({ hit: 1, miss: 1, not_in_stage: 1 }),
});
// Hand-picked follow-up: one promoted, two still awaiting triage.
const manualStage = makeStage({
  id: "stage-manual",
  name: "Take Forward",
  display_order: 2,
  kind: "manual",
  criteria: [],
  counts: makeCounts({ hit: 1, pending: 2 }),
});

const manualCampaign = {
  id: "c2",
  channels: [],
  stages: [manualStage],
  results: [],
} as unknown as CampaignResponse;

const campaign = {
  id: "c1",
  channels: [makeChannel({ id: "ch-1", label: "% Inhibition", protocol_id: "proto-1" })],
  stages: [screeningStage, confirmedStage],
  results: [
    makeResult("r1", [
      { stage_id: "stage-screen", outcome: "hit" },
      { stage_id: "stage-confirmed", outcome: "hit" },
    ]),
    makeResult("r2", [
      { stage_id: "stage-screen", outcome: "hit" },
      { stage_id: "stage-confirmed", outcome: "miss" },
    ]),
    makeResult("r3", [
      { stage_id: "stage-screen", outcome: "miss" },
      { stage_id: "stage-confirmed", outcome: "not_in_stage" },
    ]),
  ],
} as unknown as CampaignResponse;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("StagesSection", () => {
  it("renders tile numbers from the server's counts, not a client-side tally of the rows", () => {
    render(
      <StagesSection
        campaign={campaign}
        selectedStageId={null}
        onSelectStage={vi.fn()}
        readOnly={false}
      />,
      { wrapper },
    );

    expect(screen.getByRole("button", { name: /^All 3$/ })).toBeInTheDocument();
    // counts say hit 2 of population 4; tallying the three rows below would
    // have said "2 of 3". Criteria are summarized on the tile itself.
    expect(
      screen.getByRole("button", { name: /^Screening Hits 2 of 4 50% % Inhibition >= 50$/ }),
    ).toBeInTheDocument();
    // Child population is its parent's hits (r3 is gated out as not_in_stage).
    expect(
      screen.getByRole("button", { name: /^↳ after Screening Hits Confirmed Hits 1 of 2 50%$/ }),
    ).toBeInTheDocument();
  });

  it("shows the parent subline on a child stage's tab", () => {
    render(
      <StagesSection
        campaign={campaign}
        selectedStageId={null}
        onSelectStage={vi.fn()}
        readOnly={false}
      />,
      { wrapper },
    );

    expect(screen.getByText(/↳ after Screening Hits/)).toBeInTheDocument();
    // The root stage's tab carries no subline.
    expect(screen.getByRole("button", { name: /^Screening Hits 2 of 4/ })).not.toHaveTextContent(
      "↳",
    );
  });

  it("calls onSelectStage with the clicked stage's id, and null for All", () => {
    const onSelectStage = vi.fn();
    render(
      <StagesSection
        campaign={campaign}
        selectedStageId="stage-screen"
        onSelectStage={onSelectStage}
        readOnly={false}
      />,
      { wrapper },
    );

    fireEvent.click(screen.getByRole("button", { name: /Confirmed Hits 1 of 2/ }));
    expect(onSelectStage).toHaveBeenCalledWith("stage-confirmed");

    fireEvent.click(screen.getByRole("button", { name: /^All 3$/ }));
    expect(onSelectStage).toHaveBeenCalledWith(null);
  });

  it("shows nothing below the tabs for All, and the selected stage's criteria/parent otherwise", () => {
    const { rerender } = render(
      <StagesSection
        campaign={campaign}
        selectedStageId={null}
        onSelectStage={vi.fn()}
        readOnly={false}
      />,
      { wrapper },
    );
    expect(screen.queryByText(/passes its whole population/)).not.toBeInTheDocument();

    rerender(
      <StagesSection
        campaign={campaign}
        selectedStageId="stage-confirmed"
        onSelectStage={vi.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByText(/No criteria yet/)).toBeInTheDocument();
    expect(screen.getByText("after Screening Hits")).toBeInTheDocument();

    rerender(
      <StagesSection
        campaign={campaign}
        selectedStageId="stage-screen"
        onSelectStage={vi.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByText("root")).toBeInTheDocument();
    expect(screen.getByText("% Inhibition")).toBeInTheDocument();
    expect(screen.getByText(">= 50")).toBeInTheDocument();
  });

  it("marks a manual stage with a manual eyebrow and counts its pending rows in the population", () => {
    render(
      <StagesSection
        campaign={manualCampaign}
        selectedStageId={null}
        onSelectStage={vi.fn()}
        readOnly={false}
      />,
      { wrapper },
    );

    // hit 1, pending 2 -> "1 of 3", with the kind called out above the name.
    expect(
      screen.getByRole("button", { name: /^manual Take Forward 1 of 3 33%$/ }),
    ).toBeInTheDocument();
  });

  it("explains a selected manual stage instead of showing 'No criteria yet'", () => {
    render(
      <StagesSection
        campaign={manualCampaign}
        selectedStageId="stage-manual"
        onSelectStage={vi.fn()}
        readOnly={false}
      />,
      { wrapper },
    );

    expect(screen.getByText(/compounds start pending/)).toBeInTheDocument();
    expect(screen.queryByText(/No criteria yet/)).not.toBeInTheDocument();
  });

  it("hides add/edit affordances when read-only", () => {
    render(
      <StagesSection
        campaign={campaign}
        selectedStageId="stage-screen"
        onSelectStage={vi.fn()}
        readOnly={true}
      />,
      { wrapper },
    );
    expect(screen.queryByRole("button", { name: "Stage" })).not.toBeInTheDocument();
  });
});
