import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { StageOutcome } from "../../types";
import { emptyFilters } from "../campaign-filter-bar";
import {
  CompoundValueCell,
  type CompoundValueCellProps,
  RemoveSelectedButton,
  isReportedEndpoint,
} from "./results-grid";

function renderCell(overrides: Partial<CompoundValueCellProps> = {}) {
  return render(
    <CompoundValueCell
      prefix=""
      value={13.6}
      unit="uM"
      replicates={null}
      verdict={null}
      overridden={false}
      overrideReason={null}
      reported={false}
      readOnly
      onEdit={() => {}}
      {...overrides}
    />,
  );
}

describe("CompoundValueCell reported marker", () => {
  it("shows the reported chip for a DR measurement sourced from an endpoint row", () => {
    const reported = isReportedEndpoint(true, { source_readout_id: "rd-1", source_curve_id: null });
    expect(reported).toBe(true);

    renderCell({ reported });
    expect(screen.getByText("reported")).toHaveAttribute(
      "title",
      "Reported endpoint — no fitted curve for this compound",
    );
  });

  it("shows no chip for a DR measurement backed by a fitted curve", () => {
    const reported = isReportedEndpoint(true, { source_readout_id: null, source_curve_id: "c-1" });
    expect(reported).toBe(false);

    renderCell({ reported });
    expect(screen.queryByText("reported")).toBeNull();
  });

  it("shows no chip on a non-DR channel even when a readout id is present", () => {
    const reported = isReportedEndpoint(false, {
      source_readout_id: "rd-1",
      source_curve_id: null,
    });
    expect(reported).toBe(false);

    renderCell({ reported });
    expect(screen.queryByText("reported")).toBeNull();
  });

  it("keeps the chip on the marker line beside the verdict chip", () => {
    renderCell({ reported: true, verdict: "pass" });
    const chip = screen.getByText("reported");
    const markerLine = chip.parentElement;
    expect(markerLine).toHaveTextContent("pass");
    // Value stays on its own line above the markers so the 120px column
    // never clips it.
    expect(markerLine).not.toHaveTextContent("13.6");
  });
});

// ── Bulk remove ───────────────────────────────────────────────────────────────

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));

vi.mock("@/shared/lib/api/campaigns/campaigns", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useBulkRemoveResultRowsApiV1CampaignsCampaignIdResultsBulkRemovePost: () => ({
    mutate,
    isPending: false,
  }),
}));

const STAGE = "stage-1";

function row(id: string, outcome: StageOutcome) {
  return {
    result: {
      id,
      molecule_id: `mol-${id}`,
      measurements: [],
      stage_outcomes: [{ stage_id: STAGE, outcome, overridden: false, checks: [] }],
    },
  };
}

function renderToolbar(stageOutcomes: StageOutcome[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RemoveSelectedButton
        campaignId="c1"
        rows={[row("r-hit", "hit"), row("r-miss", "miss")] as never}
        filters={{ ...emptyFilters(), stageOutcomes: new Set(stageOutcomes) }}
        selectedStageId={STAGE}
      />
    </QueryClientProvider>,
  );
}

describe("RemoveSelectedButton visible selection", () => {
  beforeEach(() => mutate.mockClear());

  it("removes every selected row when no chip filter is on", () => {
    renderToolbar([]);
    fireEvent.click(screen.getByRole("button", { name: "Remove selected (2)" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove 2" }));
    expect(mutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: { result_ids: ["r-hit", "r-miss"] },
    });
  });

  it("leaves a selected row the chip filter hides untouched", () => {
    // AG Grid keeps r-miss selected after the "Hit" chip hides it; the
    // chemist can't see it, so it must not be removed — nor counted.
    renderToolbar(["hit"]);
    fireEvent.click(screen.getByRole("button", { name: "Remove selected (1)" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove 1" }));
    expect(mutate).toHaveBeenCalledWith({ campaignId: "c1", data: { result_ids: ["r-hit"] } });
  });
});
