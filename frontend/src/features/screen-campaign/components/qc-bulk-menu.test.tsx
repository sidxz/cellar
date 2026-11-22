import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { QcVerdictCountsResponse, SetQcVerdictsRequest } from "@/shared/lib/api/model";

import type { CampaignResponse } from "../types";
import { QcBulkMenu } from "./qc-bulk-menu";

type OnSuccess = (res: QcVerdictCountsResponse, vars: { data: SetQcVerdictsRequest }) => void;
const { mutate, showSuccess, hook } = vi.hoisted(() => ({
  mutate: vi.fn(),
  showSuccess: vi.fn(),
  hook: { options: undefined as { mutation?: { onSuccess?: OnSuccess } } | undefined },
}));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut: (options: typeof hook.options) => {
    hook.options = options;
    return { mutate, isPending: false };
  },
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

function renderMenu(
  opts: { stage?: string | null; readOnly?: boolean; ticked?: string[]; hidden?: number } = {},
) {
  return render(
    <QcBulkMenu
      campaign={campaign}
      resultIds={opts.ticked ?? ["r1", "r2", "r3"]}
      hiddenCount={opts.hidden ?? 0}
      selectedStageId={opts.stage === undefined ? "s1" : opts.stage}
      readOnly={opts.readOnly ?? false}
    />,
    { wrapper },
  );
}

/** Open one verdict's window from its bulk-bar button. */
function pick(item: "Mark verified…" | "Mark failed…" | "Clear QC…") {
  const button = { "Mark verified…": "Mark QC verified…", "Mark failed…": "Mark QC failed…" };
  fireEvent.click(screen.getByRole("button", { name: item === "Clear QC…" ? item : button[item] }));
}

beforeEach(() => {
  mutate.mockReset();
  showSuccess.mockClear();
});

describe("QcBulkMenu", () => {
  it("renders nothing when read-only", () => {
    expect(renderMenu({ readOnly: true }).container).toBeEmptyDOMElement();
  });

  it("forecasts the ticked rows x the stage's columns, and the overwrite box adds marked cells", () => {
    renderMenu();
    pick("Mark verified…");
    expect(screen.getByText("2 cells")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Also change cells someone already marked"));
    expect(screen.getByText("3 cells")).toBeInTheDocument();
  });

  it("applies to the stage's columns and names the ticked rows", () => {
    renderMenu();
    pick("Mark verified…");
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mutate.mock.calls[0]).toEqual([
      {
        campaignId: "c1",
        data: {
          verdict: "verified",
          targets: [{ channel_ids: ["ca", "cb"], result_ids: ["r1", "r2", "r3"] }],
          overwrite: false,
        },
      },
    ]);
  });

  it("reaches only the ticked rows, and says when filters hide some", () => {
    renderMenu({ ticked: ["r2"], hidden: 1 });
    pick("Mark verified…");
    expect(screen.getByText("1 selected row, 1 hidden by filters")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mutate.mock.calls[0][0].data.targets[0].result_ids).toEqual(["r2"]);
  });

  it("is off until rows are ticked", () => {
    renderMenu({ ticked: [] });
    for (const name of ["Mark QC verified…", "Mark QC failed…", "Clear QC…"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
  });

  it("a stage with no columns of its own ticks none, so Apply is off", () => {
    renderMenu({ stage: "s-empty" });
    pick("Mark verified…");
    expect(screen.getByText("0 cells")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
    for (const box of screen.getAllByRole("checkbox").slice(0, 3)) {
      expect(box).toHaveAttribute("aria-checked", "false");
    }
  });

  it("groups the columns under their stage, campaign columns under Whole campaign", () => {
    renderMenu();
    pick("Mark verified…");
    expect(screen.getByText("Primary")).toBeInTheDocument();
    expect(screen.getByText("Whole campaign")).toBeInTheDocument();
  });

  it("sends the note only when one is typed, and the forecast counts its re-stamps", () => {
    renderMenu();
    pick("Mark failed…");
    fireEvent.click(screen.getByLabelText("Also change cells someone already marked"));
    expect(screen.getByText("2 cells")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mutate.mock.calls[0][0].data).not.toHaveProperty("note");

    pick("Mark failed…");
    fireEvent.click(screen.getByLabelText("Also change cells someone already marked"));
    fireEvent.change(screen.getByPlaceholderText("Note (optional)"), {
      target: { value: " edge well " },
    });
    // r1's B is already Failed with no note: the named note re-stamps it.
    expect(screen.getByText("3 cells")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mutate.mock.calls[1][0].data.note).toBe("edge well");
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
  });

  const done = (verdict: SetQcVerdictsRequest["verdict"], res: QcVerdictCountsResponse) => {
    renderMenu();
    hook.options?.mutation?.onSuccess?.(res, { data: { verdict, targets: [] } });
    return showSuccess.mock.calls[0][0];
  };

  it("toasts from the hook, count first, omitting zero parts", () => {
    expect(done("verified", { changed: 2, unchanged: 3, kept: 1, no_result: 1 })).toBe(
      "Verified 2 cells · 3 already Verified · 1 kept (already marked) · 1 had no result",
    );
  });

  it("toasts failed and cleared in bench words, singular for one cell", () => {
    expect(done("failed", { changed: 1, unchanged: 1, kept: 0, no_result: 0 })).toBe(
      "Marked 1 cell Failed · 1 already Failed",
    );
    showSuccess.mockClear();
    expect(done("not_tested", { changed: 3, unchanged: 2, kept: 0, no_result: 0 })).toBe(
      "Cleared QC on 3 cells · 2 already Not tested",
    );
  });
});
