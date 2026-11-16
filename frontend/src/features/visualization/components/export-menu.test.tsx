import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { dataset, panel } from "../lib/traces/test-fixtures";
import { WorkbenchProvider } from "../store/workbench-context";
import { ExportMenu } from "./export-menu";

const downloadImage = vi.hoisted(() => vi.fn());
vi.mock("@/shared/lib/plotly", () => ({ getPlotlyGlobal: () => ({ downloadImage }) }));

const ds = dataset({ well_order: [1, 2], y: [3, 4] });
const scatter = panel("scatter", { x: "well_order", y: "y" });

function show() {
  const table = { current: { exportCsv: vi.fn() } };
  render(
    <WorkbenchProvider initialPanels={[scatter]}>
      <section data-panel-id="p1">
        <div className="js-plotly-plot" data-testid="graph" />
      </section>
      <ExportMenu ds={ds} table={table} />
    </WorkbenchProvider>,
  );
  fireEvent.keyDown(screen.getByRole("button", { name: "Export" }), { key: "Enter" });
  return table.current.exportCsv;
}

describe("ExportMenu", () => {
  it("exports the table as CSV", () => {
    const exportCsv = show();
    fireEvent.click(screen.getByRole("menuitem", { name: "Table as CSV" }));
    expect(exportCsv).toHaveBeenCalledWith("wells.csv");
  });

  it("downloads a plot as PNG named after its title, and says why not SVG", () => {
    show();
    expect(screen.getByText(/SVG of WebGL plots embeds a raster/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: "Signal by well_order" }));
    expect(downloadImage).toHaveBeenCalledWith(
      screen.getByTestId("graph"),
      expect.objectContaining({ format: "png", filename: "Signal-by-well_order" }),
    );
  });
});
