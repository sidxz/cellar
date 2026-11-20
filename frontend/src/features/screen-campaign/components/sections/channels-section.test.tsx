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

// The runs the concentration control reads: two at the chosen 10 µM, one at
// 50 µM, one with no dose recorded, and one at 50 µM on another stage.
vi.mock("@/shared/lib/api/runs/runs", () => ({
  getListRunsByProtocolApiV1ProtocolsProtocolIdRunsGetQueryOptions: (id: string) => ({
    queryKey: ["runs", id],
    queryFn: async () => [
      { id: "run-10a", protocol_id: "proto-1", conditions: { "Test concentration": "10 µM" } },
      { id: "run-10b", protocol_id: "proto-1", conditions: { "Test concentration": "10 uM" } },
      { id: "run-50", protocol_id: "proto-1", conditions: { "Test concentration": "50 µM" } },
      { id: "run-none", protocol_id: "proto-1", conditions: {} },
      { id: "run-other", protocol_id: "proto-1", conditions: { "Test concentration": "50 µM" } },
    ],
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
  it("groups readouts under a heading per protocol", () => {
    render(<ChannelsSection campaign={campaign} projectId="p1" readOnly />, { wrapper });

    expect(screen.getByText("Kinase Panel")).toBeInTheDocument();
    expect(screen.getByText("Resazurin Viability")).toBeInTheDocument();
    expect(screen.getByText("IC50")).toBeInTheDocument();
    expect(screen.getByText("% Viability")).toBeInTheDocument();
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
  value_count: 40,
};

const seedRuns = (stageId: string, ...ids: string[]) =>
  ids.map((run_id) => ({ run_id, protocol_id: "proto-1", stage_ids: [stageId] }));

const staged = {
  id: "c1",
  stages: [
    { id: "st-1", name: "Primary", display_order: 0, kind: "criteria" },
    { id: "st-2", name: "Retest", display_order: 1, kind: "criteria" },
  ],
  seed_runs: [
    ...seedRuns("st-1", "run-10a", "run-10b", "run-50", "run-none"),
    ...seedRuns("st-2", "run-other"),
  ],
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

// A stage column pinned to 10 µM whose stage also holds a 50 µM run.
const pinned = {
  ...staged,
  channels: [
    makeChannel({
      id: "ch-pinned",
      label: "% Inhibition",
      stage_id: "st-1",
      test_concentration: { value: 10, unit: "µM" },
      description: { ...description, needs_concentration: false },
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

  it("asks a column measured at several doses to choose one, naming each with its count", () => {
    render(<ChannelsSection campaign={staged} projectId="p1" readOnly={false} />, { wrapper });

    expect(screen.getByText(/10 µM \(40 compounds\) and 1 µM \(12\)/)).toBeInTheDocument();
    const choices = screen.getAllByRole("button", { name: /^Use / });
    expect(choices.map((b) => b.textContent)).toEqual(["Use 10 µM", "Use 1 µM"]);
    // The not-recorded bucket is a count, never a choice.
    expect(screen.getAllByText(/^3 compounds/)).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: /not recorded/ })).not.toBeInTheDocument();

    fireEvent.click(choices[0]);
    expect(setConcentration).toHaveBeenCalledWith({
      channelId: "ch-mixed",
      testConcentration: { value: 10, unit: "µM" },
    });
  });

  it("says which dose a pinned column uses and which of its stage's runs it sets aside", async () => {
    render(<ChannelsSection campaign={pinned} projectId="p1" readOnly={false} />, { wrapper });

    // run-10b's "10 uM" is the same dose; run-none has none; run-other is another stage's.
    expect(
      await screen.findByText("Uses the 10 µM values · 1 run at 50 µM set aside"),
    ).toBeInTheDocument();
  });

  it("changes a pinned column to another dose found, or clears the choice", () => {
    render(<ChannelsSection campaign={pinned} projectId="p1" readOnly={false} />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    // The dose already in use isn't offered again.
    expect(screen.getAllByRole("button", { name: /^Use / }).map((b) => b.textContent)).toEqual([
      "Use 1 µM",
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Use 1 µM" }));
    expect(setConcentration).toHaveBeenLastCalledWith({
      channelId: "ch-pinned",
      testConcentration: { value: 1, unit: "µM" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear choice" }));
    expect(setConcentration).toHaveBeenLastCalledWith({
      channelId: "ch-pinned",
      testConcentration: null,
    });
  });

  it("leaves out the set-aside part when no run is at another dose", async () => {
    const allAtTen = {
      ...pinned,
      seed_runs: seedRuns("st-1", "run-10a", "run-10b", "run-none"),
    } as unknown as CampaignResponse;
    render(<ChannelsSection campaign={allAtTen} projectId="p1" readOnly={false} />, { wrapper });
    expect(await screen.findByText("Uses the 10 µM values")).toBeInTheDocument();
    expect(screen.queryByText(/set aside/)).not.toBeInTheDocument();
  });

  it("offers no choice when read-only", () => {
    render(<ChannelsSection campaign={staged} projectId="p1" readOnly />, { wrapper });
    expect(screen.queryByRole("button", { name: /^Use / })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change" })).not.toBeInTheDocument();
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
