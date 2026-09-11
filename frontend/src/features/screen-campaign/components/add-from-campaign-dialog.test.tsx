import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { AddFromCampaignDialog } from "./add-from-campaign-dialog";

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useAddResultsFromCampaignApiV1CampaignsCampaignIdAddFromCampaignPost: () => ({
    mutate,
    isPending: false,
  }),
}));

vi.mock("../hooks/use-campaigns", () => ({
  campaignKeys: { detail: (id: string) => ["campaigns", "detail", id] },
  useCampaigns: () => ({
    data: [
      { id: "src-staged", name: "Source Staged", status: "closed" },
      { id: "src-plain", name: "Source Plain", status: "draft" },
    ],
    isLoading: false,
  }),
  // Only the first source has stages, so switching sources must drop the pick.
  useCampaign: (id: string) => ({
    data:
      id === "src-staged"
        ? { id, stages: [{ id: "stage-confirmed", name: "Confirmed" }] }
        : { id, stages: [] },
    isLoading: false,
  }),
}));

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderDialog() {
  return render(
    <AddFromCampaignDialog campaignId="target-1" projectId="proj-1" open onOpenChange={vi.fn()} />,
    { wrapper: Wrapper },
  );
}

/** Open the Nth <Select> and click the option whose text matches. */
function pick(comboboxIndex: number, optionText: string | RegExp) {
  fireEvent.click(screen.getAllByRole("combobox")[comboboxIndex]);
  fireEvent.click(within(screen.getByRole("listbox")).getByText(optionText));
}

const stageTrigger = () => screen.getAllByRole("combobox")[1];

describe("AddFromCampaignDialog", () => {
  beforeEach(() => {
    mutate.mockClear();
  });

  it("resets the stage picker to All compounds when the source campaign changes", () => {
    renderDialog();

    pick(0, "Source Staged");
    pick(1, /Hits at/);
    expect(stageTrigger()).toHaveTextContent(/Hits at "Confirmed"/);

    pick(0, "Source Plain");
    expect(stageTrigger()).toHaveTextContent("All compounds");
  });

  it("submits stage_id: null for All compounds", () => {
    renderDialog();

    pick(0, "Source Staged");
    fireEvent.click(screen.getByRole("button", { name: /add compounds/i }));

    expect(mutate).toHaveBeenCalledWith({
      campaignId: "target-1",
      data: {
        source_campaign_id: "src-staged",
        stage_id: null,
        description: undefined,
      },
    });
  });

  it("submits the stage id when a stage is chosen", () => {
    renderDialog();

    pick(0, "Source Staged");
    pick(1, /Hits at/);
    fireEvent.click(screen.getByRole("button", { name: /add compounds/i }));

    expect(mutate).toHaveBeenCalledWith({
      campaignId: "target-1",
      data: {
        source_campaign_id: "src-staged",
        stage_id: "stage-confirmed",
        description: undefined,
      },
    });
  });
});
