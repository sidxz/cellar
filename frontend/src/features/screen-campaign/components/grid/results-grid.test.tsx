import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { columnTooltip } from "../../lib/column-description";
import type {
  CampaignChannelResponse,
  CampaignMeasurementResponse,
  CampaignResponse,
  StageOutcome,
} from "../../types";
import { emptyFilters } from "../campaign-filter-bar";
import {
  CompoundValueCell,
  type CompoundValueCellProps,
  MeasurementFacts,
  NotDeterminedCell,
  RemoveSelectedButton,
  StageColumnHeader,
  isReportedEndpoint,
} from "./results-grid";

vi.mock("@/features/inventory/hooks/use-batches", () => ({
  useBatchesByMolecule: () => ({ data: [{ id: "b-1", batch_number: "B-007" }] }),
}));
vi.mock("../../hooks/use-campaign-run-labels", () => ({
  useCampaignRunLabels: () => (id: string) => ({
    protocolName: "Kinase Panel",
    text: id === "run-1" ? "Run on Nov 12, 2026" : "Run on Nov 14, 2026",
  }),
}));

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

// ── Stage column header ──────────────────────────────────────────────────────

const LABEL =
  "Retest · % Inhibition · single concentration 10 µM · mean of 3 replicates · 3 runs · mean across runs";
const SHORT = "single concentration 10 µM · mean of 3 replicates · 3 runs · mean across runs";

const describedColumn = {
  id: "ch-1",
  label: "% Inhibition",
  description: {
    stage_name: "Retest",
    readout_label: "% Inhibition",
    design: "single_concentration",
    concentrations: [{ value: 10, unit: "µM", count: 40 }],
    replicates: { min: 3, max: 3, not_recorded: 0 },
    run_count: 3,
    rule: "mean across runs",
    basis: ["reported"],
    needs_concentration: false,
    label: LABEL,
    short_label: SHORT,
  },
} as unknown as CampaignChannelResponse;

describe("StageColumnHeader", () => {
  it("shows the readout, its short label beneath, and the full label with its parts on hover", () => {
    const tooltip = columnTooltip(describedColumn, "Kinase Panel");
    render(<StageColumnHeader readout="% Inhibition" shortLabel={SHORT} tooltip={tooltip} />);

    expect(screen.getByText("% Inhibition")).toBeInTheDocument();
    const header = screen.getByText(SHORT).parentElement as HTMLElement;
    const lines = (header.getAttribute("title") ?? "").split("\n");
    expect(lines[0]).toBe(LABEL);
    expect(lines).toEqual(
      expect.arrayContaining([
        "Stage: Retest",
        "Protocol: Kinase Panel",
        "Concentration: 10 µM",
        "Replicates: 3",
        "Runs: 3",
        "Rule: mean across runs",
      ]),
    );
  });
});

// ── Untested cells ───────────────────────────────────────────────────────────

describe("NotDeterminedCell", () => {
  it("says quietly why a cell is untested", () => {
    render(<NotDeterminedCell unresolvedReason="several_concentrations" />);
    expect(screen.getByText("ND")).toHaveAttribute(
      "title",
      "Measured at several concentrations — choose one for this column",
    );
  });

  it("keeps the generic ND explanation when there is no reason", () => {
    render(<NotDeterminedCell unresolvedReason={null} />);
    expect(screen.getByText("ND").getAttribute("title")).toMatch(/^ND = Not Determined/);
  });
});

// ── Cell facts ───────────────────────────────────────────────────────────────

describe("MeasurementFacts", () => {
  const measurement = {
    channel_id: "ch-1",
    value: 42,
    test_concentration_value: 10,
    test_concentration_unit: "µM",
    replicate_count: null,
    contributing_run_ids: ["run-1", "run-2"],
    batch_ids: ["b-1"],
    basis: "reported",
    concentration_series: false,
  } as unknown as CampaignMeasurementResponse;

  function facts(m: CampaignMeasurementResponse) {
    render(
      <MeasurementFacts
        measurement={m}
        moleculeId="mol-1"
        campaign={{ id: "c1" } as unknown as CampaignResponse}
      />,
    );
    return screen.getByText("Concentration").closest("dl") as HTMLElement;
  }

  it("lists concentration, n, basis, batches and the runs behind the value", () => {
    const dl = facts(measurement);
    expect(dl).toHaveTextContent("Concentration10 µM");
    expect(dl).toHaveTextContent("nnot recorded");
    expect(dl).toHaveTextContent("Basisreported");
    expect(dl).toHaveTextContent("BatchesB-007");
    expect(dl).toHaveTextContent("Runs2");
    expect(screen.getByRole("link", { name: "Run on Nov 12, 2026" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run on Nov 14, 2026" })).toBeInTheDocument();
  });

  it("calls a dose-response value a concentration series and leaves n out", () => {
    const dl = facts({ ...measurement, concentration_series: true, basis: "measured" });
    expect(dl).toHaveTextContent("Concentrationconcentration series");
    expect(dl).not.toHaveTextContent("not recorded");
    expect(dl).toHaveTextContent("Basismeasured");
  });
});

describe("CompoundValueCell facts", () => {
  it("opens the value's facts from the value itself", () => {
    renderCell({ facts: <span>the facts</span> });
    fireEvent.click(screen.getByRole("button", { name: "13.6 uM" }));
    expect(screen.getByText("the facts")).toBeInTheDocument();
  });
});
