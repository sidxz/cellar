import { potencyShade } from "@/features/sar-analysis/lib/sar-activity-display";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { matrixWells, panel } from "../../lib/traces/test-fixtures";
import { WorkbenchProvider, useWorkbench } from "../../store/workbench-context";
import type { PanelPatch } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import { RGroupMatrixPanel } from "./rgroup-matrix-panel";

vi.mock("@/shared/components/chemistry", () => ({ StructureThumbnail: () => null }));

const CL_H = "R1 Cl × R2 –H: 2 compounds";
const F_H = "R1 F × R2 –H: 1 compound";

/** matrixWells plus an IC50 geomean column (a potency). */
function withPotency(): Dataset {
  const ds = matrixWells();
  return {
    ...ds,
    columns: [
      ...ds.columns,
      {
        key: "dr:rd:raw",
        label: "Enzyme · IC50",
        kind: "number",
        unit: "uM",
        provenance: { readout_definition_id: "rd", aggregation: "geomean" },
      },
    ],
    values: { ...ds.values, "dr:rd:raw": [0.1, 0.1, 0.1, 0.1, null, 1, null] },
  };
}

function Selection() {
  const ids = useWorkbench((s) => [...s.selection].join(","));
  return <output data-testid="selection">{ids}</output>;
}

function show(patch: PanelPatch = {}, ds = matrixWells()) {
  const p = panel("rgroup-matrix", {
    category: "chem:rg1:R1",
    x: "chem:rg1:R2",
    y: "rd:s:raw",
    ...patch,
  });
  render(
    <WorkbenchProvider initialPanels={[p]}>
      <RGroupMatrixPanel panel={p} ds={ds} />
      <Selection />
    </WorkbenchProvider>,
  );
}

describe("RGroupMatrixPanel", () => {
  it("selects a cell's rows on click and outlines it", () => {
    show();
    fireEvent.click(screen.getByTitle(CL_H));
    expect(screen.getByTestId("selection")).toHaveTextContent("w0,w1,w2,w3");
    expect(screen.getByTitle(CL_H)).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTitle(F_H)).toHaveAttribute("aria-pressed", "false");
  });

  it("shows the median, the compound count and what it could not place", () => {
    show();
    expect(screen.getByTitle(CL_H)).toHaveTextContent("6.5");
    expect(screen.getByTitle(CL_H)).toHaveTextContent("n=2");
    expect(screen.getByText(/1 row doesn't match the core/)).toBeInTheDocument();
    expect(screen.getByText(/1 row has no compound/)).toBeInTheDocument();
  });

  it("counts compounds when no value is chosen", () => {
    show({ y: undefined });
    expect(screen.getByTitle(CL_H)).toHaveTextContent(/^2$/);
  });

  it("shades potencies by fold off the most potent cell", () => {
    show({ y: "dr:rd:raw" }, withPotency());
    expect(screen.getByTitle(CL_H)).toHaveTextContent("0.1 uM");
    // The ramp itself is potencyShade's (tested there); here: the reference is the
    // most potent cell, so Cl sits at 1× and F (1 uM) at 10× off it.
    expect(screen.getByTitle(CL_H).className).toContain(potencyShade(0.1, 0.1));
    expect(screen.getByTitle(F_H).className).toContain(potencyShade(1, 0.1));
    expect(potencyShade(1, 0.1)).not.toBe(potencyShade(0.1, 0.1));
    expect(screen.queryByText("Shading is for potencies only")).not.toBeInTheDocument();
  });

  it("does not shade a value that is not a potency", () => {
    show();
    expect(screen.getByTitle(CL_H).className).not.toMatch(/bg-(green|amber|orange|red)/);
    expect(screen.getByText("Shading is for potencies only")).toBeInTheDocument();
  });
});
