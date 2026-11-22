import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CampaignResponse, CampaignResultResponse, StageOutcome } from "../types";
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

// One row per outcome the manual stage can hold.
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

function renderMenu(opts: { ticked?: string[]; hidden?: number; readOnly?: boolean } = {}) {
  return render(
    <StageBulkMenu
      campaign={campaign}
      resultIds={opts.ticked ?? ["r-pending-1", "r-pending-2"]}
      hiddenCount={opts.hidden ?? 0}
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
  // The stage here is hand-picked, so there are no criteria to override.
  const buttons = screen.getAllByRole("button", {
    name: new RegExp(`^Mark \\d+ ${label === "Mark hit…" ? "hit" : "miss"}$`),
  });
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
        resultIds={["r-hit"]}
        hiddenCount={0}
        selectedStageId={null}
        readOnly={false}
      />,
      { wrapper },
    );
    expect(container).toBeEmptyDOMElement();

    const readOnly = renderMenu({ readOnly: true });
    expect(readOnly.container).toBeEmptyDOMElement();
  });

  it("is off until rows are ticked", () => {
    renderMenu({ ticked: [] });
    expect(screen.getByRole("button", { name: "Mark hit…" })).toBeDisabled();
  });

  it("acts on exactly the ticked rows", () => {
    renderMenu();
    act("Mark hit…", "Re-tested, keeping for dose-response");

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

  it("says when the filters hide some ticked rows", () => {
    renderMenu({ hidden: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Mark hit…" }));
    expect(screen.getByText(/2 selected rows, 1 hidden by filters/)).toBeInTheDocument();
  });

  it("sends outcome miss for Mark miss", () => {
    renderMenu();
    act("Mark miss…", "Off-target in counter-screen");

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ outcome: "miss", reason: "Off-target in counter-screen" }),
      }),
    );
  });

  it("refuses to mark hit or miss until a reason is typed", () => {
    renderMenu();
    act("Mark hit…", "   ");
    expect(mutate).not.toHaveBeenCalled();
  });

  it("clears overrides with outcome null and no reason", () => {
    renderMenu({ ticked: ["r-hit"] });
    fireEvent.click(screen.getByRole("button", { name: "Clear overrides" }));
    // No reason field on the clear path — nothing is being asserted about
    // the rows, the override is simply dropped.
    expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear 1 override" }));

    expect(mutate).toHaveBeenCalledWith({
      campaignId: "c1",
      stageId: STAGE,
      data: { result_ids: ["r-hit"], outcome: null, reason: null },
    });
  });
});

describe("StageBulkMenu on a criteria stage", () => {
  const criteria = {
    ...campaign,
    stages: [{ id: STAGE, name: "Confirmed Active", kind: "criteria" }],
  } as unknown as CampaignResponse;

  it("says it overrides the selection criteria", () => {
    render(
      <StageBulkMenu
        campaign={criteria}
        resultIds={["r-pending-1", "r-pending-2"]}
        hiddenCount={0}
        selectedStageId={STAGE}
        readOnly={false}
      />,
      { wrapper },
    );
    fireEvent.click(screen.getByRole("button", { name: "Mark hit…" }));
    expect(
      screen.getByText("Override the selection criteria for 2 selected rows?"),
    ).toBeInTheDocument();
    expect(screen.getByText(/whatever its selection criteria say/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "Re-tested" } });
    fireEvent.click(screen.getByRole("button", { name: "Override and mark 2 hit" }));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ outcome: "hit" }) }),
    );
  });
});
