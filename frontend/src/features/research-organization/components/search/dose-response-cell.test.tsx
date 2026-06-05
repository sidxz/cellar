import { describe, expect, it, vi } from "vitest";

// Capture the curve prop the cell hands to DoseResponseFigure. We aren't
// asserting on chart rendering here — that's covered by
// dose-response-figure.test.tsx. We're verifying the wire-shape passthrough
// in DoseResponseCell.
const figureCalls: Array<Record<string, unknown>> = [];
vi.mock("@/features/screening-assay/components/dose-response-figure", () => ({
  DoseResponseFigure: (props: Record<string, unknown>) => {
    figureCalls.push(props);
    return null;
  },
}));

import { render } from "@testing-library/react";
import type { ActivityValue } from "../../types";
import { DoseResponseCell } from "./dose-response-cell";

function reset() {
  figureCalls.length = 0;
}

const BASE_AV: ActivityValue = {
  value: 0.2,
  qualifier: null,
  unit: "uM",
  source: "dose_response",
  curve_type: "ic50",
  r_squared: 0.97,
  data_point_count: 8,
  raw_data: [
    { x: 0.1, y: 5 },
    { x: 1, y: 50 },
    { x: 10, y: 95 },
  ],
  curve_params: {
    hill_slope: -1.0,
    top: 100,
    bottom: 0,
    num_points: 8,
    curve_class: "full",
    confidence_interval_low: 0.15,
    confidence_interval_high: 0.27,
  },
};

describe("<DoseResponseCell /> — aggregate overlay passthrough", () => {
  it("threads additional_curves + aggregate into the figure curve prop", () => {
    reset();
    const av: ActivityValue = {
      ...BASE_AV,
      additional_curves: [
        {
          fitted_value: 0.4,
          top: 100,
          bottom: 0,
          hill_slope: -1.0,
          r_squared: 0.95,
          curve_class: "full",
          raw_data: null,
          run_date: "2026-03-01",
          run_id: "11111111-1111-1111-1111-111111111111",
        },
      ],
      aggregate: { marker_x: 0.2, marker_label: "gmean", unit: "uM" },
    };

    render(<DoseResponseCell value={av} />);

    expect(figureCalls).toHaveLength(1);
    const curve = figureCalls[0].curve as {
      additional_curves: unknown[];
      aggregate: { marker_label: string };
    };
    expect(curve.additional_curves).toHaveLength(1);
    expect(curve.aggregate.marker_label).toBe("gmean");
  });

  it("passes null overlay fields when av has no aggregate (latest-mode)", () => {
    reset();
    render(<DoseResponseCell value={BASE_AV} />);

    expect(figureCalls).toHaveLength(1);
    const curve = figureCalls[0].curve as {
      additional_curves: unknown;
      aggregate: unknown;
    };
    expect(curve.additional_curves).toBeNull();
    expect(curve.aggregate).toBeNull();
  });

  it("renders an em-dash and skips the figure when raw_data is missing", () => {
    reset();
    const av: ActivityValue = { ...BASE_AV, raw_data: null };
    const { container } = render(<DoseResponseCell value={av} />);

    expect(figureCalls).toHaveLength(0);
    expect(container.textContent).toContain("—");
  });
});
