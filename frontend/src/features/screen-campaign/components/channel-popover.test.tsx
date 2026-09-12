import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { CampaignChannelResponse } from "../types";
import { ChannelPopoverForm } from "./channel-popover";

const { addMutate, updateMutate } = vi.hoisted(() => ({
  addMutate: vi.fn(),
  updateMutate: vi.fn(),
}));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useAddCampaignChannelApiV1CampaignsCampaignIdChannelsPost: () => ({
    mutate: addMutate,
    isPending: false,
  }),
  useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch: () => ({
    mutate: updateMutate,
    isPending: false,
  }),
  useRemoveCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdDelete: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocolSummaries: () => ({ data: [{ id: "proto-1", name: "Kinase Panel" }] }),
  useProtocol: () => ({
    data: {
      id: "proto-1",
      name: "Kinase Panel",
      readout_definitions: [{ id: "rd-1", name: "% Inhibition", data_type: "numeric" }],
    },
  }),
}));

vi.mock("../hooks/use-campaigns", () => ({
  campaignKeys: { detail: (id: string) => ["campaigns", "detail", id] },
}));

// Radix Select portals a listbox whose items call scrollIntoView +
// hasPointerCapture — jsdom ships neither.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

const existing = {
  id: "ch-1",
  label: "% Inhibition",
  protocol_id: "proto-1",
  readout_definition_id: "rd-1",
  source_kind: "readout_data",
  selection_rule: "latest_approved_run",
  qualifier_handling: "include_qualified",
  display_order: 0,
  resolve_from_all_runs: false,
} as unknown as CampaignChannelResponse;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const RUN_SCOPE = "Resolve from all runs of the protocol";

beforeEach(() => {
  addMutate.mockClear();
  updateMutate.mockClear();
});

/** Open the Nth <Select> and click the option whose text matches. */
function pick(comboboxIndex: number, optionText: string | RegExp) {
  fireEvent.click(screen.getAllByRole("combobox")[comboboxIndex]);
  fireEvent.click(within(screen.getByRole("listbox")).getByText(optionText));
}

describe("ChannelPopoverForm run scope", () => {
  it("defaults off and sends the flag when adding a readout", async () => {
    render(<ChannelPopoverForm campaignId="c1" projectId="p1" onClose={vi.fn()} />, { wrapper });

    fireEvent.change(screen.getByPlaceholderText("e.g. Primary IC50"), {
      target: { value: "Counter-screen" },
    });
    pick(0, "Kinase Panel");
    pick(1, "% Inhibition");

    const checkbox = screen.getByRole("checkbox", { name: RUN_SCOPE });
    expect(checkbox).toHaveAttribute("data-state", "unchecked");
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByRole("button", { name: "Add Readout" }));

    await waitFor(() => expect(addMutate).toHaveBeenCalledTimes(1));
    expect(addMutate.mock.calls[0][0].data).toMatchObject({
      label: "Counter-screen",
      protocol_id: "proto-1",
      readout_definition_id: "rd-1",
      resolve_from_all_runs: true,
    });
  });

  it("sends the flag on update, seeded from the existing channel", async () => {
    render(
      <ChannelPopoverForm campaignId="c1" projectId="p1" existing={existing} onClose={vi.fn()} />,
      { wrapper },
    );

    fireEvent.click(screen.getByRole("checkbox", { name: RUN_SCOPE }));
    fireEvent.click(screen.getByRole("button", { name: "Update" }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate).toHaveBeenCalledWith({
      campaignId: "c1",
      channelId: "ch-1",
      data: {
        label: "% Inhibition",
        selection_rule: "latest_approved_run",
        qc_filter: null,
        resolve_from_all_runs: true,
      },
    });
  });

  it("keeps an already-on channel on when nothing is touched", async () => {
    render(
      <ChannelPopoverForm
        campaignId="c1"
        projectId="p1"
        existing={{ ...existing, resolve_from_all_runs: true }}
        onClose={vi.fn()}
      />,
      { wrapper },
    );

    expect(screen.getByRole("checkbox", { name: RUN_SCOPE })).toHaveAttribute(
      "data-state",
      "checked",
    );
    fireEvent.click(screen.getByRole("button", { name: "Update" }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate.mock.calls[0][0].data).toMatchObject({ resolve_from_all_runs: true });
  });
});
