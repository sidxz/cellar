import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RGroupHeatmap, cellKey } from "./rgroup-heatmap";

// ---------------------------------------------------------------------------
// Controllable heatmap data + mocked heavy children (RDKit thumbnail, Plotly
// curve dialog) so the component renders in jsdom.
// ---------------------------------------------------------------------------
type HeatmapReturn = { data: unknown; isLoading: boolean; error: Error | null };
let heatmapReturn: HeatmapReturn = { data: null, isLoading: true, error: null };

vi.mock("../hooks/use-heatmap-aggregation", () => ({
  useHeatmapAggregation: () => heatmapReturn,
}));
vi.mock("@/shared/components/chemistry", () => ({ StructureThumbnail: () => null }));
vi.mock("@/features/screen-campaign/components/grid/curve-expand-dialog", () => ({
  CurveExpandDialog: ({ data }: { data: unknown }) => (data ? <div>curve-open</div> : null),
}));

const COLOR_SPEC = {
  protocolId: "p",
  column: "drc:rd",
  interceptKey: null,
  source: "dr_curve",
  label: "IC50",
} as const;

function _result(over: Record<string, unknown> = {}) {
  return {
    y_values: ["F", "Br"],
    x_values: ["Cl"],
    cells: [
      {
        y: "F",
        x: "Cl",
        count: 2,
        best_scalar: 0.1,
        best_molecule_id: "m1",
        best_molecule_label: "CV-1",
        best_snapshot: { value: 0.1, unit: "uM" },
      },
      // Unscreened corner: matched molecules, no activity value for the channel.
      {
        y: "Br",
        x: "Cl",
        count: 3,
        best_scalar: null,
        best_molecule_id: "m2",
        best_molecule_label: "CV-2",
        best_snapshot: {},
      },
    ],
    y_total: 2,
    x_total: 1,
    truncated: false,
    activity_reference: 0.1,
    ...over,
  };
}

describe("cellKey", () => {
  it("is stable + collision-free", () => {
    expect(cellKey("F", "Cl")).toBe(cellKey("F", "Cl"));
    expect(cellKey("F", "Cl")).not.toBe(cellKey("Cl", "F"));
  });
});

describe("RGroupHeatmap rendering", () => {
  beforeEach(() => {
    heatmapReturn = { data: null, isLoading: true, error: null };
  });

  it("keeps an unscreened cell (no activity) as an uncolored '—', not a dropped gap", () => {
    heatmapReturn = { data: _result(), isLoading: false, error: null };
    render(
      <RGroupHeatmap
        runId="run-1"
        projectionId="proj-1"
        labels={["R1", "R2"]}
        colorSpec={COLOR_SPEC}
      />,
    );
    // The (Br, Cl) corner has matched molecules but no value -> rendered as "—".
    expect(screen.getByText("—")).toBeTruthy();
    // Its count still surfaces via the "+N more" badge (count 3 -> +2).
    expect(screen.getByText("+2")).toBeTruthy();
    // The scored (F, Cl) cell shows a +1 badge (count 2).
    expect(screen.getByText("+1")).toBeTruthy();
  });

  it("shows an honest 'top N of M' note when truncated", () => {
    heatmapReturn = {
      data: _result({ truncated: true, y_total: 50 }),
      isLoading: false,
      error: null,
    };
    render(
      <RGroupHeatmap
        runId="run-1"
        projectionId="proj-1"
        labels={["R1", "R2"]}
        colorSpec={COLOR_SPEC}
      />,
    );
    expect(screen.getByText(/of 50/)).toBeTruthy();
  });
});
