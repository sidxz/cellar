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
