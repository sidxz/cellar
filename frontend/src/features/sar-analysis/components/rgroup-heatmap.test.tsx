import type { Molecule } from "@/features/chemical-registration/types";
import type { ActivityValue } from "@/features/research-organization/types";
import type { RGroupDecompositionResponse } from "@/shared/lib/api/model";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SarColorSpec } from "../lib/sar-color-spec";

// RDKit-free shim for the chemistry barrel (StructureThumbnail uses WASM that
// jsdom can't run). Render the SMILES into a testid so axis headers are
// assertable. Same convention as rgroup-core-picker.test.tsx.
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => <div data-testid={`thumb-${smiles}`} />,
}));

// CurveExpandDialog pulls in the Plotly DoseResponseChart — stub it and surface
// the molecule label it was opened with so the cell-click is assertable.
vi.mock("@/features/screen-campaign/components/grid/curve-expand-dialog", () => ({
  CurveExpandDialog: ({ data }: { data: { moleculeLabel: string } | null }) =>
    data ? <div data-testid="curve-dialog">{data.moleculeLabel}</div> : null,
}));

import { RGroupHeatmap } from "./rgroup-heatmap";

// Two R-positions, four assignments. (R1=F, R2=H) holds m1+m2 (a multi-compound
// cell); (R1=Cl, R2=H) holds m3; (R1=F, R2=Me) holds m4. (R1=Cl, R2=Me) is a
// gap (no assignment). yValues = R2 substituents, xValues = R1 substituents.
const decomposition: RGroupDecompositionResponse = {
  core_smiles: "c1ccccc1",
  rgroup_labels: ["R1", "R2"],
  assignments: [
    { molecule_id: "m1", rgroups: { R1: "F[*:1]", R2: "[H][*:2]" } },
    { molecule_id: "m2", rgroups: { R1: "F[*:1]", R2: "[H][*:2]" } },
    { molecule_id: "m3", rgroups: { R1: "Cl[*:1]", R2: "[H][*:2]" } },
    { molecule_id: "m4", rgroups: { R1: "F[*:1]", R2: "C[*:2]" } },
  ],
  unmatched_ids: [],
};

const colorSpec: SarColorSpec = {
  protocolId: "p1",
  column: "drc:rd1",
  interceptKey: null,
  source: "dr_curve",
  label: "EGFR · IC50",
};

/** Minimal DR ActivityValue carrying a primary scalar (`value`) + a unit, with
 *  enough shape for `snapshotFromActivity` to produce a curve. */
function drActivity(value: number): ActivityValue {
  return {
    value,
    qualifier: "=",
    unit: "nM",
    source: "dose_response",
    curve_type: "ic50",
    r_squared: 0.99,
    data_point_count: 8,
    raw_data: [
      { x: 1e-9, y: 100 },
      { x: 1e-6, y: 0 },
    ],
    curve_params: {
      hill_slope: 1,
      top: 100,
      bottom: 0,
      num_points: 8,
      curve_class: "full",
      confidence_interval_low: null,
      confidence_interval_high: null,
    },
  } as ActivityValue;
}

const activityByMolecule: Record<string, ActivityValue | undefined> = {
  m1: drActivity(50),
  m2: drActivity(5), // most potent in the m1+m2 cell
  m3: drActivity(500),
  m4: drActivity(100),
};

const molecules = [
  { id: "m1", registration_number: "CV-1", name: "a" },
  { id: "m2", registration_number: "CV-2", name: "b" },
  { id: "m3", registration_number: "CV-3", name: "c" },
  { id: "m4", registration_number: "CV-4", name: "d" },
] as Molecule[];

function renderHeatmap(overrides: Partial<React.ComponentProps<typeof RGroupHeatmap>> = {}) {
  return render(
    <RGroupHeatmap
      decomposition={decomposition}
      activityByMolecule={activityByMolecule}
      colorSpec={colorSpec}
      molecules={molecules}
      {...overrides}
    />,
  );
}

describe("RGroupHeatmap", () => {
  it("shows the empty state when no colorSpec is set", () => {
    renderHeatmap({ colorSpec: null });
    expect(screen.getByText(/Pick an activity .*to populate the heatmap/i)).toBeInTheDocument();
  });

  it("shows the empty state when fewer than two R-positions exist", () => {
    renderHeatmap({
      decomposition: { ...decomposition, rgroup_labels: ["R1"] },
    });
    expect(screen.getByText(/Need at least two R-group positions/i)).toBeInTheDocument();
  });

  it("renders axis headers for every distinct substituent (default R1=Y, R2=X)", () => {
    renderHeatmap();
    // Default axisY = labels[0] = R1, axisX = labels[1] = R2.
    // R1 substituents (Y rows): F, Cl. R2 substituents (X cols): H, Me.
    expect(screen.getByTestId("thumb-F[*:1]")).toBeInTheDocument();
    expect(screen.getByTestId("thumb-Cl[*:1]")).toBeInTheDocument();
    expect(screen.getByTestId("thumb-[H][*:2]")).toBeInTheDocument();
    expect(screen.getByTestId("thumb-C[*:2]")).toBeInTheDocument();
  });

  it("renders a populated cell with the most-potent scalar + unit", () => {
    renderHeatmap();
    // The (R1=F, R2=H) cell holds m1(50) + m2(5) → best = 5 nM.
    expect(screen.getByText("5 nM")).toBeInTheDocument();
  });

  it("shows a +N badge for a multi-compound cell", () => {
    renderHeatmap();
    // m1+m2 share one cell → one extra compound → "+1".
    expect(screen.getByText("+1")).toBeInTheDocument();
  });

  it("renders a gap state for an unoccupied combo", () => {
    renderHeatmap();
    // (R1=F, R2=H), (R1=Cl, R2=H), (R1=F, R2=Me) are occupied; (R1=Cl, R2=Me)
    // is a gap → renders the "make?" affordance exactly once.
    expect(screen.getByText("make?")).toBeInTheDocument();
  });

  it("opens the curve dialog for the most-potent molecule on cell click", () => {
    renderHeatmap();
    // Click the populated multi-compound cell (its best value reads 5 nM).
    fireEvent.click(screen.getByText("5 nM"));
    const dialog = screen.getByTestId("curve-dialog");
    // Most potent of m1(50)/m2(5) is m2 → CV-2.
    expect(within(dialog).getByText("CV-2")).toBeInTheDocument();
  });

  it("does not color cells for a readout_data (higher-is-better) source", () => {
    const { container } = renderHeatmap({
      colorSpec: { ...colorSpec, source: "readout_data", label: "EGFR · % inh" },
    });
    // No potency ramp classes should appear on any cell when the source is
    // higher-is-better (the value still renders; here m2 = 5 in the shared cell).
    expect(container.querySelector(".bg-green-600\\/30")).toBeNull();
    expect(container.querySelector(".bg-red-600\\/30")).toBeNull();
    // The legend explains the uncolored readout instead of showing the ramp.
    expect(screen.getByText(/higher-is-better readout/i)).toBeInTheDocument();
  });
});
