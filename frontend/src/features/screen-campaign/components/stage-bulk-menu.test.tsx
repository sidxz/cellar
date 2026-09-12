import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CampaignResponse, CampaignResultResponse, StageOutcome } from "../types";
import { emptyFilters } from "./campaign-filter-bar";
import { StageBulkMenu } from "./stage-bulk-menu";

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useSetStageOverridesApiV1CampaignsCampaignIdStagesStageIdOverridesPut: () => ({
    mutate,
    isPending: false,
  }),
}));

vi.mock("../hooks/use-campaigns", () => ({
  campaignKeys: { detail: (id: string) => ["campaigns", "detail", id] },
}));

const STAGE = "stage-manual";

function makeResult(id: string, outcome: StageOutcome): CampaignResultResponse {
  return {
    id,
    molecule_id: `mol-${id}`,
    measurements: [],
    stage_outcomes: [{ stage_id: STAGE, outcome, overridden: false, checks: [] }],
  } as unknown as CampaignResultResponse;
}

// One row per outcome the manual stage can hold, so a chip filter genuinely
// narrows the target set rather than trivially matching everything.
const campaign = {
  id: "c1",
  stages: [{ id: STAGE, name: "Take Forward", kind: "manual" }],
  results: [
    makeResult("r-pending-1", "pending"),
    makeResult("r-pending-2", "pending"),
    makeResult("r-hit", "hit"),
    makeResult("r-gated", "not_in_stage"),
  ],
} as unknown as CampaignResponse;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderMenu(opts: { stageOutcomes?: StageOutcome[]; readOnly?: boolean } = {}) {
  return render(
    <StageBulkMenu
      campaign={campaign}
      filters={{ ...emptyFilters(), stageOutcomes: new Set(opts.stageOutcomes ?? []) }}
      selectedStageId={STAGE}
      readOnly={opts.readOnly ?? false}
    />,
    { wrapper },
  );
}

/** Open one action's confirm dialog and press its footer button. */
function act(label: string, reason?: string) {
  fireEvent.click(screen.getByRole("button", { name: label }));
  if (reason !== undefined) {
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: reason } });
  }
  const buttons = screen.getAllByRole("button", { name: new RegExp(`^${label} \\d+ rows?$`) });
  fireEvent.click(buttons[buttons.length - 1]);
}

beforeEach(() => {
  mutate.mockClear();
});

describe("StageBulkMenu", () => {
  it("renders nothing for the All tab or a read-only campaign", () => {
    const { container } = render(
      <StageBulkMenu
        campaign={campaign}
        filters={emptyFilters()}
        selectedStageId={null}
        readOnly={false}
      />,
      { wrapper },
    );
    expect(container).toBeEmptyDOMElement();

    const readOnly = renderMenu({ readOnly: true });
    expect(readOnly.container).toBeEmptyDOMElement();
  });

  it("targets every row when no chip is on", () => {
    renderMenu();
    expect(screen.getByText("Bulk (4 visible rows):")).toBeInTheDocument();
  });

  it("targets only the rows the active chip filter leaves visible", () => {
    renderMenu({ stageOutcomes: ["pending"] });
    expect(screen.getByText("Bulk (2 visible rows):")).toBeInTheDocument();

    act("Promote", "Re-tested, keeping for dose-response");

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith({
      campaignId: "c1",
      stageId: STAGE,
      data: {
        result_ids: ["r-pending-1", "r-pending-2"],
        outcome: "hit",
        reason: "Re-tested, keeping for dose-response",
      },
    });
  });

  it("sends outcome miss for a demote", () => {
    renderMenu({ stageOutcomes: ["pending"] });
    act("Demote", "Off-target in counter-screen");

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ outcome: "miss", reason: "Off-target in counter-screen" }),
      }),
    );
  });

  it("refuses promote/demote until a reason is typed", () => {
    renderMenu({ stageOutcomes: ["pending"] });
    act("Promote", "   ");
    expect(mutate).not.toHaveBeenCalled();
  });

  it("clears overrides with outcome null and no reason", () => {
    renderMenu({ stageOutcomes: ["hit"] });
    fireEvent.click(screen.getByRole("button", { name: "Clear overrides" }));
    // No reason field on the clear path — nothing is being asserted about
    // the rows, the override is simply dropped.
    expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Clear overrides 1 row$/ }));

    expect(mutate).toHaveBeenCalledWith({
      campaignId: "c1",
      stageId: STAGE,
      data: { result_ids: ["r-hit"], outcome: null, reason: null },
    });
  });
});
