import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CampaignResponse } from "../types";
import { emptyFilters } from "./campaign-filter-bar";
import { QcBulkMenu } from "./qc-bulk-menu";

const { mutate, showSuccess } = vi.hoisted(() => ({ mutate: vi.fn(), showSuccess: vi.fn() }));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut: () => ({ mutate, isPending: false }),
}));
vi.mock("@/shared/lib/toast", () => ({ showSuccess, showError: vi.fn() }));
vi.mock("../hooks/use-campaigns", () => ({
  campaignKeys: { detail: (id: string) => ["campaigns", "detail", id] },
}));

const m = (channel_id: string, qc_verdict: string, holds_result = true) => ({
  id: `m-${channel_id}-${qc_verdict}-${Math.random()}`,
  channel_id,
  qc_verdict,
  holds_result,
});

// ca, cb belong to stage s1; cc to s2. r1: ca untested, cb failed. r2: ca untested,
// cb an untested ND (holds no result). r3 has no measurements at all.
const campaign = {
  id: "c1",
  stages: [{ id: "s1", name: "Primary", kind: "manual" }],
  channels: [
    { id: "ca", label: "A", stage_id: "s1" },
    { id: "cb", label: "B", stage_id: "s1" },
    { id: "cc", label: "C", stage_id: "s2" },
  ],
  results: [
    { id: "r1", measurements: [m("ca", "not_tested"), m("cb", "failed")], stage_outcomes: [] },
    {
      id: "r2",
      measurements: [m("ca", "not_tested"), m("cb", "not_tested", false)],
      stage_outcomes: [],
    },
    { id: "r3", measurements: [], stage_outcomes: [] },
  ],
} as unknown as CampaignResponse;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderMenu(opts: { stage?: string | null; readOnly?: boolean } = {}) {
  return render(
    <QcBulkMenu
      campaign={campaign}
      filters={emptyFilters()}
      selectedStageId={opts.stage === undefined ? "s1" : opts.stage}
      readOnly={opts.readOnly ?? false}
    />,
    { wrapper },
  );
}

function pick(item: string) {
  fireEvent.keyDown(screen.getByRole("button", { name: "QC" }), { key: "Enter" });
  fireEvent.click(screen.getByRole("menuitem", { name: item }));
}

beforeEach(() => {
  mutate.mockReset();
  showSuccess.mockClear();
});

describe("QcBulkMenu", () => {
  it("renders nothing when read-only", () => {
    expect(renderMenu({ readOnly: true }).container).toBeEmptyDOMElement();
  });

  it("forecasts the visible rows x the stage's columns, and the overwrite box adds marked cells", () => {
    renderMenu();
    pick("Mark verified…");
    expect(screen.getByText("2 cells")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Also change cells someone already marked"));
    expect(screen.getByText("3 cells")).toBeInTheDocument();
  });

  it("applies to the stage's columns and the visible rows", () => {
    renderMenu();
    pick("Mark verified…");
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mutate.mock.calls[0][0]).toEqual({
      campaignId: "c1",
      data: {
        verdict: "verified",
        targets: [{ channel_ids: ["ca", "cb"], result_ids: ["r1", "r2", "r3"] }],
        overwrite: false,
      },
    });
  });

  it("defaults to every channel with no stage selected", () => {
    renderMenu({ stage: null });
    pick("Mark failed…");
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mutate.mock.calls[0][0].data.targets[0].channel_ids).toEqual(["ca", "cb", "cc"]);
  });

  it("clear sends not_tested and shows neither overwrite nor note", () => {
    renderMenu();
    pick("Clear QC…");
    expect(screen.queryByLabelText("Also change cells someone already marked")).toBeNull();
    expect(screen.queryByPlaceholderText("Note (optional)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mutate.mock.calls[0][0].data.verdict).toBe("not_tested");
    mutate.mock.calls[0][1].onSuccess({ changed: 3, unchanged: 0, kept: 0, no_result: 0 });
    expect(showSuccess).toHaveBeenCalledWith("Cleared 3 cells");
  });

  it("toasts the counts, omitting zero parts", () => {
    renderMenu();
    pick("Mark verified…");
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    mutate.mock.calls[0][1].onSuccess({ changed: 2, unchanged: 0, kept: 1, no_result: 1 });
    expect(showSuccess).toHaveBeenCalledWith(
      "Verified 2 cells · 1 kept (already marked) · 1 had no result",
    );
  });
});
