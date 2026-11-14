import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ActivitySummaryResponse } from "../../hooks/use-molecule-activity";

// Plotly doesn't render under jsdom and the curve drawing isn't what's under
// test here — the table stack inside each protocol card is.
vi.mock("@/features/screening-assay/components/dose-response-sparkline", () => ({
  DoseResponseSparkline: () => <div data-testid="sparkline" />,
}));

const activity = vi.hoisted(() => ({ data: undefined as ActivitySummaryResponse | undefined }));
vi.mock("../../hooks/use-molecule-activity", () => ({
  useMoleculeActivity: () => ({ data: activity.data, isLoading: false }),
}));

import { ActivityTab } from "./activity-tab";

function reportedRow() {
  return { value: 3.4, qualifier: ">", unit: "nM", source: "readout", data_point_count: 2 };
}

function curveRow() {
  return {
    curve_type: "ic50",
    fitted_value: 5.2,
    fitted_unit: "uM",
    r_squared: 0.97,
    hill_slope: -1.1,
    top: 100,
    bottom: 0.5,
    num_points: 8,
    curve_class: "full",
    data_points: null,
    intercept_values: [],
  };
}

function renderTab(protocol: Record<string, unknown>) {
  activity.data = {
    molecule_id: "m1",
    protocols: [
      {
        protocol_id: "p1",
        protocol_name: "NadD Dose Response",
        protocol_type: "biochemical",
        readouts: [],
        best_curves: [],
        intercepts: [],
        ...protocol,
      },
    ],
  } as unknown as ActivitySummaryResponse;
  return render(<ActivityTab moleculeId="m1" />);
}

describe("ActivityTab reported endpoints", () => {
  it("renders a curve-less reported endpoint with the reported chip", () => {
    renderTab({ readouts: [reportedRow()] });

    expect(screen.getByText("> 3.400")).toBeInTheDocument();
    expect(screen.getByText("nM")).toBeInTheDocument();
    expect(screen.getByText("reported")).toHaveAttribute(
      "title",
      "Reported endpoint — no fitted curve for this compound",
    );
    expect(screen.queryByText("No readout data for this protocol.")).toBeNull();
  });

  it("shows the reported row alongside the curve table, not instead of it", () => {
    renderTab({ readouts: [reportedRow()], best_curves: [curveRow()] });

    expect(screen.getByTestId("sparkline")).toBeInTheDocument();
    expect(screen.getByText("reported")).toBeInTheDocument();
  });

  it("keeps the empty message when a protocol has neither", () => {
    renderTab({});
    expect(screen.getByText("No readout data for this protocol.")).toBeInTheDocument();
  });
});

function plain(over: Record<string, unknown> = {}) {
  return {
    readout_definition_id: "rd1",
    readout_name: "Max ΔTm (Main)",
    value: -8.483,
    qualifier: "=",
    unit: "°C",
    data_point_count: 1,
    run_count: 2,
    draft_run_count: 1,
    ...over,
  };
}

const outside = { readout_name: "Max ΔTm (Main)", operator: "not_between", value: [-2, 2] };

describe("ActivityTab plain readouts and hit marker", () => {
  it("lists plain readouts with their value, unit and runs, drafts marked", () => {
    renderTab({
      plain_readouts: [
        plain(),
        plain({
          readout_name: "Lowest shifting conc. (Main, ±2 °C)",
          value: 50,
          qualifier: ">",
          unit: "µM",
          run_count: 1,
          draft_run_count: 1,
        }),
      ],
    });
    expect(screen.getByText("Max ΔTm (Main)")).toBeInTheDocument();
    expect(screen.getByText("-8.483")).toBeInTheDocument();
    expect(screen.getByText("2 runs (1 draft)")).toBeInTheDocument();
    expect(screen.getByText("> 50")).toBeInTheDocument();
    expect(screen.getByText("1 run (draft)")).toBeInTheDocument();
    expect(screen.queryByText("No readout data for this protocol.")).toBeNull();
  });

  it("shows the protocol's hit call with the rule it used", () => {
    renderTab({ plain_readouts: [plain()], hit: true, hit_criteria: [outside] });
    expect(screen.getByText("Hit")).toHaveAttribute(
      "title",
      "By the protocol's recommended rule: Max ΔTm (Main) outside -2 – 2",
    );
  });

  it("says not a hit when the rule is not met, and nothing without a rule", () => {
    const first = renderTab({ plain_readouts: [plain()], hit: false, hit_criteria: [outside] });
    expect(screen.getByText("Not a hit")).toBeInTheDocument();
    first.unmount();
    renderTab({ plain_readouts: [plain()], hit: null, hit_criteria: [] });
    expect(screen.queryByText("Hit")).toBeNull();
    expect(screen.queryByText("Not a hit")).toBeNull();
  });
});

describe("ActivityTab card links and provenance", () => {
  const runs = [
    { run_id: "r2", run_date: "2026-11-13", status: "draft" },
    { run_id: "r1", run_date: "2026-11-01", status: "approved" },
  ];

  it("links the protocol, shows its code, and links each run to its results tab", () => {
    renderTab({
      plain_readouts: [plain()],
      protocol_code: "PRT-00219",
      runs,
      results_tab: "curves",
    });
    expect(screen.getByRole("link", { name: "NadD Dose Response" })).toHaveAttribute(
      "href",
      "/assays/protocols/p1",
    );
    expect(screen.getByText("PRT-00219")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Nov 13, 2026 · Draft" })).toHaveAttribute(
      "href",
      "/assays/runs/r2#curves",
    );
    expect(screen.getByRole("link", { name: "Nov 1, 2026 · Approved" })).toHaveAttribute(
      "href",
      "/assays/runs/r1#curves",
    );
  });

  it("a run link without a results tab opens the run page", () => {
    renderTab({ plain_readouts: [plain()], runs: [runs[1]], results_tab: null });
    expect(screen.getByRole("link", { name: "Nov 1, 2026 · Approved" })).toHaveAttribute(
      "href",
      "/assays/runs/r1",
    );
  });

  it("says how each value was chosen", () => {
    renderTab({
      plain_readouts: [
        plain({ best_direction: "magnitude", data_point_count: 6, run_count: 2 }),
        plain({
          readout_definition_id: "rd2",
          readout_name: "Lowest shifting conc.",
          value: 6.25,
          best_direction: "low",
          data_point_count: 2,
          run_count: 2,
        }),
        plain({
          readout_definition_id: "rd3",
          readout_name: "Signal",
          value: 9,
          best_direction: "high",
          data_point_count: 1,
          run_count: 1,
          draft_run_count: 0,
        }),
      ],
    });
    expect(screen.getByText("-8.483")).toHaveAttribute(
      "title",
      "Largest shift in either direction of 6 values in 2 runs",
    );
    expect(screen.getByText("6.25")).toHaveAttribute("title", "Lowest of 2 values in 2 runs");
    expect(screen.getByText("9")).toHaveAttribute("title", "From 1 value in 1 run");
  });
});
