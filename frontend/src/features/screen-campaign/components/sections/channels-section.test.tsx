import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { CampaignChannelResponse, CampaignResponse } from "../../types";
import { ChannelsSection } from "./channels-section";

const { mutateAsync, mirrorMutate } = vi.hoisted(() => ({
  mutateAsync: vi.fn(async () => ({})),
  mirrorMutate: vi.fn(),
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
    selection_rule: "latest_approved_run",
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

  it("renders chips: DR mark on curve readouts, rule only when non-default", () => {
    render(<ChannelsSection campaign={campaign} projectId="p1" readOnly />, { wrapper });

    const ic50 = screen.getByText("IC50").closest("[title]");
    expect(ic50).toHaveTextContent("DR");
    expect(ic50).toHaveAttribute("title", "Dose-response curve · latest approved run");
    expect(screen.queryByText("latest approved run")).not.toBeInTheDocument();

    const viability = screen.getByText("% Viability").closest("[title]");
    expect(viability).toHaveTextContent("mean across runs");
    expect(viability).not.toHaveTextContent("DR");
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

/** Open the Nth <Select> and click the option whose text matches. */
function pick(comboboxIndex: number, optionText: string | RegExp) {
  fireEvent.click(screen.getAllByRole("combobox")[comboboxIndex]);
  fireEvent.click(within(screen.getByRole("listbox")).getByText(optionText));
}

describe("MirrorProtocolPopover", () => {
  beforeEach(() => mirrorMutate.mockClear());

  it("sends the picked parent stage alongside stage_name", async () => {
    render(<ChannelsSection campaign={withStage} projectId="p1" readOnly={false} />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: /Mirror protocol/ }));
    pick(0, "Kinase Panel");
    await screen.findByLabelText("Parent stage");
    pick(1, "Primary");
    fireEvent.click(screen.getByRole("button", { name: "Mirror" }));

    expect(mirrorMutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: {
        protocol_id: "proto-1",
        stage_name: "Kinase Panel hits",
        parent_stage_id: "st-1",
      },
    });
  });

  it("reuses a colliding criteria stage — advisory, Mirror still enabled", async () => {
    render(<ChannelsSection campaign={withStage} projectId="p1" readOnly={false} />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: /Mirror protocol/ }));
    pick(0, "Kinase Panel");
    fireEvent.change(screen.getByPlaceholderText("e.g. Screening Hits"), {
      target: { value: "primary" },
    });

    expect(
      screen.getByText('Reuses stage "Primary": its criteria will be replaced.'),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mirror" })).toBeEnabled();
  });

  it("blocks a name that belongs to a manual stage", async () => {
    const manual = {
      ...withStage,
      stages: [{ id: "st-m", name: "Confirmed", display_order: 0, kind: "manual" }],
    } as unknown as CampaignResponse;
    render(<ChannelsSection campaign={manual} projectId="p1" readOnly={false} />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: /Mirror protocol/ }));
    pick(0, "Kinase Panel");
    fireEvent.change(screen.getByPlaceholderText("e.g. Screening Hits"), {
      target: { value: "Confirmed" },
    });

    expect(screen.getByText("Confirmed is a manual stage; pick another name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mirror" })).toBeDisabled();
  });

  it("leaves parent_stage_id off when the stage stays at the root", async () => {
    render(<ChannelsSection campaign={withStage} projectId="p1" readOnly={false} />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: /Mirror protocol/ }));
    pick(0, "Kinase Panel");
    await screen.findByLabelText("Parent stage");
    fireEvent.click(screen.getByRole("button", { name: "Mirror" }));

    expect(mirrorMutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: {
        protocol_id: "proto-1",
        stage_name: "Kinase Panel hits",
        parent_stage_id: undefined,
      },
    });
  });
});
