import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkbenchProvider } from "../store/workbench-context";
import { makePanel } from "../store/workbench-store";
import type { Dataset, DatasetColumn } from "../types";
import { AddPlotMenu } from "./add-plot-menu";
import { PanelGrid } from "./panel-grid";

vi.mock("@/shared/lib/plotly", () => ({ Plot: () => null }));

const col = (key: string, label: string, kind: DatasetColumn["kind"]): DatasetColumn => ({
  key,
  label,
  kind,
  provenance: {},
});
const dataset = (numeric = true): Dataset => ({
  revision: "r",
  level: "wells",
  row_count: 2,
  row_ids: ["w0", "w1"],
  columns: [
    col("well_type", "Well type", "category"),
    col("well_order", "Well order", "number"),
    col("rd:s:raw", "Signal", numeric ? "number" : "category"),
  ],
  values: {
    well_type: ["sample", "blank"],
    well_order: [1, 2],
    "rd:s:raw": numeric ? [1, 2] : ["a", "b"],
  },
});

const FULL = "Up to 4 plots — close one to add another";
const noEdit = () => {};

function show(panels: number, ds = dataset()) {
  const initial = Array.from({ length: panels }, () =>
    makePanel("bar", { agg: "count", category: "well_type" }),
  );
  return render(
    <WorkbenchProvider initialPanels={initial}>
      <AddPlotMenu ds={ds} />
      <PanelGrid ds={ds} onEdit={noEdit} />
    </WorkbenchProvider>,
  );
}

const openMenu = (name: RegExp) =>
  fireEvent.keyDown(screen.getAllByRole("button", { name })[0], { key: "Enter" });

describe("PanelGrid and AddPlotMenu", () => {
  it("adds a histogram of the first numeric readout, stacked by well type", () => {
    show(1);
    openMenu(/Add plot \(1\/4\)/);
    fireEvent.click(screen.getByRole("menuitem", { name: "Histogram" }));
    expect(screen.getByRole("region", { name: "Distribution of Signal" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add plot (2/4)" })).toBeEnabled();
  });

  it("disables the menu at four plots and says why", () => {
    show(4);
    const button = screen.getByRole("button", { name: "Add plot (4/4)" });
    expect(button).toBeDisabled();
    expect(button.closest("[title]")).toHaveAttribute("title", FULL);
  });

  it("offers an Add plot call to action when the last plot is closed", () => {
    show(1);
    fireEvent.click(screen.getByRole("button", { name: "Close plot" }));
    expect(screen.getByText("No plots yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add plot (0/4)" })).toHaveLength(2);
  });

  it("shows only the maximized plot", () => {
    show(2);
    expect(screen.getAllByRole("region")).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: "Maximize plot" })[0]);
    expect(screen.getAllByRole("region")).toHaveLength(1);
  });

  it("offers only the count bar when nothing is numeric", () => {
    show(1, dataset(false));
    openMenu(/Add plot/);
    expect(screen.getByRole("menuitem", { name: "Bar" })).not.toHaveAttribute("data-disabled");
    for (const name of ["Scatter", "Histogram", "Box"]) {
      expect(screen.getByRole("menuitem", { name })).toHaveAttribute("data-disabled");
    }
    expect(screen.getByText(/no numeric fields to plot/i)).toBeInTheDocument();
  });
});
