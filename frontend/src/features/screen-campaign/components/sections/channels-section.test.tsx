import type { ColumnDescriptionResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { CampaignChannelResponse, CampaignResponse } from "../../types";
import { ChannelsSection } from "./channels-section";

const { mutateAsync, mirrorMutate, setConcentration } = vi.hoisted(() => ({
  mutateAsync: vi.fn(async () => ({})),
  mirrorMutate: vi.fn(),
  setConcentration: vi.fn(),
}));
vi.mock("../../hooks/use-campaigns", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useSetColumnConcentration: () => ({ mutate: setConcentration, isPending: false }),
}));
vi.mock("@/shared/lib/api/campaigns/campaigns", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch: () => ({
    mutateAsync,
    isPending: false,
  }),
  useMirrorProtocolChannelsApiV1CampaignsCampaignIdChannelsMirrorProtocolPost: () => ({
    mutate: mirrorMutate,
    isPending: false,
  }),
}));

vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocolSummaries: () => ({
    data: [
      { id: "proto-1", name: "Kinase Panel" },
      { id: "proto-2", name: "Resazurin Viability" },
    ],
  }),
  // Every protocol here recommends criteria, so the mirror popover offers
  // its "also create a stage" block.
  useProtocol: () => ({
    data: { recommended_hit_criteria: [{ readout_definition_id: "rd-1", operator: "lt" }] },
  }),
}));

// Radix Select portals a listbox whose items call scrollIntoView +
// hasPointerCapture — jsdom ships neither.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

function makeChannel(overrides: Partial<CampaignChannelResponse>): CampaignChannelResponse {
  return {
    id: "ch-default",
    label: "Readout",
    protocol_id: "proto-1",
    readout_definition_id: "rd-1",
    source_kind: "readout_data",
    selection_rule: "latest_run",
    qualifier_handling: "include_qualified",
    display_order: 0,
    ...overrides,
  };
}

const campaign = {
  id: "c1",
  stages: [],
  channels: [
    makeChannel({
      id: "ch-1",
      label: "IC50",
      protocol_id: "proto-1",
      source_kind: "dose_response_curve",
      selection_rule: "latest_run",
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

  it("renders chips: DR mark on curve readouts, rule only when non-default", () => {
    render(<ChannelsSection campaign={campaign} projectId="p1" readOnly />, { wrapper });

    const ic50 = screen.getByText("IC50").closest("[title]");
    expect(ic50).toHaveTextContent("DR");
    expect(ic50).toHaveAttribute("title", "Dose-response curve · latest run");
    expect(screen.queryByText("latest run")).not.toBeInTheDocument();

    const viability = screen.getByText("% Viability").closest("[title]");
    expect(viability).toHaveTextContent("mean across runs");
    expect(viability).not.toHaveTextContent("DR");
  });

  it("marks only the readouts that resolve from all runs of their protocol", () => {
    const mixed = {
      id: "c1",
      stages: [],
      channels: [
        makeChannel({ id: "ch-1", label: "IC50", display_order: 0 }),
        makeChannel({
          id: "ch-2",
          label: "Counter-screen",
          display_order: 1,
          resolve_from_all_runs: true,
        }),
      ],
    } as unknown as CampaignResponse;
    render(<ChannelsSection campaign={mixed} projectId="p1" readOnly />, { wrapper });

    expect(screen.getByText("IC50").closest("li")).not.toHaveTextContent("all runs");
    const marker = screen.getByText("all runs");
    expect(screen.getByText("Counter-screen").closest("li")).toContainElement(marker);
    expect(marker).toHaveAttribute(
      "title",
      "Reads every run of the protocol, not only the runs added to its stage or campaign.",
    );
  });

  it("chips are edit buttons in draft mode and inert in read-only mode", () => {
    const { unmount } = render(
      <ChannelsSection campaign={campaign} projectId="p1" readOnly={false} />,
      { wrapper },
    );
    expect(screen.getByRole("button", { name: /^IC50/ })).toBeInTheDocument();
    unmount();

    render(<ChannelsSection campaign={campaign} projectId="p1" readOnly />, { wrapper });
    expect(screen.queryByRole("button", { name: /^IC50/ })).not.toBeInTheDocument();
  });
});

// ── Reorder ──────────────────────────────────────────────────────────────────

/** Two readouts on one protocol, so a row has a neighbour to swap with. */
const twoOnOneProtocol = {
  id: "c1",
  stages: [],
  channels: [
    makeChannel({ id: "ch-a", label: "IC50", protocol_id: "proto-1", display_order: 0 }),
    makeChannel({ id: "ch-b", label: "IC90", protocol_id: "proto-1", display_order: 3 }),
  ],
} as unknown as CampaignResponse;

describe("ChannelsSection reorder", () => {
  beforeEach(() => mutateAsync.mockClear());

  it("swaps display_order with the neighbour, one PATCH at a time", async () => {
    render(<ChannelsSection campaign={twoOnOneProtocol} projectId="p1" readOnly={false} />, {
      wrapper,
    });

    fireEvent.click(screen.getByRole("button", { name: "Move IC50 later" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(mutateAsync).toHaveBeenNthCalledWith(1, {
      campaignId: "c1",
      channelId: "ch-a",
      data: { display_order: 3 },
    });
    expect(mutateAsync).toHaveBeenNthCalledWith(2, {
      campaignId: "c1",
      channelId: "ch-b",
      data: { display_order: 0 },
    });
  });

  it("disables the arrows at the ends of the row", () => {
    render(<ChannelsSection campaign={twoOnOneProtocol} projectId="p1" readOnly={false} />, {
      wrapper,
    });

    expect(screen.getByRole("button", { name: "Move IC50 earlier" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move IC50 later" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Move IC90 earlier" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Move IC90 later" })).toBeDisabled();
  });

  it("shows no arrows in read-only mode", () => {
    render(<ChannelsSection campaign={twoOnOneProtocol} projectId="p1" readOnly />, { wrapper });

    expect(screen.queryByRole("button", { name: /^Move / })).not.toBeInTheDocument();
  });
});

// ── Mirror protocol ──────────────────────────────────────────────────────────

const withStage = {
  id: "c1",
  stages: [{ id: "st-1", name: "Primary", display_order: 0, kind: "criteria" }],
  // One channel, so the empty state's own "Mirror protocol" link stays away
  // and the pill is the only trigger.
  channels: [makeChannel({ id: "ch-a", label: "IC50" })],
} as unknown as CampaignResponse;

/** Open the <Select> with this accessible name and click the matching option. */
function pick(name: string, optionText: string | RegExp) {
  fireEvent.click(screen.getByRole("combobox", { name }));
  fireEvent.click(within(screen.getByRole("listbox")).getByText(optionText));
}

describe("MirrorProtocolPopover", () => {
  beforeEach(() => mirrorMutate.mockClear());

  function openAndPickProtocol() {
    fireEvent.click(screen.getByRole("button", { name: /Mirror protocol/ }));
    pick("Protocol", "Kinase Panel");
  }

  it("needs a stage once the campaign has stages, and sends the picked one", () => {
    render(<ChannelsSection campaign={withStage} projectId="p1" readOnly={false} />, { wrapper });

    openAndPickProtocol();
    expect(screen.getByRole("button", { name: "Mirror" })).toBeDisabled();
    pick("Stage", "Primary");
    fireEvent.click(screen.getByRole("button", { name: "Mirror" }));

    expect(mirrorMutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: { protocol_id: "proto-1", stage_id: "st-1", stage_name: null, parent_stage_id: null },
    });
  });

  it("sends a new stage's name and its picked parent", async () => {
    render(<ChannelsSection campaign={withStage} projectId="p1" readOnly={false} />, { wrapper });

    openAndPickProtocol();
    pick("Stage", "New stage…");
    await screen.findByLabelText("Parent stage");
    pick("Parent stage", "Primary");
    fireEvent.click(screen.getByRole("button", { name: "Mirror" }));

    expect(mirrorMutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: {
        protocol_id: "proto-1",
        stage_id: null,
        stage_name: "Kinase Panel hits",
        parent_stage_id: "st-1",
      },
    });
  });

  it("starts a first stage when the campaign has none, at the root", () => {
    const noStages = { ...withStage, stages: [] } as unknown as CampaignResponse;
    render(<ChannelsSection campaign={noStages} projectId="p1" readOnly={false} />, { wrapper });

    openAndPickProtocol();
    fireEvent.click(screen.getByRole("button", { name: "Mirror" }));

    expect(mirrorMutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: {
        protocol_id: "proto-1",
        stage_id: null,
        stage_name: "Kinase Panel hits",
        parent_stage_id: null,
      },
    });
  });

  it("reuses a colliding criteria stage — advisory, Mirror still enabled", () => {
    render(<ChannelsSection campaign={withStage} projectId="p1" readOnly={false} />, { wrapper });

    openAndPickProtocol();
    pick("Stage", "New stage…");
    fireEvent.change(screen.getByPlaceholderText("e.g. Screening Hits"), {
      target: { value: "primary" },
    });

    expect(
      screen.getByText('Reuses stage "Primary": its criteria will be replaced.'),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mirror" })).toBeEnabled();
  });

  it("blocks a name that belongs to a manual stage", () => {
    const manual = {
      ...withStage,
      stages: [{ id: "st-m", name: "Confirmed", display_order: 0, kind: "manual" }],
    } as unknown as CampaignResponse;
    render(<ChannelsSection campaign={manual} projectId="p1" readOnly={false} />, { wrapper });

    openAndPickProtocol();
    pick("Stage", "New stage…");
    fireEvent.change(screen.getByPlaceholderText("e.g. Screening Hits"), {
      target: { value: "Confirmed" },
    });

    expect(screen.getByText("Confirmed is a manual stage; pick another name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mirror" })).toBeDisabled();
  });
});

// ── Stage groups + concentration choice ──────────────────────────────────────

const description: ColumnDescriptionResponse = {
  readout_label: "% Inhibition",
  design: "single_concentration_mixed",
  concentrations: [
    { value: 10, unit: "µM", count: 40 },
    { value: 1, unit: "µM", count: 12 },
    { value: null, unit: null, count: 3 },
  ],
  replicates: { min: 1, max: 1, not_recorded: 0 },
  run_count: 2,
  rule: "latest run",
  basis: ["reported"],
  needs_concentration: true,
  label: "Primary · % Inhibition · several concentrations",
  short_label: "several concentrations",
  stage_name: "Primary",
};

const staged = {
  id: "c1",
  stages: [{ id: "st-1", name: "Primary", display_order: 0, kind: "criteria" }],
  channels: [
    makeChannel({ id: "ch-mixed", label: "% Inhibition", stage_id: "st-1", description }),
    makeChannel({
      id: "ch-plain",
      label: "IC50",
      stage_id: "st-1",
      display_order: 1,
      description: { ...description, needs_concentration: false },
    }),
    makeChannel({
      id: "ch-chosen",
      label: "Counter",
      display_order: 2,
      test_concentration: { value: 10, unit: "µM" },
      description: { ...description, readout_label: "Counter", needs_concentration: false },
    }),
  ],
} as unknown as CampaignResponse;

describe("ChannelsSection stages and concentrations", () => {
  beforeEach(() => setConcentration.mockClear());

  it("heads readouts by their stage, campaign columns last under Other columns", () => {
    render(<ChannelsSection campaign={staged} projectId="p1" readOnly />, { wrapper });
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Primary", "Other columns"]);
  });

  it("offers each found concentration only on a column that needs one", () => {
    render(<ChannelsSection campaign={staged} projectId="p1" readOnly={false} />, { wrapper });

    const choices = screen.getAllByRole("button", { name: /^Use values at/ });
    expect(choices.map((b) => b.textContent)).toEqual([
      "Use values at 10 µM",
      "Use values at 1 µM",
    ]);
    expect(screen.getByText("40 compounds")).toBeInTheDocument();
    // The not-recorded bucket is a count, never a choice.
    expect(screen.getAllByText("3 compounds: concentration not recorded")).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: /not recorded/ })).not.toBeInTheDocument();
    // A stage column's choice says what it does to the result.
    expect(screen.getByText("The stage's hits recompute.")).toBeInTheDocument();

    fireEvent.click(choices[0]);
    expect(setConcentration).toHaveBeenCalledWith({
      channelId: "ch-mixed",
      testConcentration: { value: 10, unit: "µM" },
    });
  });

  it("lets a chosen concentration be chosen again", () => {
    render(<ChannelsSection campaign={staged} projectId="p1" readOnly={false} />, { wrapper });

    expect(screen.getByText("Counter: values at 10 µM")).toBeInTheDocument();
    expect(screen.getByText("Its values recompute.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Choose a concentration again" }));
    expect(setConcentration).toHaveBeenCalledWith({
      channelId: "ch-chosen",
      testConcentration: null,
    });
  });

  it("offers no choice when read-only", () => {
    render(<ChannelsSection campaign={staged} projectId="p1" readOnly />, { wrapper });
    expect(screen.queryByRole("button", { name: /^Use values at/ })).not.toBeInTheDocument();
  });

  it("names the rule the column computes, not the one configured", () => {
    const meanOfPercent = {
      id: "c1",
      stages: [],
      channels: [
        makeChannel({
          id: "ch-gm",
          label: "% Inhibition",
          selection_rule: "geometric_mean",
          description: { ...description, rule: "mean across runs", needs_concentration: false },
        }),
      ],
    } as unknown as CampaignResponse;
    render(<ChannelsSection campaign={meanOfPercent} projectId="p1" readOnly />, { wrapper });

    const chip = screen.getByText("% Inhibition").closest("[title]");
    expect(chip).toHaveAttribute("title", "Readout data · mean across runs");
    expect(chip).not.toHaveTextContent("geometric mean");
  });
});
